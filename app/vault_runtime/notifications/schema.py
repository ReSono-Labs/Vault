from __future__ import annotations

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_notifications (
      notification_id text PRIMARY KEY,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      kind text NOT NULL,
      title text NOT NULL,
      body text NOT NULL DEFAULT '',
      payload jsonb NOT NULL DEFAULT '{}'::jsonb,
      dismissed_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_notifications_scope_active
    ON vault_private.vault_notifications (user_id, workspace_id, dismissed_at, created_at DESC)
    """,
)
