from __future__ import annotations

from hashlib import sha256

from app.vault_runtime.local_identity.schema import Cursor

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_conversations (
      conversation_id text PRIMARY KEY,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      create_key text NOT NULL,
      history_version bigint NOT NULL DEFAULT 0 CHECK (history_version >= 0),
      next_turn_ordinal bigint NOT NULL DEFAULT 0 CHECK (next_turn_ordinal >= 0),
      state text NOT NULL DEFAULT 'open' CHECK (state IN ('open','sealed')),
      title text NOT NULL DEFAULT '' CHECK (length(title) <= 256),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (user_id,workspace_id,conversation_id),
      UNIQUE (user_id,workspace_id,create_key)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_conversations_scope_updated
    ON vault_private.vault_conversations (user_id,workspace_id,updated_at DESC,conversation_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_conversation_segments (
      segment_id text PRIMARY KEY,
      conversation_id text NOT NULL,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      ordinal bigint NOT NULL CHECK (ordinal >= 0),
      state text NOT NULL DEFAULT 'open' CHECK (state IN ('open','sealed','incomplete')),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (user_id,workspace_id,conversation_id,segment_id),
      UNIQUE (user_id,workspace_id,conversation_id,ordinal),
      FOREIGN KEY (user_id,workspace_id,conversation_id)
        REFERENCES vault_private.vault_conversations (user_id,workspace_id,conversation_id)
        ON DELETE CASCADE
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_vault_conversation_open_segment
    ON vault_private.vault_conversation_segments (user_id,workspace_id,conversation_id)
    WHERE state='open'
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_conversation_turns (
      turn_id text PRIMARY KEY,
      conversation_id text NOT NULL,
      segment_id text NOT NULL,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      ordinal bigint NOT NULL CHECK (ordinal >= 0),
      submission_key text NOT NULL,
      input_text text NOT NULL CHECK (octet_length(input_text) <= 65536 AND length(input_text) > 0),
      input_fingerprint text NOT NULL CHECK (length(input_fingerprint) = 64),
      submitted_history_version bigint NOT NULL CHECK (submitted_history_version >= 0),
      state text NOT NULL DEFAULT 'submitted'
        CHECK (state IN ('submitted','running','completed','interrupted','failed')),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (user_id,workspace_id,conversation_id,turn_id),
      UNIQUE (user_id,workspace_id,conversation_id,submission_key),
      UNIQUE (user_id,workspace_id,conversation_id,ordinal),
      FOREIGN KEY (user_id,workspace_id,conversation_id,segment_id)
        REFERENCES vault_private.vault_conversation_segments (user_id,workspace_id,conversation_id,segment_id)
        ON DELETE CASCADE
    )
    """,
)

SCHEMA_STATEMENTS += (
    "ALTER TABLE vault_private.vault_conversation_turns ADD COLUMN IF NOT EXISTS explicit_remember boolean NOT NULL DEFAULT false",
)

SCHEMA_FINGERPRINT = sha256("\n".join(SCHEMA_STATEMENTS).encode("utf-8")).hexdigest()


def ensure_conversation_schema(cursor: Cursor) -> None:
    for statement in SCHEMA_STATEMENTS:
        cursor.execute(statement)
    cursor.execute(
        """INSERT INTO vault_private.local_schema_metadata (schema_key,schema_fingerprint)
           VALUES (%s,%s) ON CONFLICT (schema_key) DO UPDATE SET
             schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()""",
        ("conversation_v1", SCHEMA_FINGERPRINT),
    )
