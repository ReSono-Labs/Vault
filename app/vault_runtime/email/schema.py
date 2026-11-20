from __future__ import annotations

from hashlib import sha256
from typing import Protocol


class Cursor(Protocol):
    def execute(self, query: str, params: object | None = None) -> object: ...


# Direct Voice Mail schema slice, adapted only to Phase 2 local user/workspace FKs
# and removal of the separate Agent Mail feature.
SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_email_provider_credentials (
      provider_credential_id text PRIMARY KEY,
      account_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      nonce bytea NOT NULL,
      ciphertext bytea NOT NULL,
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked')),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (workspace_id, provider_credential_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_email_mailbox_accounts (
      vault_email_mailbox_account_id text PRIMARY KEY,
      account_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE RESTRICT,
      mailbox_role text NOT NULL CHECK (mailbox_role IN ('normal_email','agent_mail')),
      provider_kind text NOT NULL CHECK (provider_kind = 'email'),
      email_address text NOT NULL,
      display_name text,
      provider_credential_id text NOT NULL,
      lifecycle_status text NOT NULL DEFAULT 'active'
        CHECK (lifecycle_status IN ('active', 'disabled', 'disconnected', 'removed')),
      sync_enabled boolean NOT NULL DEFAULT true,
      sync_status text NOT NULL DEFAULT 'pending'
        CHECK (sync_status IN ('pending', 'backfilling', 'complete', 'stale', 'partial', 'failed', 'disconnected')),
      sync_error_code text,
      sync_error_class text,
      last_sync_started_at timestamptz,
      last_sync_completed_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (workspace_id, email_address)
    )
    """,
    """ALTER TABLE vault_private.vault_email_mailbox_accounts DROP CONSTRAINT IF EXISTS vault_email_mailbox_accounts_mailbox_role_check""",
    """ALTER TABLE vault_private.vault_email_mailbox_accounts ADD CONSTRAINT vault_email_mailbox_accounts_mailbox_role_check CHECK (mailbox_role IN ('normal_email','agent_mail'))""",
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_email_folders (
      vault_email_folder_id text PRIMARY KEY,
      account_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE RESTRICT,
      mailbox_account_id text NOT NULL
        REFERENCES vault_private.vault_email_mailbox_accounts(vault_email_mailbox_account_id) ON DELETE RESTRICT,
      provider_folder_key text NOT NULL,
      display_name text NOT NULL,
      delimiter text,
      special_use text,
      provider_flags_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
      uid_validity bigint,
      uid_next bigint,
      message_count integer,
      unread_count integer,
      provider_present boolean NOT NULL DEFAULT true,
      provider_last_seen_at timestamptz,
      reconciliation_status text NOT NULL DEFAULT 'pending'
        CHECK (reconciliation_status IN ('pending', 'backfilling', 'complete', 'stale', 'partial', 'failed')),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (mailbox_account_id, provider_folder_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_email_messages (
      vault_email_message_id text PRIMARY KEY,
      account_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE RESTRICT,
      mailbox_account_id text NOT NULL
        REFERENCES vault_private.vault_email_mailbox_accounts(vault_email_mailbox_account_id) ON DELETE RESTRICT,
      folder_id text NOT NULL
        REFERENCES vault_private.vault_email_folders(vault_email_folder_id) ON DELETE RESTRICT,
      provider_uid_validity bigint NOT NULL,
      provider_uid bigint NOT NULL,
      provider_message_id text,
      thread_key text,
      from_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
      to_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
      cc_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
      bcc_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
      reply_to_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
      subject text,
      snippet text,
      body_text text,
      body_html text,
      flags_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
      is_unread boolean NOT NULL DEFAULT true,
      is_archived boolean NOT NULL DEFAULT false,
      provider_present boolean NOT NULL DEFAULT true,
      provider_last_seen_at timestamptz,
      content_complete boolean NOT NULL DEFAULT false,
      received_at timestamptz,
      sent_at timestamptz,
      provider_internal_at timestamptz,
      size_bytes bigint,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (folder_id, provider_uid_validity, provider_uid)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_email_attachments (
      vault_email_attachment_id text PRIMARY KEY,
      account_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE RESTRICT,
      mailbox_account_id text NOT NULL
        REFERENCES vault_private.vault_email_mailbox_accounts(vault_email_mailbox_account_id) ON DELETE RESTRICT,
      message_id text NOT NULL
        REFERENCES vault_private.vault_email_messages(vault_email_message_id) ON DELETE RESTRICT,
      provider_part_key text NOT NULL,
      file_name text,
      content_type text,
      content_disposition text,
      content_id text,
      size_bytes bigint NOT NULL DEFAULT 0,
      sha256 text,
      content_bytes bytea,
      content_complete boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (message_id, provider_part_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_email_send_requests (
      vault_email_send_request_id text PRIMARY KEY,
      account_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE RESTRICT,
      mailbox_account_id text NOT NULL
        REFERENCES vault_private.vault_email_mailbox_accounts(vault_email_mailbox_account_id) ON DELETE RESTRICT,
      idempotency_key text NOT NULL,
      recipients_jsonb jsonb NOT NULL,
      subject text NOT NULL,
      body_text text NOT NULL,
      attachment_ids_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
      status text NOT NULL DEFAULT 'pending_confirmation'
        CHECK (status IN ('pending_confirmation', 'cancelled', 'sending', 'sent', 'failed', 'expired')),
      confirmation_hash text,
      expires_at timestamptz NOT NULL,
      provider_action_request_id text,
      support_safe_error_code text,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (mailbox_account_id, idempotency_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_email_sync_cursors (
      vault_email_sync_cursor_id text PRIMARY KEY,
      account_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE RESTRICT,
      mailbox_account_id text NOT NULL
        REFERENCES vault_private.vault_email_mailbox_accounts(vault_email_mailbox_account_id) ON DELETE RESTRICT,
      folder_id text NOT NULL
        REFERENCES vault_private.vault_email_folders(vault_email_folder_id) ON DELETE RESTRICT,
      cursor_kind text NOT NULL CHECK (cursor_kind IN ('backfill', 'incremental')),
      uid_validity bigint,
      last_uid bigint,
      next_before_uid bigint,
      backfill_complete boolean NOT NULL DEFAULT false,
      cursor_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (folder_id, cursor_kind)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_email_sync_runs (
      vault_email_sync_run_id text PRIMARY KEY,
      account_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE RESTRICT,
      mailbox_account_id text NOT NULL
        REFERENCES vault_private.vault_email_mailbox_accounts(vault_email_mailbox_account_id) ON DELETE RESTRICT,
      trigger_kind text NOT NULL,
      status text NOT NULL CHECK (status IN ('running', 'complete', 'partial', 'failed', 'cancelled')),
      folder_count integer NOT NULL DEFAULT 0,
      message_count integer NOT NULL DEFAULT 0,
      attachment_count integer NOT NULL DEFAULT 0,
      failure_count integer NOT NULL DEFAULT 0,
      support_safe_error_code text,
      support_safe_error_class text,
      started_at timestamptz NOT NULL DEFAULT now(),
      completed_at timestamptz,
      duration_ms integer,
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    ALTER TABLE vault_private.vault_email_folders
    ADD COLUMN IF NOT EXISTS provider_present boolean NOT NULL DEFAULT true
    """,
    """
    ALTER TABLE vault_private.vault_email_folders
    ADD COLUMN IF NOT EXISTS provider_last_seen_at timestamptz
    """,
    """
    ALTER TABLE vault_private.vault_email_messages
    ADD COLUMN IF NOT EXISTS provider_present boolean NOT NULL DEFAULT true
    """,
    """
    ALTER TABLE vault_private.vault_email_messages
    ADD COLUMN IF NOT EXISTS provider_last_seen_at timestamptz
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_email_mailboxes_scope
    ON vault_private.vault_email_mailbox_accounts (account_id, workspace_id, lifecycle_status, mailbox_role)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_email_folders_scope
    ON vault_private.vault_email_folders (account_id, workspace_id, mailbox_account_id, special_use)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_email_messages_recent
    ON vault_private.vault_email_messages (mailbox_account_id, received_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_email_messages_unread
    ON vault_private.vault_email_messages (mailbox_account_id, is_unread, received_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_email_messages_text_fts
    ON vault_private.vault_email_messages USING gin (
      to_tsvector(
        'simple',
        coalesce(subject, '') || ' ' || coalesce(snippet, '') || ' ' || coalesce(body_text, '')
      )
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_email_attachments_message
    ON vault_private.vault_email_attachments (mailbox_account_id, message_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_email_sync_runs_recent
    ON vault_private.vault_email_sync_runs (mailbox_account_id, started_at DESC)
    """,
)

SCHEMA_FINGERPRINT = sha256("\\n".join(SCHEMA_STATEMENTS).encode()).hexdigest()


def ensure_email_schema(cursor: Cursor) -> None:
    for statement in SCHEMA_STATEMENTS:
        cursor.execute(statement)
    cursor.execute(
        """INSERT INTO vault_private.local_schema_metadata (schema_key,schema_fingerprint)
           VALUES (%s,%s) ON CONFLICT (schema_key) DO UPDATE SET
             schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()""",
        ("email_v1", SCHEMA_FINGERPRINT),
    )
