"""Presentation feedback and learned presentation config (D-16..D-19). Local, per user/workspace.

Stores what was predicted (Decisions hint), what was shown (validated cards), and what the user
said (thumbs, explicit layout choice) as separate facts. Nothing here changes tools, grants or memory.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from uuid import uuid4

from app.vault_runtime.conversation.contracts import InputError, NotFoundError
from app.vault_runtime.conversation.repository import ConversationRepository
from .catalog import LAYOUT_KEYS

TEXT = "text"
CHOICES = (TEXT, *LAYOUT_KEYS)
DEFAULT_CONFIG = {"weights": {}, "guidance": {}, "visualThreshold": 0.5}
NEIGHBOR_SIMILARITY = 0.82
MAX_SCAN = 500

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS vault_private.vault_genui_feedback (
       feedback_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
       conversation_id text NOT NULL, turn_id text NOT NULL,
       verdict text CHECK(verdict IN ('up','down')), chosen_layout text,
       predicted jsonb, shown jsonb NOT NULL DEFAULT '[]'::jsonb, previews jsonb,
       embedding jsonb, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
       UNIQUE(user_id,workspace_id,turn_id),
       FOREIGN KEY(user_id,workspace_id,conversation_id,turn_id) REFERENCES
         vault_private.vault_conversation_turns(user_id,workspace_id,conversation_id,turn_id) ON DELETE CASCADE)""",
    """CREATE INDEX IF NOT EXISTS idx_genui_feedback_scope
       ON vault_private.vault_genui_feedback(user_id,workspace_id,updated_at DESC)""",
    """CREATE TABLE IF NOT EXISTS vault_private.vault_genui_presentation_config (
       user_id text NOT NULL, workspace_id text NOT NULL, version integer NOT NULL CHECK(version>0),
       config jsonb NOT NULL, state text NOT NULL CHECK(state IN ('active','undone')),
       notice jsonb, notice_pending boolean NOT NULL DEFAULT false,
       created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(user_id,workspace_id,version))""",
)


def cosine(left, right) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


