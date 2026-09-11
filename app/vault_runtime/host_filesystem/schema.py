from __future__ import annotations

from typing import Protocol


class Cursor(Protocol):
    def execute(self, query: str, params: object | None = None) -> object: ...


SCHEMA_STATEMENTS = (
    "CREATE SCHEMA IF NOT EXISTS vault_private",
    """
    CREATE TABLE IF NOT EXISTS vault_private.host_filesystem_settings (
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      enabled boolean NOT NULL DEFAULT false,
      helper_base_url text NOT NULL DEFAULT 'http://host.docker.internal:8767',
      updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (user_id, workspace_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.host_filesystem_integrations (
      integration_id text PRIMARY KEY,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      display_name text NOT NULL,
      adapter_kind text NOT NULL DEFAULT 'host-helper',
      token_hash text NOT NULL UNIQUE,
      outbound_credential_enc text,
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
      created_at timestamptz NOT NULL DEFAULT now(),
      revoked_at timestamptz
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_host_filesystem_integrations_scope
    ON vault_private.host_filesystem_integrations (workspace_id, user_id, status)
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.host_filesystem_pairings (
      pairing_id text PRIMARY KEY,
      pairing_code text NOT NULL UNIQUE,
      poll_token_hash text NOT NULL,
      runtime_token_hash text NOT NULL,
      display_name text NOT NULL,
      adapter_kind text NOT NULL DEFAULT 'host-helper',
      outbound_credential_enc text,
      status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'expired')),
      integration_id text REFERENCES vault_private.host_filesystem_integrations(integration_id) ON DELETE SET NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      expires_at timestamptz NOT NULL,
      approved_at timestamptz
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_host_filesystem_pairings_expiry
    ON vault_private.host_filesystem_pairings (status, expires_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.host_filesystem_mounts (
      mount_id text PRIMARY KEY,
      integration_id text NOT NULL REFERENCES vault_private.host_filesystem_integrations(integration_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      mount_name text NOT NULL,
      permission text NOT NULL CHECK (permission IN ('read', 'write')),
      source text NOT NULL DEFAULT 'browser' CHECK (source IN ('browser', 'helper')),
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
      created_at timestamptz NOT NULL DEFAULT now(),
      revoked_at timestamptz,
      UNIQUE (user_id, workspace_id, mount_name)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_host_filesystem_mounts_scope
    ON vault_private.host_filesystem_mounts (workspace_id, user_id, status)
    """,
    """
    ALTER TABLE vault_private.host_filesystem_integrations
      ADD COLUMN IF NOT EXISTS outbound_credential_enc text
    """,
    """
    ALTER TABLE vault_private.host_filesystem_pairings
      ADD COLUMN IF NOT EXISTS outbound_credential_enc text
    """,
    """
    ALTER TABLE vault_private.host_filesystem_mounts
      ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'browser'
    """,
)


def ensure_host_filesystem_schema(cursor: Cursor) -> None:
    for statement in SCHEMA_STATEMENTS:
        cursor.execute(statement)
