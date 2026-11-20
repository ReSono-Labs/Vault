from __future__ import annotations

from hashlib import sha256
from typing import Protocol


class Cursor(Protocol):
    def execute(self, query: str, params: object | None = None) -> object: ...


# PostgreSQL adaptation of Voice Vault memory relations and R1 v042 lifecycle.
# Phase 2 identity schema must be installed first.
SCHEMA_STATEMENTS: tuple[str, ...] = (
    "CREATE EXTENSION IF NOT EXISTS vector",
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_transcript_entries (
      entry_id text PRIMARY KEY,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      voice_session_id text NOT NULL,
      entry_index integer NOT NULL CHECK (entry_index >= 0),
      role text NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
      event_type text NOT NULL,
      text_content text NOT NULL CHECK (length(text_content) <= 16384),
      metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (workspace_id, user_id, voice_session_id, entry_index)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_transcript_scope_session
    ON vault_private.vault_transcript_entries (workspace_id, user_id, voice_session_id, entry_index)
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_session_summaries (
      summary_id text PRIMARY KEY,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      voice_session_id text NOT NULL,
      summary_text text NOT NULL,
      reviewer_contract_version integer NOT NULL,
      transcript_fingerprint text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (workspace_id, user_id, voice_session_id, reviewer_contract_version, transcript_fingerprint)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_memory_records (
      memory_id text PRIMARY KEY,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      visibility text NOT NULL CHECK (visibility IN ('private', 'workspace')),
      subject_id text NOT NULL,
      domain text NOT NULL CHECK (domain IN ('identity','personal','relationship','environment','project','device','platform')),
      memory_type text NOT NULL CHECK (memory_type IN ('fact','preference','decision','episode','constraint','correction')),
      memory_key text NOT NULL,
      content_text text NOT NULL CHECK (length(content_text) <= 4096),
      source_authority text NOT NULL CHECK (source_authority IN ('user_asserted','tool_verified','model_derived')),
      confidence text NOT NULL CHECK (confidence IN ('low','medium','high')),
      sensitivity text NOT NULL CHECK (sensitivity IN ('normal','sensitive')),
      lifecycle_status text NOT NULL DEFAULT 'active' CHECK (lifecycle_status IN ('active','conflicted','superseded')),
      current_version integer NOT NULL DEFAULT 1 CHECK (current_version >= 1),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_vault_memory_private_canonical_active
    ON vault_private.vault_memory_records
      (workspace_id, user_id, subject_id, domain, memory_type, memory_key)
    WHERE visibility='private' AND lifecycle_status IN ('active', 'conflicted')
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_vault_memory_workspace_canonical_active
    ON vault_private.vault_memory_records
      (workspace_id, subject_id, domain, memory_type, memory_key)
    WHERE visibility='workspace' AND lifecycle_status IN ('active', 'conflicted')
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_memory_scope_retrieval
    ON vault_private.vault_memory_records (workspace_id, visibility, user_id, lifecycle_status)
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_memory_record_versions (
      version_id text PRIMARY KEY,
      memory_id text NOT NULL REFERENCES vault_private.vault_memory_records(memory_id) ON DELETE CASCADE,
      version_number integer NOT NULL CHECK (version_number >= 1),
      actor_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      intent text NOT NULL CHECK (intent IN ('create','confirm','correct','conflict')),
      content_text text NOT NULL,
      source_authority text NOT NULL CHECK (source_authority IN ('user_asserted','tool_verified','model_derived')),
      confidence text NOT NULL CHECK (confidence IN ('low','medium','high')),
      sensitivity text NOT NULL CHECK (sensitivity IN ('normal','sensitive')),
      source_session_id text,
      reviewer_contract_version integer NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (memory_id, version_number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_memory_evidence (
      evidence_id text PRIMARY KEY,
      version_id text NOT NULL REFERENCES vault_private.vault_memory_record_versions(version_id) ON DELETE CASCADE,
      transcript_entry_id text REFERENCES vault_private.vault_transcript_entries(entry_id) ON DELETE SET NULL,
      evidence_kind text NOT NULL,
      source_authority text NOT NULL CHECK (source_authority IN ('user_asserted','tool_verified','model_derived')),
      evidence_text text NOT NULL CHECK (length(evidence_text) <= 16384),
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_memory_ingestions (
      ingestion_id text PRIMARY KEY,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      voice_session_id text NOT NULL,
      reviewer_contract_version integer NOT NULL,
      transcript_fingerprint text NOT NULL,
      state text NOT NULL DEFAULT 'running' CHECK (state IN ('running','completed','failed')),
      reviewer_model text,
      candidate_count integer,
      stored_count integer,
      error_code text,
      created_at timestamptz NOT NULL DEFAULT now(),
      completed_at timestamptz,
      UNIQUE (workspace_id, user_id, voice_session_id, reviewer_contract_version, transcript_fingerprint)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_memory_pending_actions (
      action_id text PRIMARY KEY,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      voice_session_id text NOT NULL,
      memory_id text NOT NULL REFERENCES vault_private.vault_memory_records(memory_id) ON DELETE CASCADE,
      action_kind text NOT NULL CHECK (action_kind IN ('correct','forget')),
      proposed_content text CHECK (proposed_content IS NULL OR length(proposed_content) <= 4096),
      prepared_entry_index integer NOT NULL CHECK (prepared_entry_index >= 0),
      status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','consumed')),
      created_at timestamptz NOT NULL DEFAULT now(),
      consumed_at timestamptz
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_vault_memory_pending_scope
    ON vault_private.vault_memory_pending_actions (workspace_id, user_id, voice_session_id, status)
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_memory_embeddings (
      memory_id text PRIMARY KEY REFERENCES vault_private.vault_memory_records(memory_id) ON DELETE CASCADE,
      provider text NOT NULL,
      model text NOT NULL,
      dimensions integer NOT NULL CHECK (dimensions > 0),
      vector_json jsonb NOT NULL,
      embedding vector NOT NULL,
      content_fingerprint text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    ALTER TABLE vault_private.vault_memory_embeddings
    ADD COLUMN IF NOT EXISTS embedding vector
    """,
    """
    UPDATE vault_private.vault_memory_embeddings
    SET embedding = vector_json::text::vector
    WHERE embedding IS NULL
    """,
    """
    ALTER TABLE vault_private.vault_memory_embeddings
    ALTER COLUMN embedding SET NOT NULL
    """,
)

SCHEMA_STATEMENTS += (
    """
    ALTER TABLE vault_private.vault_memory_records
    ADD COLUMN IF NOT EXISTS retrieval_epoch bigint NOT NULL DEFAULT 1
      CHECK (retrieval_epoch > 0)
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_memory_scope_epochs (
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      user_id text REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      retrieval_epoch bigint NOT NULL DEFAULT 1 CHECK (retrieval_epoch > 0),
      UNIQUE NULLS NOT DISTINCT (workspace_id, user_id)
    )
    """,
    """
    INSERT INTO vault_private.vault_memory_scope_epochs (workspace_id, user_id)
    SELECT workspace_id, NULL FROM vault_private.local_workspaces
    ON CONFLICT (workspace_id, user_id) DO NOTHING
    """,
    """
    INSERT INTO vault_private.vault_memory_scope_epochs (workspace_id, user_id)
    SELECT m.workspace_id, m.user_id
    FROM vault_private.local_workspace_memberships m
    JOIN vault_private.local_users u ON u.user_id = m.user_id
    WHERE u.status <> 'deleted'
    ON CONFLICT (workspace_id, user_id) DO NOTHING
    """,
    """
    CREATE OR REPLACE FUNCTION vault_private.vault_memory_record_epoch()
    RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
      IF TG_OP = 'INSERT' THEN
        NEW.retrieval_epoch := 1;
      ELSIF ROW(NEW.memory_id, NEW.workspace_id, NEW.user_id, NEW.visibility,
        NEW.subject_id, NEW.domain, NEW.memory_type, NEW.memory_key,
        NEW.content_text, NEW.source_authority, NEW.confidence, NEW.sensitivity,
        NEW.lifecycle_status, NEW.current_version, NEW.created_at, NEW.updated_at)
        IS DISTINCT FROM
        ROW(OLD.memory_id, OLD.workspace_id, OLD.user_id, OLD.visibility,
        OLD.subject_id, OLD.domain, OLD.memory_type, OLD.memory_key,
        OLD.content_text, OLD.source_authority, OLD.confidence, OLD.sensitivity,
        OLD.lifecycle_status, OLD.current_version, OLD.created_at, OLD.updated_at)
      THEN NEW.retrieval_epoch := OLD.retrieval_epoch + 1;
      ELSE NEW.retrieval_epoch := OLD.retrieval_epoch;
      END IF;
      RETURN NEW;
    END $$
    """,
    """
    CREATE OR REPLACE TRIGGER vault_memory_record_epoch
    BEFORE INSERT OR UPDATE ON vault_private.vault_memory_records
    FOR EACH ROW EXECUTE FUNCTION vault_private.vault_memory_record_epoch()
    """,
    """
    CREATE OR REPLACE FUNCTION vault_private.vault_memory_bump_scope(
      target_workspace text, target_user text)
    RETURNS void LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM vault_private.local_workspaces
        WHERE workspace_id = target_workspace) THEN RETURN; END IF;
      IF target_user IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM vault_private.local_users
        WHERE user_id = target_user AND status <> 'deleted') THEN RETURN; END IF;
      INSERT INTO vault_private.vault_memory_scope_epochs (workspace_id, user_id)
        VALUES (target_workspace, NULL)
        ON CONFLICT (workspace_id, user_id) DO NOTHING;
      INSERT INTO vault_private.vault_memory_scope_epochs (workspace_id, user_id)
        VALUES (target_workspace, target_user)
        ON CONFLICT (workspace_id, user_id) DO UPDATE SET
          retrieval_epoch = vault_private.vault_memory_scope_epochs.retrieval_epoch + 1;
    END $$
    """,
    """
    CREATE OR REPLACE FUNCTION vault_private.vault_memory_scope_epoch()
    RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    DECLARE old_user text; new_user text;
    BEGIN
      IF TG_OP = 'UPDATE' AND NEW.retrieval_epoch = OLD.retrieval_epoch
        THEN RETURN NULL; END IF;
      IF TG_OP <> 'INSERT' THEN
        old_user := CASE WHEN OLD.visibility = 'workspace' THEN NULL ELSE OLD.user_id END;
        PERFORM vault_private.vault_memory_bump_scope(OLD.workspace_id, old_user);
      END IF;
      IF TG_OP <> 'DELETE' THEN
        new_user := CASE WHEN NEW.visibility = 'workspace' THEN NULL ELSE NEW.user_id END;
        IF TG_OP = 'INSERT' OR ROW(OLD.workspace_id, old_user)
          IS DISTINCT FROM ROW(NEW.workspace_id, new_user) THEN
          PERFORM vault_private.vault_memory_bump_scope(NEW.workspace_id, new_user);
        END IF;
      END IF;
      RETURN NULL;
    END $$
    """,
    """
    CREATE OR REPLACE TRIGGER vault_memory_scope_epoch
    AFTER INSERT OR UPDATE OR DELETE ON vault_private.vault_memory_records
    FOR EACH ROW EXECUTE FUNCTION vault_private.vault_memory_scope_epoch()
    """,
)

SCHEMA_STATEMENTS += (
    "ALTER TABLE vault_private.vault_memory_evidence ADD COLUMN IF NOT EXISTS source_ref_json jsonb",
    """ALTER TABLE vault_private.vault_memory_ingestions
      ADD COLUMN IF NOT EXISTS review_json jsonb,
      ADD COLUMN IF NOT EXISTS reviewer_provider text,
      ADD COLUMN IF NOT EXISTS analysis_steps_json jsonb NOT NULL DEFAULT '{}'::jsonb""",
    """ALTER TABLE vault_private.vault_memory_pending_actions
      ALTER COLUMN voice_session_id DROP NOT NULL,
      ADD COLUMN IF NOT EXISTS conversation_id text,
      ADD COLUMN IF NOT EXISTS prepared_turn_id text""",

)

SCHEMA_FINGERPRINT = sha256("\n".join(SCHEMA_STATEMENTS).encode("utf-8")).hexdigest()


def ensure_memory_schema(cursor: Cursor) -> None:
    for statement in SCHEMA_STATEMENTS:
        cursor.execute(statement)
    from app.vault_runtime.memory.suppression import ensure_suppression_schema
    ensure_suppression_schema(cursor)
    cursor.execute(
        """
        INSERT INTO vault_private.local_schema_metadata (schema_key, schema_fingerprint)
        VALUES (%s, %s)
        ON CONFLICT (schema_key) DO UPDATE SET
          schema_fingerprint = EXCLUDED.schema_fingerprint,
          updated_at = now()
        """,
        ("memory_v1_r1_contract_v2", SCHEMA_FINGERPRINT),
    )