class GenuiFeedbackStore:
    def __init__(self, *, database_url, embedder_factory=None):
        self.database_url, self.embedder_factory = database_url, embedder_factory

    def _connect(self):
        import psycopg
        return psycopg.connect(self.database_url)

    def ensure_schema(self):
        with self._connect() as connection, connection.cursor() as cursor:
            for statement in STATEMENTS:
                cursor.execute(statement)

    @staticmethod
    def _scope(principal):
        return principal.user_id, principal.workspace_id

    def _embed(self, principal, text):
        if self.embedder_factory is None:
            return None
        try:
            vector = self.embedder_factory(principal.user_id, principal.workspace_id).embed_query(text[:4000])
            return [round(float(v), 6) for v in vector]
        except Exception:
            return None  # Local embeddings unavailable: feedback is kept, neighbours are skipped.

    # ── turn facts ──────────────────────────────────────────────
    def turn_facts(self, principal, conversation_id, turn_id):
        """Final input, answer, shown cards and the hint for one completed turn of this user."""
        with self._connect() as connection, connection.cursor() as cursor:
            ConversationRepository._require_authority(cursor, principal)
            cursor.execute("""SELECT t.input_text,t.state,
                (SELECT e.payload->>'text' FROM vault_private.vault_conversation_events e WHERE e.turn_id=t.turn_id
                   AND e.user_id=t.user_id AND e.kind='assistant_final' ORDER BY e.sequence DESC LIMIT 1),
                (SELECT jsonb_agg(e.payload->'card' ORDER BY e.sequence) FROM vault_private.vault_conversation_events e
                   WHERE e.turn_id=t.turn_id AND e.user_id=t.user_id AND e.kind='ui'),
                (SELECT e.payload->'finalPreparation'->'presentation' FROM vault_private.vault_conversation_events e
                   WHERE e.turn_id=t.turn_id AND e.user_id=t.user_id AND e.kind='context' ORDER BY e.sequence LIMIT 1)
              FROM vault_private.vault_conversation_turns t
              WHERE t.user_id=%s AND t.workspace_id=%s AND t.conversation_id=%s AND t.turn_id=%s""",
              (*self._scope(principal), conversation_id, turn_id))
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError("Conversation turn unavailable.")
        if row[1] != "completed":
            raise InputError("Feedback is available after a reply completes.")
        return dict(input=row[0], answer=row[2] or "", cards=row[3] or [], presentation=row[4])

    def _upsert(self, principal, conversation_id, turn_id, **fields):
        facts = self.turn_facts(principal, conversation_id, turn_id)
        shown = [card.get("layout") for card in facts["cards"]] or [TEXT]
        sets = ", ".join(f"{name}=EXCLUDED.{name}" for name in fields)
        columns = ["feedback_id", "user_id", "workspace_id", "conversation_id", "turn_id", "predicted", "shown", *fields]
        values = [str(uuid4()), *self._scope(principal), conversation_id, turn_id,
                  json.dumps(facts["presentation"]), json.dumps(shown),
                  *[json.dumps(v) if name in ("previews", "embedding") else v for name, v in fields.items()]]
        with self._connect() as connection, connection.cursor() as cursor:
            ConversationRepository._require_authority(cursor, principal)
            cursor.execute(f"""INSERT INTO vault_private.vault_genui_feedback ({",".join(columns)})
              VALUES ({",".join(["%s"] * len(columns))})
              ON CONFLICT(user_id,workspace_id,turn_id) DO UPDATE SET {sets}{"," if sets else ""} updated_at=now()
              RETURNING verdict,chosen_layout,previews IS NOT NULL""", values)
            row = cursor.fetchone()
        return facts, dict(verdict=row[0], chosenLayout=row[1], hasPreviews=row[2], shown=shown)

    def record_verdict(self, principal, conversation_id, turn_id, verdict):
        if verdict not in ("up", "down", None):
            raise InputError("Verdict must be up, down or null.")
        return self._upsert(principal, conversation_id, turn_id, verdict=verdict)[1]

    def store_previews(self, principal, conversation_id, turn_id, previews):
        return self._upsert(principal, conversation_id, turn_id, previews=previews)[1]

    def cached_previews(self, principal, turn_id):
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT previews FROM vault_private.vault_genui_feedback
              WHERE user_id=%s AND workspace_id=%s AND turn_id=%s""", (*self._scope(principal), turn_id))
            row = cursor.fetchone()
        return row[0] if row and row[0] else None

    def record_choice(self, principal, conversation_id, turn_id, layout):
        if layout not in CHOICES:
            raise InputError("Unknown layout choice.")
        previews = self.cached_previews(principal, turn_id) or []
        if layout != TEXT and layout not in {p.get("layout") for p in previews}:
            raise InputError("Choose one of the previews you were shown.")
        facts = self.turn_facts(principal, conversation_id, turn_id)
        embedding = self._embed(principal, facts["input"])
        return self._upsert(principal, conversation_id, turn_id, chosen_layout=layout, verdict="down"
                            if layout not in ([c.get("layout") for c in facts["cards"]] or [TEXT]) else "up",
                            embedding=embedding)[1]

    # ── neighbours (explicit choices only) ─────────────────────
    def neighbors(self, principal, vector, *, limit=5, similarity=NEIGHBOR_SIMILARITY):
        if not vector:
            return []
        with self._connect() as connection, connection.cursor() as cursor:
            ConversationRepository._require_authority(cursor, principal)
            cursor.execute("""SELECT f.chosen_layout,f.embedding,t.input_text,f.updated_at
              FROM vault_private.vault_genui_feedback f JOIN vault_private.vault_conversation_turns t
                ON t.turn_id=f.turn_id AND t.user_id=f.user_id AND t.workspace_id=f.workspace_id
              WHERE f.user_id=%s AND f.workspace_id=%s AND f.chosen_layout IS NOT NULL AND f.embedding IS NOT NULL
              ORDER BY f.updated_at DESC LIMIT %s""", (*self._scope(principal), MAX_SCAN))
            rows = cursor.fetchall()
        scored = [(cosine(vector, row[1]), row) for row in rows]
        scored = sorted((s for s in scored if s[0] >= similarity), key=lambda s: -s[0])[:limit]
        return [dict(layout=row[0], request=row[2][:160], similarity=round(score, 3), at=row[3].isoformat())
                for score, row in scored]

    # ── learned config (versioned) ──────────────────────────────
    def config(self, principal):
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT version,config,notice,notice_pending FROM vault_private.vault_genui_presentation_config
              WHERE user_id=%s AND workspace_id=%s AND state='active' ORDER BY version DESC LIMIT 1""",
              self._scope(principal))
            row = cursor.fetchone()
        if row is None:
            return dict(version=0, config=dict(DEFAULT_CONFIG), notice=None, noticePending=False)
        return dict(version=row[0], config={**DEFAULT_CONFIG, **row[1]}, notice=row[2], noticePending=row[3])

    def save_config(self, principal, config, notice):
        with self._connect() as connection, connection.cursor() as cursor:
            ConversationRepository._require_authority(cursor, principal)
            cursor.execute("""SELECT coalesce(max(version),0)+1 FROM vault_private.vault_genui_presentation_config
              WHERE user_id=%s AND workspace_id=%s""", self._scope(principal))
            version = cursor.fetchone()[0]
            cursor.execute("""INSERT INTO vault_private.vault_genui_presentation_config
              (user_id,workspace_id,version,config,state,notice,notice_pending) VALUES(%s,%s,%s,%s,'active',%s,true)""",
              (*self._scope(principal), version, json.dumps(config), json.dumps(dict(notice, version=version))))
        return version

    def keep(self, principal, version):
        self._update_version(principal, version, "notice_pending=false")

    def undo(self, principal, version):
        self._update_version(principal, version, "state='undone',notice_pending=false")

    def _update_version(self, principal, version, assignment):
        if type(version) is not int or version < 1:
            raise InputError("Invalid presentation version.")
        with self._connect() as connection, connection.cursor() as cursor:
            ConversationRepository._require_authority(cursor, principal)
            cursor.execute(f"""UPDATE vault_private.vault_genui_presentation_config SET {assignment}
              WHERE user_id=%s AND workspace_id=%s AND version=%s AND state='active'""", (*self._scope(principal), version))
            if cursor.rowcount != 1:
                raise NotFoundError("Presentation change unavailable.")

    def reset(self, principal):
        """Forget learned presentation: feedback, choices and tuned versions for this user/workspace."""
        with self._connect() as connection, connection.cursor() as cursor:
            ConversationRepository._require_authority(cursor, principal)
            cursor.execute("DELETE FROM vault_private.vault_genui_feedback WHERE user_id=%s AND workspace_id=%s",
                           self._scope(principal))
            removed = cursor.rowcount
            cursor.execute("DELETE FROM vault_private.vault_genui_presentation_config WHERE user_id=%s AND workspace_id=%s",
                           self._scope(principal))
        return removed

    # ── tuner evidence + export ─────────────────────────────────
    def recent_choices(self, principal, *, days=30):
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT f.chosen_layout,f.shown,f.embedding,t.input_text,f.previews
              FROM vault_private.vault_genui_feedback f JOIN vault_private.vault_conversation_turns t
                ON t.turn_id=f.turn_id AND t.user_id=f.user_id AND t.workspace_id=f.workspace_id
              WHERE f.user_id=%s AND f.workspace_id=%s AND f.chosen_layout IS NOT NULL AND f.embedding IS NOT NULL
                AND f.updated_at>now()-make_interval(days=>%s) ORDER BY f.updated_at DESC LIMIT %s""",
              (*self._scope(principal), days, MAX_SCAN))
            return [dict(layout=r[0], shown=r[1], embedding=r[2], request=r[3], previews=r[4] or []) for r in cursor.fetchall()]

    def export(self, principal, *, include_text=False, catalog_version=1):
        with self._connect() as connection, connection.cursor() as cursor:
            ConversationRepository._require_authority(cursor, principal)
            cursor.execute("""SELECT f.feedback_id,f.verdict,f.chosen_layout,f.predicted,f.shown,
                (SELECT jsonb_agg(p->>'layout') FROM jsonb_array_elements(coalesce(f.previews,'[]'::jsonb)) p),
                f.created_at,f.updated_at,t.input_text,
                (SELECT e.payload->>'model' FROM vault_private.vault_conversation_events e WHERE e.turn_id=t.turn_id
                   AND e.user_id=t.user_id AND e.kind='context' ORDER BY e.sequence LIMIT 1)
              FROM vault_private.vault_genui_feedback f JOIN vault_private.vault_conversation_turns t
                ON t.turn_id=f.turn_id AND t.user_id=f.user_id AND t.workspace_id=f.workspace_id
              WHERE f.user_id=%s AND f.workspace_id=%s ORDER BY f.created_at LIMIT 5000""", self._scope(principal))
            rows = cursor.fetchall()
        items = []
        for index, r in enumerate(rows, 1):
            item = dict(item=index, verdict=r[1], chosenLayout=r[2], predicted=r[3], shown=r[4],
                        previewLayouts=r[5] or [], model=r[9], recordedAt=r[7].isoformat())
            if include_text:
                item["request"] = r[8]
            items.append(item)
        return dict(format="resono-vault-genui-feedback", formatVersion=1, catalogVersion=catalog_version,
                    exportedAt=datetime.now(UTC).isoformat(), includesRequestText=include_text,
                    config=self.config(principal)["config"], items=items)
