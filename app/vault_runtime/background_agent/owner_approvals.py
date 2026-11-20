"""One owner-approval system for Vault Chat and Voice (plan: 2026-11-17-vault-owner-approvals.md).

An agent's tool call that needs the owner's approval asks here and waits. The question is shown on
the owner's Link phone (the same popup Link shows for Hermes, OpenClaw and Codex) and on the Vault
website. Every approval belongs to exactly one account; only that account answers it. Two choices:
allow once or deny. No answer before the deadline, or the turn/call ending first, is deny. Vault
never answers for the owner; a model flag or tool result is never an approval.

The records are Task 4's prepared actions (`vault_background_actions`, kind `owner_approval`) and
decisions go through `BackgroundActions.decide`, so there is one decision path for interactive and
background approvals.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from .actions import BackgroundActions
from .authority import validate_approval_channel
from .coordination_contracts import ApprovalDecision, OwnerScope, PreparedAction
from .coordination_repository import CoordinationRepository, _json
from .errors import BackgroundRunAuthorizationError, BackgroundRunConflictError

KIND = "owner_approval"
CHOICES = ("allow_once", "deny")
TTL_SECONDS = 300           # Link's limit: no answer within 5 minutes is deny
MAX_DETAIL_LINES = 12
MAX_LINE = 300


@dataclass(frozen=True, slots=True)
class ApprovalOrigin:
    """Where the question was asked: one Chat turn or one Voice call, and the tool call in it."""
    tool_call_id: str
    conversation_id: str | None = None
    turn_id: str | None = None
    voice_session_id: str | None = None

    def __post_init__(self) -> None:
        if not self.tool_call_id or (self.turn_id is None) == (self.voice_session_id is None) \
                or (self.turn_id is None) != (self.conversation_id is None):
            raise ValueError("An approval belongs to exactly one Chat turn or one Voice call")

    @property
    def key(self) -> str:
        where = f"turn:{self.turn_id}" if self.turn_id else f"voice:{self.voice_session_id}"
        return f"{KIND}:{where}:{self.tool_call_id}"


def _owner(principal) -> OwnerScope:
    return OwnerScope(principal.user_id, principal.workspace_id)


class OwnerApprovals:
    def __init__(self, *, database_url: str, actions: BackgroundActions | None = None,
                 ttl_seconds: int = TTL_SECONDS, poll_seconds: float = 0.5,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if not 0 < ttl_seconds <= TTL_SECONDS or poll_seconds <= 0:
            raise ValueError("Approvals wait at most five minutes")
        self._repo = CoordinationRepository(database_url=database_url)
        self._actions = actions or BackgroundActions(database_url=database_url)
        self._ttl, self._poll, self._sleep = ttl_seconds, poll_seconds, sleep

    # ── asking ────────────────────────────────────────────────────────────────
    def ask(self, principal, *, origin: ApprovalOrigin, tool_name: str, tool_arguments: dict, title: str,
            detail_lines: list[str], domain_ref: str | None = None, resource_version: str | None = None,
            deadline: datetime | None = None) -> PreparedAction:
        """Record the question for this account (one waiting per account). The same tool call asking
        again gets the same approval back."""
        if not isinstance(tool_name, str) or not tool_name or not isinstance(tool_arguments, dict) or "approve" in tool_arguments:
            raise ValueError("An approval needs the exact tool call, without an approval flag")
        title = str(title or "").strip()[:200]
        lines = [str(line)[:MAX_LINE] for line in (detail_lines or [])][:MAX_DETAIL_LINES]
        if not title:
            raise ValueError("An approval needs a title")
        arguments = _json({"tool": tool_name, "tool_arguments": tool_arguments, "summary": "\n".join(lines)})
        fingerprint = BackgroundActions._hash(KIND, arguments, resource_version, domain_ref)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=self._ttl)
        if deadline is not None:
            expires = min(expires, deadline)
        owner = _owner(principal)
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._authority(cursor, principal)
            # A question nobody answered in time no longer blocks this account.
            cursor.execute("""UPDATE vault_private.vault_background_actions SET state='expired',updated_at=now()
                WHERE user_id=%s AND workspace_id=%s AND kind=%s AND state='pending' AND expires_at<=now()""",
                (owner.user_id, owner.workspace_id, KIND))
        try:
            with self._repo._connect() as connection, connection.cursor() as cursor:
                cursor.execute("""INSERT INTO vault_private.vault_background_actions
                    (action_id,user_id,workspace_id,kind,action_hash,arguments_json,domain_ref,resource_version,title,detail,
                     detail_lines,expires_at,operation_key,origin_conversation_id,origin_turn_id,origin_voice_session_id,
                     origin_tool_call_id,origin_json)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(user_id,workspace_id,operation_key) DO NOTHING RETURNING *""",
                    (str(uuid4()), owner.user_id, owner.workspace_id, KIND, fingerprint, Jsonb(arguments), domain_ref,
                     resource_version, title, "\n".join(lines)[:2048], Jsonb(lines), expires, origin.key,
                     origin.conversation_id, origin.turn_id, origin.voice_session_id, origin.tool_call_id,
                     Jsonb({"session_id": principal.session_id})))
                row = cursor.fetchone()
                if row is None:
                    cursor.execute("""SELECT * FROM vault_private.vault_background_actions
                        WHERE user_id=%s AND workspace_id=%s AND operation_key=%s""", (owner.user_id, owner.workspace_id, origin.key))
                    row = cursor.fetchone()
        except psycopg.errors.UniqueViolation as exc:   # another question of this account is waiting
            raise BackgroundRunConflictError("Already waiting for your answer to another request") from exc
        return PreparedAction(row["action_id"], row["action_hash"], None, KIND, row["title"], row["detail"], row["expires_at"])

    # ── what the phone and website show ───────────────────────────────────────
    def pending(self, principal, *, turn_id: str | None = None, voice_session_id: str | None = None) -> dict | None:
        """The waiting question of this account's turn or call, in the Link agent-contract shape."""
        if (turn_id is None) == (voice_session_id is None):
            raise ValueError("Ask about one turn or one call")
        column = "origin_turn_id" if turn_id else "origin_voice_session_id"
        with self._repo._connect() as connection, connection.cursor() as cursor:
            cursor.execute(f"""SELECT * FROM vault_private.vault_background_actions
                WHERE user_id=%s AND workspace_id=%s AND kind=%s AND state='pending' AND expires_at>now() AND {column}=%s
                ORDER BY created_at DESC LIMIT 1""", (principal.user_id, principal.workspace_id, KIND, turn_id or voice_session_id))
            row = cursor.fetchone()
        return None if row is None else self._shape(row)

    def waiting(self, principal) -> list[dict]:
        """This account's waiting questions (the website's list)."""
        with self._repo._connect() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM vault_private.vault_background_actions
                WHERE user_id=%s AND workspace_id=%s AND kind=%s AND state='pending' AND expires_at>now()
                ORDER BY created_at""", (principal.user_id, principal.workspace_id, KIND))
            return [{**self._shape(row), "conversationId": row["origin_conversation_id"],
                     "voiceSessionId": row["origin_voice_session_id"]} for row in cursor.fetchall()]

    @staticmethod
    def _shape(row) -> dict:
        return {"id": row["action_id"], "title": row["title"], "detail": list(row["detail_lines"] or []),
                "choices": list(CHOICES), "expires_at": int(row["expires_at"].timestamp())}

    # ── answering ─────────────────────────────────────────────────────────────
    def answer(self, principal, action_id: str, choice: str, *, channel: str,
               turn_id: str | None = None, voice_session_id: str | None = None) -> str:
        """The account's own answer from the website or its paired phone. Returns approved, denied or
        expired. The decision id is derived from the channel and the approval, so a repeated answer
        from the same place counts once; a different answer after the first is a conflict."""
        if choice not in CHOICES:
            raise ValueError("The choices are allow_once and deny")
        row = self._row(principal, action_id)
        # An answer that names its turn or call must be for that turn or call.
        if (turn_id is not None and row["origin_turn_id"] != turn_id) or \
                (voice_session_id is not None and row["origin_voice_session_id"] != voice_session_id):
            raise BackgroundRunAuthorizationError("Approval belongs to another turn or call")
        if row["state"] == "expired" or (row["state"] == "pending" and row["expires_at"] <= datetime.now(timezone.utc)):
            self._expire(principal, action_id)
            return "expired"
        decision = ApprovalDecision(action_id, row["action_hash"], choice, principal.user_id, principal.workspace_id,
                                    channel, principal.session_id, f"{channel}:{action_id}")
        try:
            self._actions.decide(principal, decision)
        except BackgroundRunAuthorizationError:
            # The deadline passed between reading the question and recording the answer.
            current = self._row(principal, action_id)
            if current["state"] in {"pending", "expired"} and current["expires_at"] <= datetime.now(timezone.utc):
                self._expire(principal, action_id)
                return "expired"
            raise
        return "approved" if choice == "allow_once" else "denied"

    # ── waiting (inside the tool call) ────────────────────────────────────────
    def wait(self, principal, action_id: str, *, cancelled: Callable[[], bool] = lambda: False) -> str:
        """Block until answered: allowed, denied, expired (no answer in time) or cancelled (the turn or
        call ended first; recorded as expired, which is deny). Polls with short connections; holds no
        transaction or lock while waiting."""
        while True:
            row = self._row(principal, action_id)
            state = row["state"]
            if state in {"approved", "executing", "completed", "failed", "unknown"}:
                return "allowed"
            if state == "denied":
                return "denied"
            if state == "expired":
                return "expired"
            if cancelled():
                if self._expire(principal, action_id):
                    return "cancelled"
                continue                        # answered at the same moment: read it again
            if row["expires_at"] <= datetime.now(timezone.utc):
                if self._expire(principal, action_id):
                    return "expired"
                continue
            self._sleep(self._poll)

    # ── running the approved tool call ────────────────────────────────────────
    def consume(self, principal, action_id: str) -> dict:
        """Approved → executing, once. The answering channel must still be valid (a phone unpaired
        after its allow stops the tool)."""
        owner = _owner(principal)
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._authority(cursor, principal)
            row = self._locked(cursor, principal, action_id)
            if row["state"] != "approved":
                if row["state"] in {"executing", "completed", "failed", "unknown"}:
                    raise BackgroundRunConflictError("This approval was already used")
                raise BackgroundRunAuthorizationError("The owner has not approved this")
            validate_approval_channel(cursor, owner, row["channel"], row["channel_generation"])
            cursor.execute("UPDATE vault_private.vault_background_actions SET state='executing',updated_at=now() WHERE action_id=%s",
                           (action_id,))
            return row | {"state": "executing"}

    def finish(self, principal, action_id: str, outcome: dict) -> None:
        if not isinstance(outcome, dict) or outcome.get("state") not in {"completed", "failed", "unknown"}:
            raise ValueError("A terminal outcome is required")
        with self._repo._connect() as connection, connection.cursor() as cursor:
            row = self._locked(cursor, principal, action_id)
            if row["state"] != "executing":
                raise BackgroundRunConflictError("This approval is not running")
            cursor.execute("UPDATE vault_private.vault_background_actions SET state=%s,receipt_json=%s,updated_at=now() WHERE action_id=%s",
                           (outcome["state"], Jsonb(_json(outcome)), action_id))

    def expire_all_waiting(self) -> int:
        """At startup: questions whose tool call ended with the previous process are deny."""
        with self._repo._connect() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE vault_private.vault_background_actions SET state='expired',updated_at=now()
                WHERE kind=%s AND state='pending'""", (KIND,))
            return cursor.rowcount

    # ── helpers ───────────────────────────────────────────────────────────────
    def _authority(self, cursor, principal) -> None:
        owner = _owner(principal)
        self._repo._owner(cursor, owner)
        self._repo._authority(cursor, owner, principal.session_id, None)

    def _row(self, principal, action_id):
        with self._repo._connect() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM vault_private.vault_background_actions
                WHERE user_id=%s AND workspace_id=%s AND action_id=%s AND kind=%s""",
                (principal.user_id, principal.workspace_id, action_id, KIND))
            row = cursor.fetchone()
        if row is None:
            raise BackgroundRunAuthorizationError("Approval unavailable")
        return row

    def _locked(self, cursor, principal, action_id):
        cursor.execute("""SELECT * FROM vault_private.vault_background_actions
            WHERE user_id=%s AND workspace_id=%s AND action_id=%s AND kind=%s FOR UPDATE""",
            (principal.user_id, principal.workspace_id, action_id, KIND))
        row = cursor.fetchone()
        if row is None:
            raise BackgroundRunAuthorizationError("Approval unavailable")
        return row

    def _expire(self, principal, action_id) -> bool:
        with self._repo._connect() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE vault_private.vault_background_actions SET state='expired',updated_at=now()
                WHERE user_id=%s AND workspace_id=%s AND action_id=%s AND kind=%s AND state='pending'""",
                (principal.user_id, principal.workspace_id, action_id, KIND))
            return cursor.rowcount == 1
