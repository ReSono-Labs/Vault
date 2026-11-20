from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from app.vault_runtime.folders.errors import FolderInvalidRequestError, FolderUnavailableError


class Cursor(Protocol):
    def execute(self, query: str, params: object | None = None) -> object: ...


SCHEMA_STATEMENTS = (
    "CREATE SCHEMA IF NOT EXISTS vault_private",
    # Vault-wide settings the master account controls (one row per key).
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_settings (
      setting_key text PRIMARY KEY,
      value jsonb NOT NULL,
      updated_by text REFERENCES vault_private.local_users(user_id) ON DELETE SET NULL,
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    # Every command an agent asked to run: the approval state and the outcome (audit trail).
    """
    CREATE TABLE IF NOT EXISTS vault_private.command_requests (
      request_id text PRIMARY KEY,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL,
      agent text NOT NULL CHECK (agent IN ('chat', 'background')),
      conversation_id text,
      directory text NOT NULL,
      command text NOT NULL,
      state text NOT NULL CHECK (state IN ('pending', 'approved', 'denied', 'running', 'completed', 'expired', 'failed')),
      outcome jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      decided_at timestamptz,
      completed_at timestamptz,
      expires_at timestamptz NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_command_requests_conversation
    ON vault_private.command_requests (user_id, conversation_id, state)
    """,
)

APPROVAL_WINDOW = timedelta(minutes=15)
_COLUMNS = ("request_id, user_id, workspace_id, agent, conversation_id, directory, command, state, outcome, "
            "created_at, decided_at, completed_at, expires_at")


@dataclass(frozen=True, slots=True)
class CommandRequest:
    request_id: str
    user_id: str
    workspace_id: str
    agent: str
    conversation_id: str | None
    directory: str
    command: str
    state: str
    outcome: dict[str, Any] | None
    created_at: datetime
    decided_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime


def _row(row: Any) -> CommandRequest:
    outcome = row[8]
    if isinstance(outcome, str):
        outcome = json.loads(outcome)
    return CommandRequest(*row[:8], outcome, *row[9:])


class CommandRepository:
    def __init__(
        self, *, database_url: str, connector: Callable[..., AbstractContextManager[Any]] | None = None,
    ) -> None:
        self._database_url = database_url
        self._connector = connector

    def _connect(self):
        if self._connector is not None:
            return self._connector(self._database_url)
        import psycopg
        return psycopg.connect(self._database_url, connect_timeout=5)

    def ensure_schema(self) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            for statement in SCHEMA_STATEMENTS:
                cursor.execute(statement)

    # Settings

    def get_setting(self, key: str) -> Any:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT value FROM vault_private.vault_settings WHERE setting_key=%s", (key,))
            row = cursor.fetchone()
            if row is None:
                return None
            return json.loads(row[0]) if isinstance(row[0], str) else row[0]

    def set_setting(self, key: str, value: Any, *, updated_by: str) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO vault_private.vault_settings (setting_key, value, updated_by)
                   VALUES (%s, %s::jsonb, %s)
                   ON CONFLICT (setting_key) DO UPDATE
                   SET value=EXCLUDED.value, updated_by=EXCLUDED.updated_by, updated_at=now()""",
                (key, json.dumps(value), updated_by),
            )

    # Requests

    def create(
        self, *, user_id: str, workspace_id: str, agent: str, conversation_id: str | None,
        directory: str, command: str, state: str,
    ) -> CommandRequest:
        now = datetime.now(UTC)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""INSERT INTO vault_private.command_requests
                    (request_id, user_id, workspace_id, agent, conversation_id, directory, command, state, expires_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING {_COLUMNS}""",
                (str(uuid4()), user_id, workspace_id, agent, conversation_id, directory, command, state,
                 now + APPROVAL_WINDOW),
            )
            return _row(cursor.fetchone())

    def get(self, *, user_id: str, request_id: str) -> CommandRequest | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_COLUMNS} FROM vault_private.command_requests WHERE user_id=%s AND request_id=%s",
                (user_id, request_id),
            )
            row = cursor.fetchone()
            return _row(row) if row else None

    def pending_for_conversation(self, *, user_id: str, conversation_id: str) -> list[CommandRequest]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""UPDATE vault_private.command_requests SET state='expired'
                    WHERE user_id=%s AND conversation_id=%s AND state IN ('pending','approved') AND expires_at < now()""",
                (user_id, conversation_id),
            )
            cursor.execute(
                f"""SELECT {_COLUMNS} FROM vault_private.command_requests
                    WHERE user_id=%s AND conversation_id=%s AND state IN ('pending','approved')
                    ORDER BY created_at""",
                (user_id, conversation_id),
            )
            return [_row(row) for row in cursor.fetchall()]

    def decide(self, *, user_id: str, request_id: str, approve: bool) -> CommandRequest:
        """The person's decision, from an authenticated click. Only pending, unexpired requests."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""UPDATE vault_private.command_requests
                    SET state=%s, decided_at=now()
                    WHERE user_id=%s AND request_id=%s AND state='pending' AND expires_at >= now()
                    RETURNING {_COLUMNS}""",
                ("approved" if approve else "denied", user_id, request_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise FolderUnavailableError("That command request is no longer waiting for a decision.")
            return _row(row)

    def claim_approved(self, *, user_id: str, request_id: str, conversation_id: str) -> CommandRequest:
        """Atomically move an approved request to running, so it can run once."""
        with self._connect() as connection, connection.cursor() as cursor:
            # A Link owner approval (background actions table) also counts; Vault may run without it.
            cursor.execute("SELECT to_regclass('vault_private.vault_background_actions') IS NOT NULL")
            owner_approvals = bool(cursor.fetchone()[0])
            owner_clause = """OR (
                          state='pending'
                          AND EXISTS (
                            SELECT 1 FROM vault_private.vault_background_actions a
                            WHERE a.user_id=%s AND a.workspace_id=vault_private.command_requests.workspace_id
                              AND a.kind='owner_approval' AND a.domain_ref=%s AND a.state='executing'
                          )
                        )""" if owner_approvals else ""
            cursor.execute(
                f"""UPDATE vault_private.command_requests SET state='running', decided_at=COALESCE(decided_at, now())
                    WHERE user_id=%s AND request_id=%s AND conversation_id=%s
                      AND (state='approved' {owner_clause})
                      AND expires_at >= now()
                    RETURNING {_COLUMNS}""",
                (user_id, request_id, conversation_id, *((user_id, request_id) if owner_approvals else ())),
            )
            row = cursor.fetchone()
            if row is None:
                current = self.get(user_id=user_id, request_id=request_id)
                if current is not None and current.state == "pending":
                    raise FolderInvalidRequestError(
                        "The person hasn't approved this command yet. Ask them to click Run in the chat."
                    )
                if current is not None and current.state == "denied":
                    raise FolderInvalidRequestError("The person chose not to run this command. Don't run it.")
                raise FolderUnavailableError("That command can't run: it was already used, changed or expired.")
            return _row(row)

    def finish(self, *, request_id: str, state: str, outcome: dict[str, Any]) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE vault_private.command_requests
                   SET state=%s, outcome=%s::jsonb, completed_at=now() WHERE request_id=%s""",
                (state, json.dumps(outcome), request_id),
            )
