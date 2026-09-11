from __future__ import annotations

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_workspace_folder_shares (
      share_id text PRIMARY KEY,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      folder_path text NOT NULL,
      folder_path_hash text NOT NULL,
      grantee_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      permission text NOT NULL CHECK (permission IN ('read', 'write')),
      created_by_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
      created_at timestamptz NOT NULL DEFAULT now(),
      revoked_at timestamptz,
      UNIQUE (workspace_id, folder_path_hash, grantee_user_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_workspace_folder_shares_grantee
    ON vault_private.vault_workspace_folder_shares (grantee_user_id, status)
    """,
    """
    ALTER TABLE vault_private.vault_workspace_folder_shares
    ADD COLUMN IF NOT EXISTS share_kind text NOT NULL DEFAULT 'folder'
    """,
    """
    ALTER TABLE vault_private.vault_workspace_folder_shares
    ADD COLUMN IF NOT EXISTS share_mount_name text
    """,
    """
    UPDATE vault_private.vault_workspace_folder_shares
    SET share_mount_name = split_part(folder_path, '/', array_length(string_to_array(folder_path, '/'), 1))
    WHERE share_mount_name IS NULL OR share_mount_name = ''
    """,
    """
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'vault_private'
          AND table_name = 'vault_workspace_folder_shares'
          AND column_name = 'share_mount_name'
          AND is_nullable = 'YES'
      ) THEN
        ALTER TABLE vault_private.vault_workspace_folder_shares
        ALTER COLUMN share_mount_name SET NOT NULL;
      END IF;
    END $$
    """,
)
