from __future__ import annotations

from hashlib import sha256
from typing import Protocol


class Cursor(Protocol):
    def execute(self, query: str, params: object | None = None) -> object: ...


# The browser-handle and host-helper tables are replaced, not migrated.
LEGACY_DROP_STATEMENTS = (
    """
    DROP TABLE IF EXISTS
      vault_private.host_filesystem_mounts,
      vault_private.host_filesystem_pairings,
      vault_private.host_filesystem_integrations,
      vault_private.host_filesystem_settings
    CASCADE
    """,
)

SCHEMA_STATEMENTS = (
    "CREATE SCHEMA IF NOT EXISTS vault_private",
    """
    CREATE TABLE IF NOT EXISTS vault_private.folder_grants (
      grant_id text PRIMARY KEY,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      location_id text NOT NULL,
      relative_path text NOT NULL,
      max_permission text NOT NULL CHECK (max_permission IN ('read', 'write')),
      created_by text REFERENCES vault_private.local_users(user_id) ON DELETE SET NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (user_id, location_id, relative_path)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.user_folders (
      folder_id text PRIMARY KEY,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      grant_id text NOT NULL REFERENCES vault_private.folder_grants(grant_id) ON DELETE CASCADE,
      relative_path text NOT NULL,
      name text NOT NULL,
      name_folded text NOT NULL,
      permission text NOT NULL CHECK (permission IN ('read', 'write')),
      created_vault boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (user_id, name_folded)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_user_folders_grant
    ON vault_private.user_folders (grant_id)
    """,
    # Hidden files (names starting with ".") are off unless switched on. The switch covers the
    # folder and everything inside it.
    """
    ALTER TABLE vault_private.folder_grants
      ADD COLUMN IF NOT EXISTS include_hidden boolean NOT NULL DEFAULT false
    """,
    """
    ALTER TABLE vault_private.user_folders
      ADD COLUMN IF NOT EXISTS include_hidden boolean NOT NULL DEFAULT false
    """,
)

SCHEMA_FINGERPRINT = sha256("\n".join(SCHEMA_STATEMENTS).encode("utf-8")).hexdigest()


def ensure_folders_schema(cursor: Cursor) -> None:
    for statement in LEGACY_DROP_STATEMENTS + SCHEMA_STATEMENTS:
        cursor.execute(statement)
    cursor.execute(
        """
        INSERT INTO vault_private.local_schema_metadata (schema_key, schema_fingerprint)
        VALUES (%s, %s)
        ON CONFLICT (schema_key) DO UPDATE SET
          schema_fingerprint = EXCLUDED.schema_fingerprint,
          updated_at = now()
        """,
        ("folders_v1", SCHEMA_FINGERPRINT),
    )
