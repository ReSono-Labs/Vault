from __future__ import annotations

from hashlib import sha256
from typing import Protocol


class Cursor(Protocol):
    def execute(self, query: str, params: object | None = None) -> object: ...
    def fetchone(self): ...


SCHEMA_STATEMENTS: tuple[str, ...] = (
    "CREATE SCHEMA IF NOT EXISTS vault_private",
    """
    CREATE TABLE IF NOT EXISTS vault_private.local_users (
      user_id text PRIMARY KEY,
      username_normalized text NOT NULL UNIQUE,
      display_name text NOT NULL,
      experience_style text NOT NULL,
      password_hash text NOT NULL,
      is_device_owner boolean NOT NULL DEFAULT false,
      password_mode text NOT NULL DEFAULT 'user_managed'
        CHECK (password_mode IN ('user_managed', 'temporary_password', 'master_managed', 'setup_link')),
      must_change_password boolean NOT NULL DEFAULT false,
      activation_token_hash text UNIQUE,
      activation_expires_at timestamptz,
      activation_consumed_at timestamptz,
      age_group text NOT NULL DEFAULT 'adult'
        CHECK (age_group IN ('under_18', 'adult')),
      status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'locked', 'deleted')),
      failed_login_count integer NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0),
      locked_at timestamptz,
      last_login_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.local_workspaces (
      workspace_id text PRIMARY KEY,
      owner_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      display_name text NOT NULL,
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.local_workspace_memberships (
      membership_id text PRIMARY KEY,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      membership_type text NOT NULL CHECK (membership_type IN ('owner', 'member')),
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
      created_at timestamptz NOT NULL DEFAULT now(),
      revoked_at timestamptz,
      UNIQUE (workspace_id, user_id)
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_local_workspace_one_active_owner
    ON vault_private.local_workspace_memberships (workspace_id)
    WHERE membership_type = 'owner' AND status = 'active'
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_local_workspace_memberships_user_status
    ON vault_private.local_workspace_memberships (user_id, status)
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.local_sessions (
      session_id text PRIMARY KEY,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      token_hash text NOT NULL UNIQUE,
      csrf_token_hash text NOT NULL,
      active_workspace_id text REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE SET NULL,
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked', 'rotated')),
      issued_at timestamptz NOT NULL,
      expires_at timestamptz NOT NULL,
      revoked_at timestamptz,
      revocation_reason text,
      rotated_to_session_id text REFERENCES vault_private.local_sessions(session_id) ON DELETE SET NULL,
      last_seen_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_local_sessions_user_status_expires
    ON vault_private.local_sessions (user_id, status, expires_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.local_schema_metadata (
      schema_key text PRIMARY KEY,
      schema_fingerprint text NOT NULL,
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
)

SCHEMA_FINGERPRINT = sha256("\n".join(SCHEMA_STATEMENTS).encode("utf-8")).hexdigest()


def ensure_local_identity_schema(cursor: Cursor) -> None:
    for statement in SCHEMA_STATEMENTS:
        cursor.execute(statement)
    cursor.execute("ALTER TABLE vault_private.local_users ADD COLUMN IF NOT EXISTS password_mode text NOT NULL DEFAULT 'user_managed'")
    cursor.execute("ALTER TABLE vault_private.local_users ADD COLUMN IF NOT EXISTS must_change_password boolean NOT NULL DEFAULT false")
    cursor.execute("ALTER TABLE vault_private.local_users ADD COLUMN IF NOT EXISTS activation_token_hash text")
    cursor.execute("ALTER TABLE vault_private.local_users ADD COLUMN IF NOT EXISTS activation_expires_at timestamptz")
    cursor.execute("ALTER TABLE vault_private.local_users ADD COLUMN IF NOT EXISTS activation_consumed_at timestamptz")
    cursor.execute("ALTER TABLE vault_private.local_users ADD COLUMN IF NOT EXISTS age_group text NOT NULL DEFAULT 'adult'")
    cursor.execute(
        """DO $$ BEGIN
             ALTER TABLE vault_private.local_users ADD CONSTRAINT ck_local_users_age_group
               CHECK (age_group IN ('under_18', 'adult'));
           EXCEPTION WHEN duplicate_object THEN NULL;
           END $$"""
    )
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_local_users_activation_token_hash ON vault_private.local_users (activation_token_hash) WHERE activation_token_hash IS NOT NULL")
    cursor.execute(
        """
        INSERT INTO vault_private.local_schema_metadata (schema_key, schema_fingerprint)
        VALUES (%s, %s)
        ON CONFLICT (schema_key) DO UPDATE SET
          schema_fingerprint = EXCLUDED.schema_fingerprint,
          updated_at = now()
        """,
        ("local_identity_v1", SCHEMA_FINGERPRINT),
    )
