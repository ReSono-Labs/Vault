from __future__ import annotations

from hashlib import sha256
from typing import Protocol


class Cursor(Protocol):
    def execute(self, query: str, params: object | None = None) -> object: ...


SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS vault_private.vault_a2a_connections (
      connection_id text PRIMARY KEY,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      display_name text NOT NULL,
      card_url text NOT NULL,
      rpc_url text NOT NULL,
      agent_card jsonb NOT NULL,
      credential_nonce bytea,
      credential_ciphertext bytea,
      enabled boolean NOT NULL DEFAULT true,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )""",
    """CREATE INDEX IF NOT EXISTS ix_vault_a2a_connections_scope
       ON vault_private.vault_a2a_connections(workspace_id,user_id,created_at)""",
    """CREATE TABLE IF NOT EXISTS vault_private.vault_a2a_conversations (
      connection_id text NOT NULL REFERENCES vault_private.vault_a2a_connections(connection_id) ON DELETE CASCADE,
      user_id text NOT NULL,
      workspace_id text NOT NULL,
      owner_kind text NOT NULL CHECK (owner_kind IN ('voice','background')),
      owner_id text NOT NULL,
      context_id text NOT NULL,
      updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(connection_id,user_id,workspace_id,owner_kind,owner_id)
    )""",
    """CREATE TABLE IF NOT EXISTS vault_private.vault_a2a_tasks (
      task_record_id text PRIMARY KEY,
      connection_id text NOT NULL REFERENCES vault_private.vault_a2a_connections(connection_id) ON DELETE CASCADE,
      user_id text NOT NULL,
      workspace_id text NOT NULL,
      owner_kind text NOT NULL CHECK (owner_kind IN ('voice','background')),
      owner_id text NOT NULL,
      remote_task_id text,
      context_id text NOT NULL,
      state text NOT NULL,
      summary text NOT NULL DEFAULT '',
      issue text,
      notified boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      completed_at timestamptz
    )""",
    """CREATE INDEX IF NOT EXISTS ix_vault_a2a_tasks_scope_updated
       ON vault_private.vault_a2a_tasks(workspace_id,user_id,updated_at DESC)""",
)

SCHEMA_FINGERPRINT = sha256("\n".join(SCHEMA_STATEMENTS).encode()).hexdigest()


def ensure_a2a_schema(cursor: Cursor) -> None:
    for statement in SCHEMA_STATEMENTS:
        cursor.execute(statement)
    cursor.execute(
        """INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
           VALUES (%s,%s) ON CONFLICT(schema_key) DO UPDATE SET
           schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()""",
        ("agent_network_a2a_v1", SCHEMA_FINGERPRINT),
    )
