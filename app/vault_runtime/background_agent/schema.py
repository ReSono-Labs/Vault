from __future__ import annotations

from hashlib import sha256
from typing import Protocol


class Cursor(Protocol):
    def execute(self, query: str, params: object | None = None) -> object: ...


SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_background_runs (
      run_id text PRIMARY KEY,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      local_session_id text NOT NULL REFERENCES vault_private.local_sessions(session_id) ON DELETE CASCADE,
      request_json jsonb NOT NULL,
      state text NOT NULL CHECK (state IN ('accepted','queued','running','reviewing','repairing','completed','failed','cancelled')),
      cancellation_requested boolean NOT NULL DEFAULT false,
      output_json jsonb,
      failure_code text,
      failure_message text,
      model_turns integer NOT NULL DEFAULT 0 CHECK (model_turns >= 0),
      tool_calls integer NOT NULL DEFAULT 0 CHECK (tool_calls >= 0),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      completed_at timestamptz
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_background_runs_scope_created
    ON vault_private.vault_background_runs (workspace_id,user_id,created_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_background_run_events (
      run_id text NOT NULL REFERENCES vault_private.vault_background_runs(run_id) ON DELETE CASCADE,
      event_index integer NOT NULL CHECK (event_index >= 0),
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      event_type text NOT NULL,
      state text NOT NULL CHECK (state IN ('accepted','queued','running','reviewing','repairing','completed','failed','cancelled')),
      detail_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (run_id,event_index)
    )
    """,
)

SCHEMA_FINGERPRINT = sha256("\n".join(SCHEMA_STATEMENTS).encode("utf-8")).hexdigest()


def ensure_background_schema(cursor: Cursor) -> None:
    for statement in SCHEMA_STATEMENTS:
        cursor.execute(statement)
    cursor.execute(
        """
        INSERT INTO vault_private.local_schema_metadata (schema_key,schema_fingerprint)
        VALUES (%s,%s) ON CONFLICT (schema_key) DO UPDATE SET
          schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
        """,
        ("background_agent_v1", SCHEMA_FINGERPRINT),
    )
