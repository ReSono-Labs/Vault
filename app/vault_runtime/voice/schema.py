from __future__ import annotations

from hashlib import sha256
from typing import Protocol


class Cursor(Protocol):
    def execute(self, query: str, params: object | None = None) -> object: ...


# PostgreSQL translation of Voice VoiceRealtimeSessionModel plus its
# support-safe provider-event and tool-invocation ledgers. Hosted teardown and
# route-grant delivery tables are intentionally excluded.
SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_voice_provider_credentials (
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      provider_key text NOT NULL,
      model_key text NOT NULL,
      background_model_key text NOT NULL DEFAULT 'gpt-5.6-sol',
      voice text NOT NULL,
      nonce bytea NOT NULL,
      ciphertext bytea NOT NULL,
      changed_by_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (workspace_id, provider_key)
    )
    """,
    """ALTER TABLE vault_private.vault_voice_provider_credentials
       ADD COLUMN IF NOT EXISTS auth_method text NOT NULL DEFAULT 'api_key'""",
    """ALTER TABLE vault_private.vault_voice_provider_credentials
       ADD COLUMN IF NOT EXISTS api_key_configured boolean NOT NULL DEFAULT true""",
    """ALTER TABLE vault_private.vault_voice_provider_credentials
       ADD COLUMN IF NOT EXISTS background_model_key text NOT NULL DEFAULT 'gpt-5.6-sol'""",
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_ai_oauth_credentials (
      workspace_id text NOT NULL,
      provider_key text NOT NULL,
      nonce bytea NOT NULL,
      ciphertext bytea NOT NULL,
      updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (workspace_id,provider_key),
      FOREIGN KEY (workspace_id,provider_key)
        REFERENCES vault_private.vault_voice_provider_credentials(workspace_id,provider_key)
        ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_voice_sessions (
      voice_session_id text PRIMARY KEY,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      local_session_id text NOT NULL REFERENCES vault_private.local_sessions(session_id) ON DELETE CASCADE,
      provider_key text NOT NULL,
      auth_method text NOT NULL DEFAULT 'api_key' CHECK (auth_method IN ('api_key','chatgpt_oauth','gemini_oauth','xai_oauth')),
      api_key_configured boolean NOT NULL DEFAULT true,
      model_key text NOT NULL,
      connection_mode text NOT NULL CHECK (connection_mode IN ('webrtc','websocket','provider-websocket')),
      status text NOT NULL CHECK (status IN ('starting','transport_open','closed','failed','lost')),
      provider_session_id text,
      provider_request_id text,
      opened_at timestamptz NOT NULL,
      closed_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CHECK (
        (status IN ('closed','failed','lost') AND closed_at IS NOT NULL)
        OR (status IN ('starting','transport_open') AND closed_at IS NULL)
      )
    )
    """,
    """ALTER TABLE vault_private.vault_voice_sessions DROP CONSTRAINT IF EXISTS vault_voice_sessions_connection_mode_check""",
    """ALTER TABLE vault_private.vault_voice_sessions ADD CONSTRAINT vault_voice_sessions_connection_mode_check
       CHECK (connection_mode IN ('webrtc','websocket','provider-websocket'))""",
    """ALTER TABLE vault_private.vault_voice_sessions DROP CONSTRAINT IF EXISTS vault_voice_sessions_auth_method_check""",
    """ALTER TABLE vault_private.vault_voice_sessions ADD CONSTRAINT vault_voice_sessions_auth_method_check
       CHECK (auth_method IN ('api_key','chatgpt_oauth','gemini_oauth','xai_oauth'))""",
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_ai_provider_selection (
      workspace_id text PRIMARY KEY REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      provider_key text NOT NULL,
      changed_by_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_voice_provider_access (
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      provider_key text NOT NULL,
      access_mode text NOT NULL DEFAULT 'shared' CHECK (access_mode IN ('shared','individual')),
      changed_by_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (user_id, provider_key)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_voice_sessions_scope_opened
    ON vault_private.vault_voice_sessions (workspace_id, user_id, opened_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_voice_sessions_local_status
    ON vault_private.vault_voice_sessions (local_session_id, status)
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_voice_provider_events (
      provider_event_id text NOT NULL,
      voice_session_id text NOT NULL REFERENCES vault_private.vault_voice_sessions(voice_session_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      event_type text NOT NULL,
      event_role text CHECK (event_role IS NULL OR event_role IN ('user','assistant','tool')),
      payload_sha256 text NOT NULL CHECK (length(payload_sha256)=64),
      transcript_entry_index integer CHECK (transcript_entry_index IS NULL OR transcript_entry_index >= 0),
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (voice_session_id, provider_event_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_voice_tool_grants (
      grant_id text PRIMARY KEY,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      user_id text REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      tool_name text NOT NULL,
      effect_class text NOT NULL CHECK (effect_class IN ('read','write','delete')),
      voice_enabled boolean NOT NULL DEFAULT false,
      background_enabled boolean NOT NULL DEFAULT false,
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked')),
      created_at timestamptz NOT NULL DEFAULT now(),
      revoked_at timestamptz,
      UNIQUE NULLS NOT DISTINCT (workspace_id, user_id, tool_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_voice_tool_invocations (
      invocation_id text PRIMARY KEY,
      voice_session_id text NOT NULL REFERENCES vault_private.vault_voice_sessions(voice_session_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      tool_call_id text NOT NULL,
      tool_name text NOT NULL,
      effect_class text NOT NULL CHECK (effect_class IN ('read','write','delete')),
      arguments_sha256 text NOT NULL CHECK (length(arguments_sha256)=64),
      arguments_redacted jsonb NOT NULL DEFAULT '{}'::jsonb,
      state text NOT NULL CHECK (state IN ('prepared','invoking','failed','succeeded','effect_unknown')),
      attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
      failure_code text,
      prepared_at timestamptz NOT NULL DEFAULT now(),
      completed_at timestamptz,
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (voice_session_id, tool_call_id),
      CHECK (
        (state IN ('succeeded','effect_unknown') AND completed_at IS NOT NULL)
        OR (state IN ('prepared','invoking','failed') AND completed_at IS NULL)
      )
    )
    """,
    """ALTER TABLE vault_private.vault_voice_tool_invocations
       ADD COLUMN IF NOT EXISTS arguments_redacted jsonb NOT NULL DEFAULT '{}'::jsonb""",
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_voice_tool_results (
      invocation_id text PRIMARY KEY REFERENCES vault_private.vault_voice_tool_invocations(invocation_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      result_json jsonb NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
)

SCHEMA_FINGERPRINT = sha256("\n".join(SCHEMA_STATEMENTS).encode("utf-8")).hexdigest()


def ensure_voice_schema(cursor: Cursor) -> None:
    for statement in SCHEMA_STATEMENTS:
        cursor.execute(statement)
    cursor.execute(
        """
        INSERT INTO vault_private.local_schema_metadata (schema_key, schema_fingerprint)
        VALUES (%s,%s)
        ON CONFLICT (schema_key) DO UPDATE SET
          schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
        """,
        ("voice_runtime_v1", SCHEMA_FINGERPRINT),
    )
