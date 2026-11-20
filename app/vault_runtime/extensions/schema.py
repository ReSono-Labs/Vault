from __future__ import annotations

from hashlib import sha256
from typing import Protocol


class Cursor(Protocol):
    def execute(self, query: str, params: object | None = None) -> object: ...


SCHEMA_STATEMENTS: tuple[str, ...] = (
    "CREATE SCHEMA IF NOT EXISTS vault_private",
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_extensions (
      extension_id text PRIMARY KEY,
      kind text NOT NULL CHECK (kind IN ('plugin','skill','mcp')),
      identity text NOT NULL,
      display_name text NOT NULL,
      version text,
      description text,
      content_hash text NOT NULL,
      state text NOT NULL CHECK (state IN ('enabled','disabled','removed')),
      installed_by_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      installed_in_workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      previous_content_hash text,
      configuration_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      removed_at timestamptz,
      UNIQUE (installed_in_workspace_id, kind, identity)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_extension_components (
      component_id text PRIMARY KEY,
      extension_id text NOT NULL REFERENCES vault_private.vault_extensions(extension_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      component_kind text NOT NULL CHECK (component_kind IN ('skill','mcp')),
      component_name text NOT NULL,
      component_hash text NOT NULL,
      UNIQUE (workspace_id, component_kind, component_name),
      UNIQUE (extension_id, component_kind, component_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_extension_grants (
      grant_id text PRIMARY KEY,
      extension_id text NOT NULL REFERENCES vault_private.vault_extensions(extension_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      agent_kind text NOT NULL CHECK (agent_kind IN ('voice','background')),
      capability_name text NOT NULL DEFAULT '',
      enabled boolean NOT NULL DEFAULT true,
      effect_class text CHECK (effect_class IS NULL OR effect_class IN ('read','write','delete')),
      granted_by_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (extension_id, user_id, workspace_id, agent_kind, capability_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_mcp_tools (
      extension_id text NOT NULL REFERENCES vault_private.vault_extensions(extension_id) ON DELETE CASCADE,
      tool_name text NOT NULL,
      title text,
      description text NOT NULL,
      input_schema_json jsonb NOT NULL,
      output_schema_json jsonb,
      discovery_hash text NOT NULL,
      discovered_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (extension_id, tool_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_extension_events (
      event_id text PRIMARY KEY,
      extension_id text,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      actor_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      event_type text NOT NULL,
      detail_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_extension_secrets (
      extension_id text NOT NULL REFERENCES vault_private.vault_extensions(extension_id) ON DELETE CASCADE,
      secret_name text NOT NULL,
      nonce bytea NOT NULL,
      ciphertext bytea NOT NULL,
      changed_by_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (extension_id, secret_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_extension_runtime_settings (
      setting_key text PRIMARY KEY,
      enabled boolean NOT NULL,
      changed_by_user_id text REFERENCES vault_private.local_users(user_id) ON DELETE SET NULL,
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    INSERT INTO vault_private.vault_extension_runtime_settings (setting_key, enabled)
    VALUES ('third_party_extensions', false)
    ON CONFLICT (setting_key) DO NOTHING
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_extensions_scope_state
    ON vault_private.vault_extensions (installed_in_workspace_id, kind, state)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_extension_grants_scope
    ON vault_private.vault_extension_grants (user_id, workspace_id, agent_kind, enabled)
    """,
)

SCHEMA_FINGERPRINT = sha256("\n".join(SCHEMA_STATEMENTS).encode()).hexdigest()


def ensure_extension_schema(cursor: Cursor) -> None:
    for statement in SCHEMA_STATEMENTS:
        cursor.execute(statement)
    cursor.execute(
        """
        INSERT INTO vault_private.local_schema_metadata (schema_key, schema_fingerprint)
        VALUES (%s,%s)
        ON CONFLICT (schema_key) DO UPDATE SET
          schema_fingerprint=EXCLUDED.schema_fingerprint, updated_at=now()
        """,
        ("extensions_v1", SCHEMA_FINGERPRINT),
    )
