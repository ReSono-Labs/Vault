from __future__ import annotations

from typing import Protocol


class Cursor(Protocol):
    def execute(self, query: str, params: object | None = None) -> object: ...


SCHEMA_STATEMENTS = (
    "CREATE SCHEMA IF NOT EXISTS vault_private",
    """
    CREATE TABLE IF NOT EXISTS vault_private.external_memory_integrations (
      integration_id text PRIMARY KEY,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      display_name text NOT NULL,
      adapter_kind text NOT NULL,
      token_hash text NOT NULL UNIQUE,
      grants_json jsonb NOT NULL,
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
      created_at timestamptz NOT NULL DEFAULT now(),
      revoked_at timestamptz
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_external_memory_integrations_scope
    ON vault_private.external_memory_integrations (workspace_id, user_id, status)
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.external_memory_pairings (
      pairing_id text PRIMARY KEY,
      pairing_code text NOT NULL UNIQUE,
      poll_token_hash text NOT NULL,
      runtime_token_hash text NOT NULL,
      display_name text NOT NULL,
      adapter_kind text NOT NULL,
      grants_json jsonb NOT NULL,
      status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'expired')),
      integration_id text REFERENCES vault_private.external_memory_integrations(integration_id) ON DELETE SET NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      expires_at timestamptz NOT NULL,
      approved_at timestamptz
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_external_memory_pairings_expiry
    ON vault_private.external_memory_pairings (status, expires_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.external_memory_requests (
      integration_id text NOT NULL REFERENCES vault_private.external_memory_integrations(integration_id) ON DELETE CASCADE,
      request_id text NOT NULL,
      operation text NOT NULL CHECK (operation IN ('search', 'propose')),
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (integration_id, request_id)
    )
    """,
    """
    ALTER TABLE vault_private.external_memory_requests
      DROP CONSTRAINT IF EXISTS external_memory_requests_operation_check
    """,
    """
    ALTER TABLE vault_private.external_memory_requests
      ADD CONSTRAINT external_memory_requests_operation_check
      CHECK (operation IN ('search', 'propose', 'correct', 'forget'))
    """,
)


def ensure_external_memory_schema(cursor: Cursor) -> None:
    for statement in SCHEMA_STATEMENTS:
        cursor.execute(statement)
