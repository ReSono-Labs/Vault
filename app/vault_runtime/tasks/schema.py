from __future__ import annotations

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_tasks (
      task_id text PRIMARY KEY,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      task_text text NOT NULL,
      status text NOT NULL CHECK (status IN ('open', 'completed')),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      completed_at timestamptz
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_tasks_scope_status
    ON vault_private.vault_tasks (user_id, workspace_id, status, created_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_task_pending_actions (
      action_id text PRIMARY KEY,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      task_id text,
      operation text NOT NULL CHECK (operation IN ('add', 'edit', 'complete', 'remove')),
      payload_json text NOT NULL,
      content_hash text NOT NULL,
      state text NOT NULL CHECK (state IN ('pending_review', 'executing', 'completed', 'failed')),
      voice_session_id text NOT NULL,
      tool_call_id text NOT NULL,
      prepared_utterance_id integer NOT NULL DEFAULT 0,
      expires_at timestamptz NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
)
