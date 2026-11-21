"""0002: personal MCP credentials, owner grants for a shared account, OAuth client registrations.

Adds the tables ``extensions/mcp_accounts.py`` uses (decision record 2026-11-20, "Authorization
and accounts"). Idempotent. Moving credentials stored per connection into personal ones needs
the local key, so Vault does that at startup (``McpAccounts.migrate_connection_headers``).

Do not edit after release; add a new migration.
"""

from __future__ import annotations

STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_extension_credentials (
      extension_id text NOT NULL REFERENCES vault_private.vault_extensions(extension_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      credential_kind text NOT NULL CHECK (credential_kind IN ('headers','oauth')),
      shared boolean NOT NULL DEFAULT false,
      nonce bytea NOT NULL,
      ciphertext bytea NOT NULL,
      updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (extension_id, user_id)
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ux_vault_extension_credentials_one_shared
    ON vault_private.vault_extension_credentials (extension_id) WHERE shared
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_extension_credential_grants (
      extension_id text NOT NULL REFERENCES vault_private.vault_extensions(extension_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      granted_by_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (extension_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_mcp_oauth_clients (
      client_key text PRIMARY KEY,
      issuer text NOT NULL,
      nonce bytea NOT NULL,
      ciphertext bytea NOT NULL,
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
)


def apply(cursor) -> None:
    for statement in STATEMENTS:
        cursor.execute(statement)
