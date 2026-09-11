from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from hashlib import sha256
from typing import Any
from uuid import uuid4

from app.vault_runtime.memory.contracts import (
    MEMORY_AUTHORITIES,
    REVIEWER_CONTRACT_VERSION,
    MemoryCandidate,
    MemoryContractError,
)
from app.vault_runtime.memory.models import (
    MemoryEmbedding,
    MemoryRecord,
    PendingMemoryAction,
    TranscriptEntry,
)
from app.vault_runtime.memory.schema import ensure_memory_schema


class MemoryRepositoryError(RuntimeError):
    code = "memory_repository_error"


class MemoryAuthorizationError(MemoryRepositoryError):
    code = "memory_authorization_denied"


class MemoryNotFoundError(MemoryRepositoryError):
    code = "memory_not_found"


class MemoryConfirmationError(MemoryRepositoryError):
    code = "memory_confirmation_required"


def transcript_fingerprint(entries: Iterable[TranscriptEntry]) -> str:
    digest = sha256()
    for entry in entries:
        digest.update(
            json.dumps(
                {
                    "entryIndex": entry.entry_index,
                    "role": entry.role,
                    "eventType": entry.event_type,
                    "text": entry.text_content,
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()


class MemoryRepository:
    """Voice PostgreSQL persistence adapted to Phase 2 local scope.

    R1 contributes the reconciliation lifecycle; this class deliberately does
    not model a memory/reviewer agent.
    """

    def __init__(
        self,
        *,
        database_url: str,
        connector: Callable[..., AbstractContextManager[Any]] | None = None,
    ) -> None:
        self._database_url = database_url
        self._connector = connector

    def _connect(self):
        if self._connector is not None:
            return self._connector(self._database_url)
        import psycopg

        return psycopg.connect(self._database_url, connect_timeout=5)

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                ensure_memory_schema(cursor)

    @staticmethod
    def _require_membership(cursor: Any, *, user_id: str, workspace_id: str) -> None:
        cursor.execute(
            """
            SELECT 1
            FROM vault_private.local_workspace_memberships m
            JOIN vault_private.local_users u ON u.user_id = m.user_id
            JOIN vault_private.local_workspaces w ON w.workspace_id = m.workspace_id
            WHERE m.user_id = %s AND m.workspace_id = %s AND m.status = 'active'
              AND u.status = 'active' AND w.status = 'active'
            """,
            (user_id, workspace_id),
        )
        if cursor.fetchone() is None:
            raise MemoryAuthorizationError("Active workspace membership is required.")

    @staticmethod
    def _scope_sql(alias: str = "m") -> str:
        return f"{alias}.workspace_id = %s AND ({alias}.visibility = 'workspace' OR {alias}.user_id = %s)"

    def append_transcript(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        entry_index: int,
        role: str,
        event_type: str,
        text_content: str,
        metadata: dict[str, object] | None = None,
        entry_id: str | None = None,
    ) -> TranscriptEntry:
        if role not in {"user", "assistant", "tool"}:
            raise MemoryContractError("invalid transcript role")
        text = text_content.strip()
        if entry_index < 0 or not text or len(text) > 16384:
            raise MemoryContractError("invalid transcript entry")
        identifier = entry_id or str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_transcript_entries
                      (entry_id, workspace_id, user_id, voice_session_id, entry_index,
                       role, event_type, text_content, metadata_json)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                    ON CONFLICT (workspace_id, user_id, voice_session_id, entry_index)
                    DO UPDATE SET entry_id = vault_private.vault_transcript_entries.entry_id
                    RETURNING entry_id, workspace_id, user_id, voice_session_id, entry_index,
                              role, event_type, text_content, created_at
                    """,
                    (
                        identifier, workspace_id, user_id, voice_session_id, entry_index,
                        role, event_type.strip(), text, json.dumps(metadata or {}, separators=(",", ":")),
                    ),
                )
                return TranscriptEntry(*cursor.fetchone())

    def append_transcript_next(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        role: str,
        event_type: str,
        text_content: str,
        metadata: dict[str, object] | None = None,
    ) -> TranscriptEntry:
        if role not in {"user", "assistant", "tool"}:
            raise MemoryContractError("invalid transcript role")
        text = text_content.strip()
        if not text or len(text) > 16384:
            raise MemoryContractError("invalid transcript entry")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    ("\x1f".join((workspace_id, user_id, voice_session_id, "transcript")),),
                )
                cursor.execute(
                    """
                    SELECT COALESCE(max(entry_index), -1) + 1
                    FROM vault_private.vault_transcript_entries
                    WHERE workspace_id=%s AND user_id=%s AND voice_session_id=%s
                    """,
                    (workspace_id, user_id, voice_session_id),
                )
                entry_index = int(cursor.fetchone()[0])
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_transcript_entries
                      (entry_id,workspace_id,user_id,voice_session_id,entry_index,
                       role,event_type,text_content,metadata_json)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                    RETURNING entry_id,workspace_id,user_id,voice_session_id,entry_index,
                              role,event_type,text_content,created_at
                    """,
                    (
                        str(uuid4()), workspace_id, user_id, voice_session_id, entry_index,
                        role, event_type.strip(), text,
                        json.dumps(metadata or {}, separators=(",", ":")),
                    ),
                )
                return TranscriptEntry(*cursor.fetchone())

    def transcript_entries(
        self, *, user_id: str, workspace_id: str, voice_session_id: str
    ) -> tuple[TranscriptEntry, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT entry_id, workspace_id, user_id, voice_session_id, entry_index,
                           role, event_type, text_content, created_at
                    FROM vault_private.vault_transcript_entries
                    WHERE workspace_id=%s AND user_id=%s AND voice_session_id=%s
                    ORDER BY entry_index
                    """,
                    (workspace_id, user_id, voice_session_id),
                )
                return tuple(TranscriptEntry(*row) for row in cursor.fetchall())

    def claim_ingestion(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        fingerprint: str,
        contract_version: int = REVIEWER_CONTRACT_VERSION,
        reviewer_model: str = "",
    ) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_memory_ingestions
                      (ingestion_id, workspace_id, user_id, voice_session_id,
                       reviewer_contract_version, transcript_fingerprint, state, reviewer_model)
                    VALUES (%s,%s,%s,%s,%s,%s,'running',%s)
                    ON CONFLICT (workspace_id, user_id, voice_session_id,
                                 reviewer_contract_version, transcript_fingerprint)
                    DO NOTHING
                    RETURNING ingestion_id
                    """,
                    (
                        str(uuid4()), workspace_id, user_id, voice_session_id,
                        contract_version, fingerprint, reviewer_model or None,
                    ),
                )
                return cursor.fetchone() is not None

    def ingestion_completed(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        fingerprint: str,
        contract_version: int = REVIEWER_CONTRACT_VERSION,
    ) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT 1 FROM vault_private.vault_memory_ingestions
                    WHERE workspace_id=%s AND user_id=%s AND voice_session_id=%s
                      AND reviewer_contract_version=%s AND transcript_fingerprint=%s
                      AND state='completed'
                    """,
                    (workspace_id, user_id, voice_session_id, contract_version, fingerprint),
                )
                return cursor.fetchone() is not None

    def complete_ingestion(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        fingerprint: str,
        candidate_count: int,
        stored_count: int,
        contract_version: int = REVIEWER_CONTRACT_VERSION,
    ) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    UPDATE vault_private.vault_memory_ingestions
                    SET state='completed',candidate_count=%s,stored_count=%s,
                        completed_at=now(),error_code=NULL
                    WHERE workspace_id=%s AND user_id=%s AND voice_session_id=%s
                      AND reviewer_contract_version=%s AND transcript_fingerprint=%s
                    """,
                    (
                        candidate_count, stored_count, workspace_id, user_id,
                        voice_session_id, contract_version, fingerprint,
                    ),
                )
                if cursor.rowcount != 1:
                    raise MemoryRepositoryError("Memory ingestion was not claimed.")

    def store_summary(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        summary_text: str,
        fingerprint: str,
        contract_version: int = REVIEWER_CONTRACT_VERSION,
    ) -> str:
        summary = summary_text.strip()
        if not summary:
            raise MemoryContractError("summary text is required")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                summary_id = str(uuid4())
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_session_summaries
                      (summary_id,workspace_id,user_id,voice_session_id,summary_text,
                       reviewer_contract_version,transcript_fingerprint)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (workspace_id,user_id,voice_session_id,
                                 reviewer_contract_version,transcript_fingerprint)
                    DO UPDATE SET summary_text=EXCLUDED.summary_text
                    RETURNING summary_id
                    """,
                    (
                        summary_id, workspace_id, user_id, voice_session_id,
                        summary, contract_version, fingerprint,
                    ),
                )
                return str(cursor.fetchone()[0])

    def session_summary(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        fingerprint: str,
        contract_version: int = REVIEWER_CONTRACT_VERSION,
    ) -> str | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT summary_text FROM vault_private.vault_session_summaries
                    WHERE workspace_id=%s AND user_id=%s AND voice_session_id=%s
                      AND reviewer_contract_version=%s AND transcript_fingerprint=%s
                    """,
                    (workspace_id, user_id, voice_session_id, contract_version, fingerprint),
                )
                row = cursor.fetchone()
                return str(row[0]) if row else None

    def previous_session_summary(
        self, *, user_id: str, workspace_id: str, exclude_voice_session_id: str
    ) -> str | None:
        """Return the most recent completed scoped summary before a new Voice session."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT summary_text
                    FROM vault_private.vault_session_summaries
                    WHERE workspace_id=%s AND user_id=%s AND voice_session_id<>%s
                    ORDER BY created_at DESC, summary_id DESC
                    LIMIT 1
                    """,
                    (workspace_id, user_id, exclude_voice_session_id),
                )
                row = cursor.fetchone()
                return str(row[0]) if row else None

    def reconcile_memory(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        candidate: MemoryCandidate,
        evidence: tuple[tuple[str | None, str, str, str], ...],
        contract_version: int = REVIEWER_CONTRACT_VERSION,
    ) -> MemoryRecord:
        item = candidate.validated()
        if not evidence:
            raise MemoryContractError("memory evidence is required")
        for _, _, authority, excerpt in evidence:
            if authority not in MEMORY_AUTHORITIES or not excerpt.strip():
                raise MemoryContractError("invalid memory evidence")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                canonical_lock = "\x1f".join(
                    (
                        workspace_id,
                        item.visibility,
                        user_id if item.visibility == "private" else "workspace",
                        item.subject_id,
                        item.domain,
                        item.memory_type,
                        item.memory_key,
                    )
                )
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (canonical_lock,),
                )
                owner_predicate = "AND user_id=%s" if item.visibility == "private" else ""
                owner_params: tuple[object, ...] = (user_id,) if item.visibility == "private" else ()
                cursor.execute(
                    f"""
                    SELECT * FROM vault_private.vault_memory_records
                    WHERE workspace_id=%s AND visibility=%s {owner_predicate}
                      AND subject_id=%s AND domain=%s AND memory_type=%s AND memory_key=%s
                      AND lifecycle_status IN ('active','conflicted')
                    ORDER BY updated_at DESC FOR UPDATE
                    """,
                    (
                        workspace_id, item.visibility, *owner_params, item.subject_id,
                        item.domain, item.memory_type, item.memory_key,
                    ),
                )
                current = cursor.fetchone()
                if current is None:
                    memory_id, version = str(uuid4()), 1
                    status = "conflicted" if item.intent == "conflict" else "active"
                    cursor.execute(
                        """
                        INSERT INTO vault_private.vault_memory_records
                          (memory_id,workspace_id,user_id,visibility,subject_id,domain,memory_type,
                           memory_key,content_text,source_authority,confidence,sensitivity,
                           lifecycle_status,current_version)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            memory_id, workspace_id, user_id, item.visibility, item.subject_id,
                            item.domain, item.memory_type, item.memory_key, item.content_text,
                            item.source_authority, item.confidence, item.sensitivity, status, version,
                        ),
                    )
                else:
                    memory_id = str(current[0])
                    version = int(current[13])
                    same_content = str(current[8]) == item.content_text
                    if same_content and item.intent not in {"correct", "conflict"}:
                        cursor.execute(
                            """
                            UPDATE vault_private.vault_memory_records
                            SET confidence=%s, source_authority=%s, updated_at=now()
                            WHERE memory_id=%s
                            """,
                            (item.confidence, item.source_authority, memory_id),
                        )
                    else:
                        version += 1
                        status = "active" if item.intent == "correct" else "conflicted"
                        cursor.execute(
                            """
                            UPDATE vault_private.vault_memory_records
                            SET content_text=%s,source_authority=%s,confidence=%s,sensitivity=%s,
                                lifecycle_status=%s,current_version=%s,updated_at=now()
                            WHERE memory_id=%s
                            """,
                            (
                                item.content_text, item.source_authority, item.confidence,
                                item.sensitivity, status, version, memory_id,
                            ),
                        )
                        cursor.execute(
                            "DELETE FROM vault_private.vault_memory_embeddings WHERE memory_id=%s",
                            (memory_id,),
                        )
                version_id = str(uuid4())
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_memory_record_versions
                      (version_id,memory_id,version_number,actor_user_id,intent,content_text,source_authority,
                       confidence,sensitivity,source_session_id,reviewer_contract_version)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (memory_id,version_number) DO NOTHING
                    RETURNING version_id
                    """,
                    (
                        version_id, memory_id, version, user_id, item.intent, item.content_text,
                        item.source_authority, item.confidence, item.sensitivity,
                        voice_session_id, contract_version,
                    ),
                )
                inserted = cursor.fetchone()
                if inserted is None:
                    cursor.execute(
                        """
                        SELECT version_id FROM vault_private.vault_memory_record_versions
                        WHERE memory_id=%s AND version_number=%s
                        """,
                        (memory_id, version),
                    )
                    version_id = str(cursor.fetchone()[0])
                for entry_id, kind, authority, excerpt in evidence:
                    cursor.execute(
                        """
                        INSERT INTO vault_private.vault_memory_evidence
                          (evidence_id,version_id,transcript_entry_id,evidence_kind,
                           source_authority,evidence_text)
                        VALUES (%s,%s,%s,%s,%s,%s)
                        """,
                        (str(uuid4()), version_id, entry_id, kind, authority, excerpt[:16384]),
                    )
                return self._memory_by_id_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id, memory_id=memory_id
                )

    def memory(self, *, user_id: str, workspace_id: str, memory_id: str) -> MemoryRecord:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                return self._memory_by_id_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id, memory_id=memory_id
                )

    def memory_evidence(
        self, *, user_id: str, workspace_id: str, memory_id: str
    ) -> tuple[dict[str, object], ...]:
        """Return evidence for the current scoped memory version only."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                memory = self._memory_by_id_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id, memory_id=memory_id
                )
                cursor.execute(
                    """
                    SELECT e.evidence_kind,e.source_authority,e.evidence_text,
                           e.transcript_entry_id
                    FROM vault_private.vault_memory_record_versions v
                    JOIN vault_private.vault_memory_evidence e ON e.version_id=v.version_id
                    WHERE v.memory_id=%s AND v.version_number=%s
                    ORDER BY e.evidence_id
                    """,
                    (memory.memory_id, memory.current_version),
                )
                return tuple({
                    "evidenceKind": str(row[0]), "sourceAuthority": str(row[1]),
                    "evidenceText": str(row[2]),
                    "transcriptEntryId": str(row[3]) if row[3] is not None else None,
                } for row in cursor.fetchall())

    def _memory_by_id_cursor(
        self, cursor: Any, *, user_id: str, workspace_id: str, memory_id: str
    ) -> MemoryRecord:
        cursor.execute(
            f"""
            SELECT m.memory_id,m.workspace_id,m.user_id,m.visibility,m.subject_id,m.domain,
                   m.memory_type,m.memory_key,m.content_text,m.source_authority,m.confidence,
                   m.sensitivity,m.lifecycle_status,m.current_version,m.created_at,m.updated_at
            FROM vault_private.vault_memory_records m
            JOIN vault_private.local_workspace_memberships membership
              ON membership.workspace_id=m.workspace_id AND membership.user_id=%s
             AND membership.status='active'
            WHERE m.memory_id=%s AND {self._scope_sql('m')}
            """,
            (user_id, memory_id, workspace_id, user_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise MemoryNotFoundError("Memory is unavailable in the active scope.")
        return MemoryRecord(*row)

    def profile_memories(
        self, *, user_id: str, workspace_id: str, limit: int = 8
    ) -> tuple[MemoryRecord, ...]:
        bounded = max(1, min(int(limit), 32))
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    f"""
                    SELECT m.memory_id,m.workspace_id,m.user_id,m.visibility,m.subject_id,m.domain,
                           m.memory_type,m.memory_key,m.content_text,m.source_authority,m.confidence,
                           m.sensitivity,m.lifecycle_status,m.current_version,m.created_at,m.updated_at
                    FROM vault_private.vault_memory_records m
                    WHERE {self._scope_sql('m')} AND m.lifecycle_status='active'
                      AND m.confidence IN ('medium','high') AND m.sensitivity='normal'
                    ORDER BY CASE m.domain WHEN 'identity' THEN 0 WHEN 'personal' THEN 1
                      WHEN 'relationship' THEN 2 WHEN 'environment' THEN 3
                      WHEN 'platform' THEN 4 WHEN 'project' THEN 5 ELSE 6 END,
                      m.updated_at DESC LIMIT %s
                    """,
                    (workspace_id, user_id, bounded),
                )
                return tuple(MemoryRecord(*row) for row in cursor.fetchall())

    def prepare_action(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        prepared_entry_index: int,
        action_kind: str,
        memory_id: str,
        proposed_content: str | None = None,
    ) -> str:
        if action_kind not in {"correct", "forget"}:
            raise MemoryContractError("unsupported memory action")
        content = proposed_content.strip() if proposed_content is not None else None
        if action_kind == "correct" and (not content or len(content) > 4096):
            raise MemoryContractError("correction content is required and bounded")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                self._memory_by_id_cursor(cursor, user_id=user_id, workspace_id=workspace_id, memory_id=memory_id)
                cursor.execute(
                    """
                    SELECT 1 FROM vault_private.vault_transcript_entries
                    WHERE workspace_id=%s AND user_id=%s AND voice_session_id=%s
                      AND entry_index=%s AND role='user'
                    """,
                    (workspace_id, user_id, voice_session_id, prepared_entry_index),
                )
                if cursor.fetchone() is None:
                    raise MemoryConfirmationError("Preparing user transcript entry is required.")
                action_id = str(uuid4())
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_memory_pending_actions
                      (action_id,workspace_id,user_id,voice_session_id,memory_id,action_kind,
                       proposed_content,prepared_entry_index)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        action_id, workspace_id, user_id, voice_session_id, memory_id,
                        action_kind, content, prepared_entry_index,
                    ),
                )
                return action_id

    def consume_action(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        action_id: str,
        confirmation_entry_index: int,
    ) -> PendingMemoryAction:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT action_kind,memory_id,proposed_content,prepared_entry_index
                    FROM vault_private.vault_memory_pending_actions
                    WHERE action_id=%s AND workspace_id=%s AND user_id=%s
                      AND voice_session_id=%s AND status='pending'
                    FOR UPDATE
                    """,
                    (action_id, workspace_id, user_id, voice_session_id),
                )
                action = cursor.fetchone()
                if action is None or confirmation_entry_index <= int(action[3]):
                    raise MemoryConfirmationError("A later same-session user confirmation is required.")
                cursor.execute(
                    """
                    SELECT entry_id,text_content FROM vault_private.vault_transcript_entries
                    WHERE workspace_id=%s AND user_id=%s AND voice_session_id=%s
                      AND entry_index=%s AND role='user'
                    """,
                    (workspace_id, user_id, voice_session_id, confirmation_entry_index),
                )
                confirmation = cursor.fetchone()
                if confirmation is None:
                    raise MemoryConfirmationError("A later same-session user confirmation is required.")
                cursor.execute(
                    """
                    UPDATE vault_private.vault_memory_pending_actions
                    SET status='consumed', consumed_at=now()
                    WHERE action_id=%s AND status='pending'
                    RETURNING action_id
                    """,
                    (action_id,),
                )
                if cursor.fetchone() is None:
                    raise MemoryConfirmationError("Memory action was already consumed.")
                return PendingMemoryAction(
                    action_id=action_id,
                    action_kind=str(action[0]),
                    memory_id=str(action[1]),
                    proposed_content=str(action[2]) if action[2] is not None else None,
                    confirmation_entry_id=str(confirmation[0]),
                    confirmation_text=str(confirmation[1]),
                )

    def delete_memory(self, *, user_id: str, workspace_id: str, memory_id: str) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                self._memory_by_id_cursor(cursor, user_id=user_id, workspace_id=workspace_id, memory_id=memory_id)
                cursor.execute(
                    f"DELETE FROM vault_private.vault_memory_records m WHERE m.memory_id=%s AND {self._scope_sql('m')} RETURNING m.memory_id",
                    (memory_id, workspace_id, user_id),
                )
                return cursor.fetchone() is not None

    def lexical_memories(
        self, *, user_id: str, workspace_id: str, query: str, limit: int = 25
    ) -> tuple[MemoryRecord, ...]:
        stop_words = {
            "and", "are", "for", "from", "has", "have", "how", "the", "this",
            "that", "was", "what", "when", "where", "which", "who", "with", "your",
        }
        terms = [
            term for term in re.findall(r"[a-z0-9]+", query.lower())
            if len(term) >= 3 and term not in stop_words
        ][:8]
        if not terms:
            return ()
        bounded = max(1, min(int(limit), 50))
        clauses = " OR ".join("lower(m.content_text) LIKE %s" for _ in terms)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    f"""
                    SELECT m.memory_id,m.workspace_id,m.user_id,m.visibility,m.subject_id,m.domain,
                           m.memory_type,m.memory_key,m.content_text,m.source_authority,m.confidence,
                           m.sensitivity,m.lifecycle_status,m.current_version,m.created_at,m.updated_at
                    FROM vault_private.vault_memory_records m
                    WHERE {self._scope_sql('m')} AND m.lifecycle_status='active'
                      AND ({clauses}) ORDER BY m.updated_at DESC LIMIT %s
                    """,
                    (workspace_id, user_id, *(f"%{term}%" for term in terms), bounded),
                )
                return tuple(MemoryRecord(*row) for row in cursor.fetchall())

    def store_embedding(
        self,
        *,
        user_id: str,
        workspace_id: str,
        memory_id: str,
        provider: str,
        model: str,
        embedding: list[float],
        content_text: str,
    ) -> None:
        if not provider.strip() or not model.strip() or not embedding:
            raise MemoryContractError("real embedding provider, model and vector are required")
        vector = tuple(float(value) for value in embedding)
        if any(value != value or abs(value) == float("inf") for value in vector):
            raise MemoryContractError("embedding contains a non-finite value")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                memory = self._memory_by_id_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id, memory_id=memory_id
                )
                if memory.content_text != content_text:
                    raise MemoryContractError("embedding content must match current memory content")
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_memory_embeddings
                      (memory_id,provider,model,dimensions,vector_json,embedding,content_fingerprint)
                    VALUES (%s,%s,%s,%s,%s::jsonb,%s::vector,%s)
                    ON CONFLICT (memory_id) DO UPDATE SET
                      provider=EXCLUDED.provider,model=EXCLUDED.model,
                      dimensions=EXCLUDED.dimensions,vector_json=EXCLUDED.vector_json,
                      embedding=EXCLUDED.embedding,
                      content_fingerprint=EXCLUDED.content_fingerprint,updated_at=now()
                    """,
                    (
                        memory_id, provider.strip(), model.strip(), len(vector),
                        json.dumps(vector, separators=(",", ":")),
                        "[" + ",".join(str(value) for value in vector) + "]",
                        sha256(content_text.encode("utf-8")).hexdigest(),
                    ),
                )

    def embeddings_for(
        self, *, user_id: str, workspace_id: str, model: str | None = None
    ) -> tuple[MemoryEmbedding, ...]:
        model_clause = "AND e.model=%s" if model is not None else ""
        params: tuple[object, ...] = (workspace_id, user_id, *((model,) if model is not None else ()))
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    f"""
                    SELECT e.memory_id,e.provider,e.model,e.dimensions,e.vector_json,e.content_fingerprint
                    FROM vault_private.vault_memory_embeddings e
                    JOIN vault_private.vault_memory_records m ON m.memory_id=e.memory_id
                    WHERE {self._scope_sql('m')} AND m.lifecycle_status='active' {model_clause}
                    """,
                    params,
                )
                results = []
                for row in cursor.fetchall():
                    raw = row[4] if isinstance(row[4], list) else json.loads(str(row[4]))
                    results.append(
                        MemoryEmbedding(
                            memory_id=str(row[0]), provider=str(row[1]), model=str(row[2]),
                            dimensions=int(row[3]), embedding=tuple(float(value) for value in raw),
                            content_fingerprint=str(row[5]),
                        )
                    )
                return tuple(results)

    def memories_missing_embeddings(
        self, *, user_id: str, workspace_id: str, model: str, limit: int = 256,
    ) -> tuple[MemoryRecord, ...]:
        bounded = max(1, min(int(limit), 1000))
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    f"""
                    SELECT m.memory_id,m.workspace_id,m.user_id,m.visibility,m.subject_id,m.domain,
                           m.memory_type,m.memory_key,m.content_text,m.source_authority,m.confidence,
                           m.sensitivity,m.lifecycle_status,m.current_version,m.created_at,m.updated_at
                    FROM vault_private.vault_memory_records m
                    LEFT JOIN vault_private.vault_memory_embeddings e ON e.memory_id=m.memory_id
                    WHERE {self._scope_sql('m')} AND m.lifecycle_status='active'
                      AND (e.memory_id IS NULL OR e.model<>%s)
                    ORDER BY m.updated_at ASC LIMIT %s
                    """,
                    (workspace_id, user_id, model, bounded),
                )
                return tuple(MemoryRecord(*row) for row in cursor.fetchall())
