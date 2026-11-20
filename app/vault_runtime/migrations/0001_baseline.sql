-- 0001 baseline, frozen: the statements migration 0001 executed on a fresh database before
-- FREEZE-0001 (cleanup B5), in order. 0001_baseline.py runs them; the module DDL functions
-- they came from may change later without changing what 0001 does. Never edit this file:
-- the migration checksum covers it. Add a new migration instead.
--
-- Format: each "-- @statement" line starts one statement (optional JSON list: its parameters).
-- "-- @step <name>" marks a state-dependent step that 0001_baseline.py runs as code.
-- @statement
CREATE SCHEMA IF NOT EXISTS vault_private
-- @statement

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
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.local_workspaces (
      workspace_id text PRIMARY KEY,
      owner_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      display_name text NOT NULL,
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    
-- @statement

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
    
-- @statement

    CREATE UNIQUE INDEX IF NOT EXISTS uq_local_workspace_one_active_owner
    ON vault_private.local_workspace_memberships (workspace_id)
    WHERE membership_type = 'owner' AND status = 'active'
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_local_workspace_memberships_user_status
    ON vault_private.local_workspace_memberships (user_id, status)
    
-- @statement

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
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_local_sessions_user_status_expires
    ON vault_private.local_sessions (user_id, status, expires_at)
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.local_schema_metadata (
      schema_key text PRIMARY KEY,
      schema_fingerprint text NOT NULL,
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    
-- @statement
ALTER TABLE vault_private.local_users ADD COLUMN IF NOT EXISTS password_mode text NOT NULL DEFAULT 'user_managed'
-- @statement
ALTER TABLE vault_private.local_users ADD COLUMN IF NOT EXISTS must_change_password boolean NOT NULL DEFAULT false
-- @statement
ALTER TABLE vault_private.local_users ADD COLUMN IF NOT EXISTS activation_token_hash text
-- @statement
ALTER TABLE vault_private.local_users ADD COLUMN IF NOT EXISTS activation_expires_at timestamptz
-- @statement
ALTER TABLE vault_private.local_users ADD COLUMN IF NOT EXISTS activation_consumed_at timestamptz
-- @statement
ALTER TABLE vault_private.local_users ADD COLUMN IF NOT EXISTS age_group text NOT NULL DEFAULT 'adult'
-- @statement
DO $$ BEGIN
             ALTER TABLE vault_private.local_users ADD CONSTRAINT ck_local_users_age_group
               CHECK (age_group IN ('under_18', 'adult'));
           EXCEPTION WHEN duplicate_object THEN NULL;
           END $$
-- @statement
CREATE UNIQUE INDEX IF NOT EXISTS uq_local_users_activation_token_hash ON vault_private.local_users (activation_token_hash) WHERE activation_token_hash IS NOT NULL
-- @statement ["local_identity_v1", "8e5eb74692d45e69ef2f1ebc7ee7b1db9bad8dd8e052708fc34b97d4d355cbd2"]

        INSERT INTO vault_private.local_schema_metadata (schema_key, schema_fingerprint)
        VALUES (%s, %s)
        ON CONFLICT (schema_key) DO UPDATE SET
          schema_fingerprint = EXCLUDED.schema_fingerprint,
          updated_at = now()
        
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_live_memory_preferences (
       user_id text NOT NULL,
       workspace_id text NOT NULL,
       enabled boolean NOT NULL DEFAULT true,
       epoch bigint NOT NULL DEFAULT 1 CHECK (epoch > 0),
       PRIMARY KEY (user_id, workspace_id),
       FOREIGN KEY (workspace_id, user_id)
         REFERENCES vault_private.local_workspace_memberships(workspace_id, user_id)
         ON DELETE CASCADE
    )
-- @statement ["live_memory_preference_v1", "35d586458c287cb5ee5c39d49767c12b65f96ae91156d954b8e9d52aac1c29e3"]
INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
           VALUES (%s,%s) ON CONFLICT(schema_key) DO UPDATE SET
           schema_fingerprint=EXCLUDED.schema_fingerprint, updated_at=now()
-- @statement
CREATE EXTENSION IF NOT EXISTS vector
-- @statement

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
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_transcript_scope_session
    ON vault_private.vault_transcript_entries (workspace_id, user_id, voice_session_id, entry_index)
    
-- @statement

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
    
-- @statement

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
    
-- @statement

    CREATE UNIQUE INDEX IF NOT EXISTS uq_vault_memory_private_canonical_active
    ON vault_private.vault_memory_records
      (workspace_id, user_id, subject_id, domain, memory_type, memory_key)
    WHERE visibility='private' AND lifecycle_status IN ('active', 'conflicted')
    
-- @statement

    CREATE UNIQUE INDEX IF NOT EXISTS uq_vault_memory_workspace_canonical_active
    ON vault_private.vault_memory_records
      (workspace_id, subject_id, domain, memory_type, memory_key)
    WHERE visibility='workspace' AND lifecycle_status IN ('active', 'conflicted')
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_memory_scope_retrieval
    ON vault_private.vault_memory_records (workspace_id, visibility, user_id, lifecycle_status)
    
-- @statement

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
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_memory_evidence (
      evidence_id text PRIMARY KEY,
      version_id text NOT NULL REFERENCES vault_private.vault_memory_record_versions(version_id) ON DELETE CASCADE,
      transcript_entry_id text REFERENCES vault_private.vault_transcript_entries(entry_id) ON DELETE SET NULL,
      evidence_kind text NOT NULL,
      source_authority text NOT NULL CHECK (source_authority IN ('user_asserted','tool_verified','model_derived')),
      evidence_text text NOT NULL CHECK (length(evidence_text) <= 16384),
      created_at timestamptz NOT NULL DEFAULT now()
    )
    
-- @statement

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
    
-- @statement

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
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_memory_pending_scope
    ON vault_private.vault_memory_pending_actions (workspace_id, user_id, voice_session_id, status)
    
-- @statement

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
    
-- @statement

    ALTER TABLE vault_private.vault_memory_embeddings
    ADD COLUMN IF NOT EXISTS embedding vector
    
-- @statement

    UPDATE vault_private.vault_memory_embeddings
    SET embedding = vector_json::text::vector
    WHERE embedding IS NULL
    
-- @statement

    ALTER TABLE vault_private.vault_memory_embeddings
    ALTER COLUMN embedding SET NOT NULL
    
-- @statement

    ALTER TABLE vault_private.vault_memory_records
    ADD COLUMN IF NOT EXISTS retrieval_epoch bigint NOT NULL DEFAULT 1
      CHECK (retrieval_epoch > 0)
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_memory_scope_epochs (
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      user_id text REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      retrieval_epoch bigint NOT NULL DEFAULT 1 CHECK (retrieval_epoch > 0),
      UNIQUE NULLS NOT DISTINCT (workspace_id, user_id)
    )
    
-- @statement

    INSERT INTO vault_private.vault_memory_scope_epochs (workspace_id, user_id)
    SELECT workspace_id, NULL FROM vault_private.local_workspaces
    ON CONFLICT (workspace_id, user_id) DO NOTHING
    
-- @statement

    INSERT INTO vault_private.vault_memory_scope_epochs (workspace_id, user_id)
    SELECT m.workspace_id, m.user_id
    FROM vault_private.local_workspace_memberships m
    JOIN vault_private.local_users u ON u.user_id = m.user_id
    WHERE u.status <> 'deleted'
    ON CONFLICT (workspace_id, user_id) DO NOTHING
    
-- @statement

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
    
-- @statement

    CREATE OR REPLACE TRIGGER vault_memory_record_epoch
    BEFORE INSERT OR UPDATE ON vault_private.vault_memory_records
    FOR EACH ROW EXECUTE FUNCTION vault_private.vault_memory_record_epoch()
    
-- @statement

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
    
-- @statement

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
    
-- @statement

    CREATE OR REPLACE TRIGGER vault_memory_scope_epoch
    AFTER INSERT OR UPDATE OR DELETE ON vault_private.vault_memory_records
    FOR EACH ROW EXECUTE FUNCTION vault_private.vault_memory_scope_epoch()
    
-- @statement
ALTER TABLE vault_private.vault_memory_evidence ADD COLUMN IF NOT EXISTS source_ref_json jsonb
-- @statement
ALTER TABLE vault_private.vault_memory_ingestions
      ADD COLUMN IF NOT EXISTS review_json jsonb,
      ADD COLUMN IF NOT EXISTS reviewer_provider text,
      ADD COLUMN IF NOT EXISTS analysis_steps_json jsonb NOT NULL DEFAULT '{}'::jsonb
-- @statement
ALTER TABLE vault_private.vault_memory_pending_actions
      ALTER COLUMN voice_session_id DROP NOT NULL,
      ADD COLUMN IF NOT EXISTS conversation_id text,
      ADD COLUMN IF NOT EXISTS prepared_turn_id text
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_memory_suppressions (
      suppression_id text PRIMARY KEY,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      visibility text NOT NULL CHECK (visibility IN ('private','workspace')),
      identity_digest text NOT NULL CHECK(length(identity_digest)=64),
      content_digest text NOT NULL CHECK(length(content_digest)=64),
      source_entry_ids text[] NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(workspace_id,user_id,visibility,identity_digest,content_digest)
    )
-- @statement
CREATE INDEX IF NOT EXISTS ix_vault_memory_suppression_scope
      ON vault_private.vault_memory_suppressions(workspace_id,visibility,user_id)
-- @statement ["memory_suppression_v1", "af4fd1281e89562e565cdcc56beae97ba80c0d117f6a4f7970f43bea5b792587"]
INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
      VALUES(%s,%s) ON CONFLICT(schema_key) DO UPDATE SET schema_fingerprint=EXCLUDED.schema_fingerprint,
      updated_at=now()
-- @statement ["memory_v1_r1_contract_v2", "1c75c866c86e4018b583a397bdbbb545c4c3e4062d4072a1dab2906184b9229b"]

        INSERT INTO vault_private.local_schema_metadata (schema_key, schema_fingerprint)
        VALUES (%s, %s)
        ON CONFLICT (schema_key) DO UPDATE SET
          schema_fingerprint = EXCLUDED.schema_fingerprint,
          updated_at = now()
        
-- @statement

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
    
-- @statement
ALTER TABLE vault_private.vault_voice_provider_credentials
       ADD COLUMN IF NOT EXISTS auth_method text NOT NULL DEFAULT 'api_key'
-- @statement
ALTER TABLE vault_private.vault_voice_provider_credentials
       ADD COLUMN IF NOT EXISTS api_key_configured boolean NOT NULL DEFAULT true
-- @statement
ALTER TABLE vault_private.vault_voice_provider_credentials
       ADD COLUMN IF NOT EXISTS background_model_key text NOT NULL DEFAULT 'gpt-5.6-sol'
-- @statement

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
    
-- @statement

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
    
-- @statement
ALTER TABLE vault_private.vault_voice_sessions DROP CONSTRAINT IF EXISTS vault_voice_sessions_connection_mode_check
-- @statement
ALTER TABLE vault_private.vault_voice_sessions ADD CONSTRAINT vault_voice_sessions_connection_mode_check
       CHECK (connection_mode IN ('webrtc','websocket','provider-websocket'))
-- @statement
ALTER TABLE vault_private.vault_voice_sessions DROP CONSTRAINT IF EXISTS vault_voice_sessions_auth_method_check
-- @statement
ALTER TABLE vault_private.vault_voice_sessions ADD CONSTRAINT vault_voice_sessions_auth_method_check
       CHECK (auth_method IN ('api_key','chatgpt_oauth','gemini_oauth','xai_oauth'))
-- @statement
ALTER TABLE vault_private.vault_voice_sessions ADD COLUMN IF NOT EXISTS transcript_capture_state
       text NOT NULL DEFAULT 'unknown' CHECK(transcript_capture_state IN ('unknown','acknowledged','incomplete'))
-- @statement
ALTER TABLE vault_private.vault_voice_sessions ADD COLUMN IF NOT EXISTS transcript_capture_failures
       integer NOT NULL DEFAULT 0 CHECK(transcript_capture_failures>=0)
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_ai_provider_selection (
      workspace_id text PRIMARY KEY REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      provider_key text NOT NULL,
      changed_by_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_voice_provider_access (
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      provider_key text NOT NULL,
      access_mode text NOT NULL DEFAULT 'shared' CHECK (access_mode IN ('shared','individual')),
      changed_by_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (user_id, provider_key)
    )
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_voice_sessions_scope_opened
    ON vault_private.vault_voice_sessions (workspace_id, user_id, opened_at DESC)
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_voice_sessions_local_status
    ON vault_private.vault_voice_sessions (local_session_id, status)
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_voice_provider_events (
      provider_event_id text NOT NULL,
      voice_session_id text NOT NULL REFERENCES vault_private.vault_voice_sessions(voice_session_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      event_type text NOT NULL,
      event_role text CHECK (event_role IS NULL OR event_role IN ('user','assistant','tool')),
      payload_sha256 text NOT NULL CHECK (length(payload_sha256)=64),
      evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      transcript_entry_index integer CHECK (transcript_entry_index IS NULL OR transcript_entry_index >= 0),
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (voice_session_id, provider_event_id)
    )
    
-- @statement
ALTER TABLE vault_private.vault_voice_provider_events
       ADD COLUMN IF NOT EXISTS evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_voice_tool_grants (
      grant_id text PRIMARY KEY,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      user_id text REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      tool_name text NOT NULL,
      effect_class text NOT NULL CHECK (effect_class IN ('read','write','delete')),
      voice_enabled boolean NOT NULL DEFAULT false,
      background_enabled boolean NOT NULL DEFAULT false,
      approval_mode text NOT NULL DEFAULT 'allow' CHECK (approval_mode IN ('allow','ask','refuse')),
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked')),
      created_at timestamptz NOT NULL DEFAULT now(),
      revoked_at timestamptz,
      UNIQUE NULLS NOT DISTINCT (workspace_id, user_id, tool_name)
    )
    
-- @statement
ALTER TABLE vault_private.vault_voice_tool_grants
       ADD COLUMN IF NOT EXISTS approval_mode text NOT NULL DEFAULT 'allow'
         CHECK (approval_mode IN ('allow','ask','refuse'))
-- @statement

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
    
-- @statement
ALTER TABLE vault_private.vault_voice_tool_invocations
       ADD COLUMN IF NOT EXISTS arguments_redacted jsonb NOT NULL DEFAULT '{}'::jsonb
-- @statement
ALTER TABLE vault_private.vault_voice_tool_invocations
       ADD COLUMN IF NOT EXISTS source_utterance_index integer
         CHECK(source_utterance_index IS NULL OR source_utterance_index>=0)
-- @statement
ALTER TABLE vault_private.vault_voice_tool_invocations
       ADD COLUMN IF NOT EXISTS source_utterance_fingerprint text
         CHECK((source_utterance_fingerprint IS NULL OR source_utterance_fingerprint ~ '^[0-9a-f]{64}$')
           AND (source_utterance_index IS NULL)=(source_utterance_fingerprint IS NULL))
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_voice_tool_results (
      invocation_id text PRIMARY KEY REFERENCES vault_private.vault_voice_tool_invocations(invocation_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      result_json jsonb NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )
    
-- @statement ["voice_runtime_v1", "9162bf60ee8cce6af2a71eb668e00c0f296ef7a1e17c582f0dec3147add65b63"]

        INSERT INTO vault_private.local_schema_metadata (schema_key, schema_fingerprint)
        VALUES (%s,%s)
        ON CONFLICT (schema_key) DO UPDATE SET
          schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
        
-- @statement
CREATE EXTENSION IF NOT EXISTS vector
-- @statement

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
    
-- @statement

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
    
-- @statement
ALTER TABLE vault_private.vault_email_mailbox_accounts DROP CONSTRAINT IF EXISTS vault_email_mailbox_accounts_mailbox_role_check
-- @statement
ALTER TABLE vault_private.vault_email_mailbox_accounts ADD CONSTRAINT vault_email_mailbox_accounts_mailbox_role_check CHECK (mailbox_role IN ('normal_email','agent_mail'))
-- @statement

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
    
-- @statement

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
    
-- @statement

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
    
-- @statement

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
    
-- @statement

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
    
-- @statement

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
    
-- @statement

    ALTER TABLE vault_private.vault_email_folders
    ADD COLUMN IF NOT EXISTS provider_present boolean NOT NULL DEFAULT true
    
-- @statement

    ALTER TABLE vault_private.vault_email_folders
    ADD COLUMN IF NOT EXISTS provider_last_seen_at timestamptz
    
-- @statement

    ALTER TABLE vault_private.vault_email_messages
    ADD COLUMN IF NOT EXISTS provider_present boolean NOT NULL DEFAULT true
    
-- @statement

    ALTER TABLE vault_private.vault_email_messages
    ADD COLUMN IF NOT EXISTS provider_last_seen_at timestamptz
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_email_mailboxes_scope
    ON vault_private.vault_email_mailbox_accounts (account_id, workspace_id, lifecycle_status, mailbox_role)
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_email_folders_scope
    ON vault_private.vault_email_folders (account_id, workspace_id, mailbox_account_id, special_use)
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_email_messages_recent
    ON vault_private.vault_email_messages (mailbox_account_id, received_at DESC)
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_email_messages_unread
    ON vault_private.vault_email_messages (mailbox_account_id, is_unread, received_at DESC)
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_email_messages_text_fts
    ON vault_private.vault_email_messages USING gin (
      to_tsvector(
        'simple',
        coalesce(subject, '') || ' ' || coalesce(snippet, '') || ' ' || coalesce(body_text, '')
      )
    )
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_email_attachments_message
    ON vault_private.vault_email_attachments (mailbox_account_id, message_id)
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_email_sync_runs_recent
    ON vault_private.vault_email_sync_runs (mailbox_account_id, started_at DESC)
    
-- @statement ["email_v1", "f4243f8f2bda43da810a821e6f260cbc0d9029ecce4a90c0b13971f02b35c0dc"]
INSERT INTO vault_private.local_schema_metadata (schema_key,schema_fingerprint)
           VALUES (%s,%s) ON CONFLICT (schema_key) DO UPDATE SET
             schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement
CREATE SCHEMA IF NOT EXISTS vault_private
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_extensions (
      extension_id text PRIMARY KEY,
      kind text NOT NULL CHECK (kind IN ('plugin','skill','mcp')),
      identity text NOT NULL,
      display_name text NOT NULL,
      version text,
      description text,
      content_hash text NOT NULL,
      state text NOT NULL CHECK (state IN ('enabled','disabled','removed')),
      installed_by_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      installed_in_workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      previous_content_hash text,
      configuration_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      removed_at timestamptz,
      UNIQUE (installed_in_workspace_id, kind, identity)
    )
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_extension_components (
      component_id text PRIMARY KEY,
      extension_id text NOT NULL REFERENCES vault_private.vault_extensions(extension_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      component_kind text NOT NULL CHECK (component_kind IN ('skill','mcp')),
      component_name text NOT NULL,
      component_hash text NOT NULL,
      UNIQUE (workspace_id, component_kind, component_name),
      UNIQUE (extension_id, component_kind, component_name)
    )
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_extension_grants (
      grant_id text PRIMARY KEY,
      extension_id text NOT NULL REFERENCES vault_private.vault_extensions(extension_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      agent_kind text NOT NULL CHECK (agent_kind IN ('voice','background')),
      capability_name text NOT NULL DEFAULT '',
      enabled boolean NOT NULL DEFAULT true,
      effect_class text CHECK (effect_class IS NULL OR effect_class IN ('read','write','delete')),
      granted_by_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (extension_id, user_id, workspace_id, agent_kind, capability_name)
    )
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_mcp_tools (
      extension_id text NOT NULL REFERENCES vault_private.vault_extensions(extension_id) ON DELETE CASCADE,
      tool_name text NOT NULL,
      title text,
      description text NOT NULL,
      input_schema_json jsonb NOT NULL,
      output_schema_json jsonb,
      discovery_hash text NOT NULL,
      discovered_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (extension_id, tool_name)
    )
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_extension_events (
      event_id text PRIMARY KEY,
      extension_id text,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      actor_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      event_type text NOT NULL,
      detail_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now()
    )
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_extension_secrets (
      extension_id text NOT NULL REFERENCES vault_private.vault_extensions(extension_id) ON DELETE CASCADE,
      secret_name text NOT NULL,
      nonce bytea NOT NULL,
      ciphertext bytea NOT NULL,
      changed_by_user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE RESTRICT,
      updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (extension_id, secret_name)
    )
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_extension_runtime_settings (
      setting_key text PRIMARY KEY,
      enabled boolean NOT NULL,
      changed_by_user_id text REFERENCES vault_private.local_users(user_id) ON DELETE SET NULL,
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    
-- @statement

    INSERT INTO vault_private.vault_extension_runtime_settings (setting_key, enabled)
    VALUES ('third_party_extensions', false)
    ON CONFLICT (setting_key) DO NOTHING
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_extensions_scope_state
    ON vault_private.vault_extensions (installed_in_workspace_id, kind, state)
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_extension_grants_scope
    ON vault_private.vault_extension_grants (user_id, workspace_id, agent_kind, enabled)
    
-- @statement ["extensions_v1", "a47e86966e752cdec1b184bb05768c1f641b39fd6436418078daa12cdd03b687"]

        INSERT INTO vault_private.local_schema_metadata (schema_key, schema_fingerprint)
        VALUES (%s,%s)
        ON CONFLICT (schema_key) DO UPDATE SET
          schema_fingerprint=EXCLUDED.schema_fingerprint, updated_at=now()
        
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_personal_records (
      record_id text PRIMARY KEY,
      account_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      domain text NOT NULL CHECK (domain IN ('contacts_entries','contacts_pending_actions','calendar_event_cache','calendar_pending_actions','provider_credentials')),
      source_table text NOT NULL CHECK (source_table IN ('contacts_entries','contacts_pending_actions','calendar_event_cache','calendar_pending_actions','provider_credentials')),
      source_id text NOT NULL,
      source_payload jsonb NOT NULL,
      content_text text,
      imported_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (account_id,workspace_id,source_table,source_id)
    )
    
-- @statement
CREATE INDEX IF NOT EXISTS ix_vault_personal_records_scope
       ON vault_private.vault_personal_records (account_id,workspace_id,source_table,updated_at DESC)
-- @statement
CREATE INDEX IF NOT EXISTS ix_vault_personal_records_text
       ON vault_private.vault_personal_records USING gin
       (to_tsvector('simple',coalesce(content_text,'') || ' ' || source_payload::text))
-- @statement

                CREATE TABLE IF NOT EXISTS vault_private.vault_builtin_plugins (
                  account_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
                  workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
                  plugin_key text NOT NULL,
                  enabled boolean NOT NULL DEFAULT false,
                  configuration jsonb NOT NULL DEFAULT '{}'::jsonb,
                  updated_at timestamptz NOT NULL DEFAULT now(),
                  PRIMARY KEY (account_id, workspace_id, plugin_key)
                )
            
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_background_runs (
      run_id text PRIMARY KEY,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      local_session_id text NOT NULL REFERENCES vault_private.local_sessions(session_id) ON DELETE CASCADE,
      request_json jsonb NOT NULL,
      state text NOT NULL CHECK (state IN ('accepted','queued','running','reviewing','repairing','completed','failed','cancelled')),
      cancellation_requested boolean NOT NULL DEFAULT false,
      output_json jsonb,
      failure_code text,
      failure_message text,
      model_turns integer NOT NULL DEFAULT 0 CHECK (model_turns >= 0),
      tool_calls integer NOT NULL DEFAULT 0 CHECK (tool_calls >= 0),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      completed_at timestamptz
    )
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_background_runs_scope_created
    ON vault_private.vault_background_runs (workspace_id,user_id,created_at DESC)
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_background_run_events (
      run_id text NOT NULL REFERENCES vault_private.vault_background_runs(run_id) ON DELETE CASCADE,
      event_index integer NOT NULL CHECK (event_index >= 0),
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      event_type text NOT NULL,
      state text NOT NULL CHECK (state IN ('accepted','queued','running','reviewing','repairing','completed','failed','cancelled')),
      detail_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (run_id,event_index)
    )
    
-- @statement ["background_agent_v1", "cb75e8d62075a1162ba0c2a58003fd6b9341d881c120d85b60ee922140ec49fd"]

        INSERT INTO vault_private.local_schema_metadata (schema_key,schema_fingerprint)
        VALUES (%s,%s) ON CONFLICT (schema_key) DO UPDATE SET
          schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
        
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_execution_grants (
      grant_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      purpose text NOT NULL, policy_json jsonb NOT NULL CHECK (jsonb_typeof(policy_json)='object'),
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked')),
      version integer NOT NULL DEFAULT 1 CHECK (version>0), expires_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,grant_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_workers (
      worker_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      role_key text NOT NULL, spec_json jsonb NOT NULL CHECK (jsonb_typeof(spec_json)='object'),
      spec_hash text NOT NULL CHECK (length(spec_hash)=64), grant_id text,
      generation integer NOT NULL DEFAULT 1 CHECK (generation>0),
      status text NOT NULL DEFAULT 'idle' CHECK (status IN ('idle','active','paused','deleted')),
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,worker_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,grant_id) REFERENCES vault_private.vault_background_execution_grants(user_id,workspace_id,grant_id)
    )
-- @statement
CREATE UNIQUE INDEX IF NOT EXISTS uq_background_worker_role
       ON vault_private.vault_background_workers(user_id,workspace_id,role_key) WHERE status<>'deleted'
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_routines (
      routine_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      version integer NOT NULL DEFAULT 1 CHECK (version>0), rule_json jsonb NOT NULL,
      timezone text NOT NULL, next_due_at timestamptz, grant_id text NOT NULL, template_json jsonb NOT NULL,
      status text NOT NULL DEFAULT 'paused' CHECK (status IN ('active','paused','deleted')),
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,routine_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,grant_id) REFERENCES vault_private.vault_background_execution_grants(user_id,workspace_id,grant_id)
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_work (
      work_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      source_key text NOT NULL, intent_version integer NOT NULL DEFAULT 1 CHECK (intent_version>0),
      request_json jsonb NOT NULL CHECK (jsonb_typeof(request_json)='object'),
      state text NOT NULL DEFAULT 'proposed' CHECK (state IN ('proposed','ready','queued','running','waiting_approval','waiting_input','waiting_event','completed','failed','cancelled','unknown')),
      worker_id text, worker_generation integer, local_session_id text REFERENCES vault_private.local_sessions(session_id),
      grant_id text, task_id text, parent_work_id text, routine_id text,
      result_json jsonb, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      CHECK ((local_session_id IS NOT NULL) <> (grant_id IS NOT NULL)),
      CHECK ((worker_id IS NULL)=(worker_generation IS NULL)),
      UNIQUE(user_id,workspace_id,work_id), UNIQUE(user_id,workspace_id,source_key),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,worker_id) REFERENCES vault_private.vault_background_workers(user_id,workspace_id,worker_id),
      FOREIGN KEY(user_id,workspace_id,grant_id) REFERENCES vault_private.vault_background_execution_grants(user_id,workspace_id,grant_id),
      FOREIGN KEY(user_id,workspace_id,parent_work_id) REFERENCES vault_private.vault_background_work(user_id,workspace_id,work_id),
      FOREIGN KEY(user_id,workspace_id,routine_id) REFERENCES vault_private.vault_background_routines(user_id,workspace_id,routine_id)
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_sessions (
      session_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      worker_id text NOT NULL, work_id text NOT NULL, worker_generation integer NOT NULL CHECK (worker_generation>0),
      intent_version integer NOT NULL CHECK (intent_version>0), provider_key text, model_id text, adapter_version text,
      checkpoint_version integer NOT NULL DEFAULT 1, checkpoint_json jsonb,
      history_json jsonb NOT NULL DEFAULT '[]'::jsonb, source_refs_json jsonb NOT NULL DEFAULT '[]'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,session_id), UNIQUE(user_id,workspace_id,work_id,intent_version),
      CHECK ((provider_key IS NULL AND model_id IS NULL AND adapter_version IS NULL) OR
             (provider_key IS NOT NULL AND model_id IS NOT NULL AND adapter_version IS NOT NULL)),
      FOREIGN KEY(user_id,workspace_id,worker_id) REFERENCES vault_private.vault_background_workers(user_id,workspace_id,worker_id),
      FOREIGN KEY(user_id,workspace_id,work_id) REFERENCES vault_private.vault_background_work(user_id,workspace_id,work_id) ON DELETE CASCADE
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_occurrences (
      occurrence_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      routine_id text NOT NULL, routine_version integer NOT NULL, scheduled_for timestamptz NOT NULL, work_id text,
      UNIQUE(user_id,workspace_id,routine_id,routine_version,scheduled_for),
      FOREIGN KEY(user_id,workspace_id,routine_id) REFERENCES vault_private.vault_background_routines(user_id,workspace_id,routine_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,work_id) REFERENCES vault_private.vault_background_work(user_id,workspace_id,work_id)
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_events (
      event_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      source_kind text NOT NULL, source_id text NOT NULL, payload_json jsonb NOT NULL,
      state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','processed','cancelled')),
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,source_kind,source_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_actions (
      action_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      work_id text, intent_version integer, worker_generation integer, kind text NOT NULL,
      origin_json jsonb NOT NULL DEFAULT '{}'::jsonb, action_hash text NOT NULL CHECK (length(action_hash)=64),
      domain_ref text, resource_version text, arguments_json jsonb NOT NULL,
      title text NOT NULL, detail text NOT NULL, expires_at timestamptz NOT NULL,
      state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','approved','denied','expired','executing','completed','failed','unknown')),
      decision_id text, actor_user_id text, channel text, channel_generation text, receipt_json jsonb,
      operation_key text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      -- Owner approvals (2026-11-17): an approval asked during an interactive Chat turn or Voice call.
      -- Added inside CREATE TABLE before the first install had this table; later changes are migrations.
      origin_conversation_id text, origin_turn_id text, origin_voice_session_id text, origin_tool_call_id text,
      detail_lines jsonb NOT NULL DEFAULT '[]'::jsonb,
      CHECK ((origin_turn_id IS NULL)=(origin_conversation_id IS NULL)),
      CHECK ((origin_turn_id IS NOT NULL OR origin_voice_session_id IS NOT NULL)=(kind='owner_approval')),
      CHECK (kind<>'owner_approval' OR (work_id IS NULL AND origin_tool_call_id IS NOT NULL
             AND (origin_turn_id IS NULL)<>(origin_voice_session_id IS NULL))),
      CHECK (work_id IS NOT NULL OR kind IN ('worker_create','execution_grant','routine_create','owner_approval')),
      CHECK (actor_user_id IS NULL OR actor_user_id=user_id),
      UNIQUE(user_id,workspace_id,action_id), UNIQUE(user_id,workspace_id,operation_key),
      UNIQUE(user_id,workspace_id,decision_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,work_id) REFERENCES vault_private.vault_background_work(user_id,workspace_id,work_id)
    )
-- @statement
CREATE UNIQUE INDEX IF NOT EXISTS ux_owner_approval_pending ON vault_private.vault_background_actions(user_id,workspace_id)
      WHERE kind='owner_approval' AND state='pending'
-- @statement
CREATE INDEX IF NOT EXISTS ix_background_due ON vault_private.vault_background_routines(next_due_at) WHERE status='active'
-- @statement
CREATE INDEX IF NOT EXISTS ix_background_work_scope_state ON vault_private.vault_background_work(user_id,workspace_id,state,created_at)
-- @statement
ALTER TABLE vault_private.vault_background_runs ALTER COLUMN local_session_id DROP NOT NULL
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS work_id text
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS coordination_session_id text
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS execution_grant_id text
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS attempt_generation bigint NOT NULL DEFAULT 0
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS checkpoint_json jsonb
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS active_seconds double precision NOT NULL DEFAULT 0
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS first_started_at timestamptz
-- @statement
DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_background_run_authority'
                     AND conrelid='vault_private.vault_background_runs'::regclass) THEN
        ALTER TABLE vault_private.vault_background_runs ADD CONSTRAINT ck_background_run_authority
          CHECK ((local_session_id IS NOT NULL) <> (execution_grant_id IS NOT NULL));
        ALTER TABLE vault_private.vault_background_runs ADD CONSTRAINT fk_background_run_work
          FOREIGN KEY(user_id,workspace_id,work_id) REFERENCES vault_private.vault_background_work(user_id,workspace_id,work_id);
        ALTER TABLE vault_private.vault_background_runs ADD CONSTRAINT fk_background_run_session
          FOREIGN KEY(user_id,workspace_id,coordination_session_id) REFERENCES vault_private.vault_background_sessions(user_id,workspace_id,session_id);
        ALTER TABLE vault_private.vault_background_runs ADD CONSTRAINT fk_background_run_grant
          FOREIGN KEY(user_id,workspace_id,execution_grant_id) REFERENCES vault_private.vault_background_execution_grants(user_id,workspace_id,grant_id);
      END IF;
    END $$
-- @statement ["993aee392f9be696456c2d3b2f435c5af49f1806a7977d9dd2ab0b9182d6ee7e"]
INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
        VALUES ('background_coordination_v1',%s) ON CONFLICT(schema_key) DO UPDATE SET
        schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_calendar_accounts (
      calendar_account_id text PRIMARY KEY,
      account_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      provider_type text NOT NULL CHECK (provider_type IN ('ics','caldav')),
      display_name text NOT NULL,
      public_configuration jsonb NOT NULL,
      nonce bytea NOT NULL,
      ciphertext bytea NOT NULL,
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
      sync_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(account_id,workspace_id,calendar_account_id)
    )
-- @statement
CREATE INDEX IF NOT EXISTS ix_vault_calendar_accounts_scope
       ON vault_private.vault_calendar_accounts(account_id,workspace_id,status,updated_at DESC)
-- @statement

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
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_tasks_scope_status
    ON vault_private.vault_tasks (user_id, workspace_id, status, created_at)
    
-- @statement

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
    
-- @statement
ALTER TABLE vault_private.vault_task_pending_actions ALTER COLUMN voice_session_id DROP NOT NULL
-- @statement
ALTER TABLE vault_private.vault_task_pending_actions ADD COLUMN IF NOT EXISTS background_work_id text
-- @statement
ALTER TABLE vault_private.vault_task_pending_actions ADD COLUMN IF NOT EXISTS background_intent_version integer
-- @statement
ALTER TABLE vault_private.vault_task_pending_actions ADD COLUMN IF NOT EXISTS target_revision text
-- @statement

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
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_conversations_scope_updated
    ON vault_private.vault_conversations (user_id,workspace_id,updated_at DESC,conversation_id)
    
-- @statement

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
    
-- @statement

    CREATE UNIQUE INDEX IF NOT EXISTS uq_vault_conversation_open_segment
    ON vault_private.vault_conversation_segments (user_id,workspace_id,conversation_id)
    WHERE state='open'
    
-- @statement

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
    
-- @statement
ALTER TABLE vault_private.vault_conversation_turns ADD COLUMN IF NOT EXISTS explicit_remember boolean NOT NULL DEFAULT false
-- @statement ["conversation_v1", "ce701b9fbb951d965b5b17afaa6694b8421d1238c61e9900e7b05223579f3475"]
INSERT INTO vault_private.local_schema_metadata (schema_key,schema_fingerprint)
           VALUES (%s,%s) ON CONFLICT (schema_key) DO UPDATE SET
             schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement
CREATE UNIQUE INDEX IF NOT EXISTS uq_voice_session_review_scope
      ON vault_private.vault_voice_sessions(user_id,workspace_id,voice_session_id)
-- @statement
ALTER TABLE vault_private.vault_conversations
      ADD COLUMN IF NOT EXISTS source_voice_session_id text
-- @statement
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE
      conname='fk_conversation_voice_review_source' AND conrelid='vault_private.vault_conversations'::regclass)
      THEN ALTER TABLE vault_private.vault_conversations ADD CONSTRAINT fk_conversation_voice_review_source
      FOREIGN KEY(user_id,workspace_id,source_voice_session_id) REFERENCES
        vault_private.vault_voice_sessions(user_id,workspace_id,voice_session_id) ON DELETE CASCADE;
      END IF; END $$
-- @statement ["voice_decision_review_bridge_v1", "67d76e694e455e1c6930960e4219ffe975fa0ebc95c0cce1312c5d065431c2dc"]
INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
      VALUES (%s,%s) ON CONFLICT(schema_key) DO UPDATE SET
      schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_decision_reviews (
      review_id text PRIMARY KEY,
      user_id text NOT NULL,
      workspace_id text NOT NULL,
      conversation_id text NOT NULL,
      segment_id text NOT NULL,
      source_snapshot_fingerprint text NOT NULL CHECK (source_snapshot_fingerprint ~ '^[0-9a-f]{64}$'),
      learner_contract_version integer NOT NULL CHECK (learner_contract_version > 0),
      provider text NOT NULL DEFAULT '',
      model text NOT NULL DEFAULT '',
      state text NOT NULL CHECK (state IN ('queued','running','retryable','failed','completed')),
      lease_owner text,
      lease_until timestamptz,
      attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
      proposals_json jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(proposals_json)='array'),
      source_coverage_json jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(source_coverage_json)='object'),
      output_fingerprint text CHECK (output_fingerprint IS NULL OR output_fingerprint ~ '^[0-9a-f]{64}$'),
      error_code text,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      completed_at timestamptz,
      UNIQUE(user_id,workspace_id,conversation_id,segment_id,source_snapshot_fingerprint,learner_contract_version),
      FOREIGN KEY(user_id,workspace_id,conversation_id,segment_id)
        REFERENCES vault_private.vault_conversation_segments(user_id,workspace_id,conversation_id,segment_id)
        ON DELETE CASCADE,
      CHECK (state <> 'running' OR (lease_owner IS NOT NULL AND lease_until IS NOT NULL)),
      CHECK ((state='completed') = (completed_at IS NOT NULL)),
      CHECK (state <> 'completed' OR output_fingerprint IS NOT NULL)
    )
-- @statement
ALTER TABLE vault_private.vault_decision_reviews ADD COLUMN IF NOT EXISTS assessments_json
      jsonb NOT NULL DEFAULT '[]'::jsonb CHECK(jsonb_typeof(assessments_json)='array')
-- @statement
CREATE INDEX IF NOT EXISTS ix_vault_decision_reviews_scope_lease
       ON vault_private.vault_decision_reviews(user_id,workspace_id,state,lease_until)
-- @statement ["dab0bee2855a4fed529ce9e25403423b289e58c99d05f06d072145726f5e68a2"]
INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
      VALUES ('decision_reviews_v1',%s) ON CONFLICT(schema_key) DO UPDATE SET
      schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement
CREATE EXTENSION IF NOT EXISTS vector
-- @statement
CREATE UNIQUE INDEX IF NOT EXISTS uq_vault_decision_review_scope_id
       ON vault_private.vault_decision_reviews(user_id,workspace_id,review_id)
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_decision_generations (
      generation_id text PRIMARY KEY,user_id text NOT NULL,workspace_id text NOT NULL,
      review_id text NOT NULL,schema_version integer NOT NULL CHECK(schema_version>0),
      compiler_version text NOT NULL,source_snapshot_fingerprint text NOT NULL
        CHECK(source_snapshot_fingerprint ~ '^[0-9a-f]{64}$'),
      state text NOT NULL CHECK(state IN ('building','validated','active','retired','failed')),
      created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,generation_id),UNIQUE(user_id,workspace_id,review_id),
      FOREIGN KEY(user_id,workspace_id,review_id)
        REFERENCES vault_private.vault_decision_reviews(user_id,workspace_id,review_id) ON DELETE CASCADE
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_decision_definitions (
      definition_id text NOT NULL,generation_id text NOT NULL,version integer NOT NULL CHECK(version>0),
      user_id text NOT NULL,workspace_id text NOT NULL,decision_key text NOT NULL,
      conditions_json jsonb NOT NULL CHECK(jsonb_typeof(conditions_json)='object'),
      required_slots_json jsonb NOT NULL CHECK(jsonb_typeof(required_slots_json)='array'),
      capability_refs_json jsonb NOT NULL CHECK(jsonb_typeof(capability_refs_json)='array'),
      action_description text NOT NULL,exclusions_json jsonb NOT NULL CHECK(jsonb_typeof(exclusions_json)='array'),
      status text NOT NULL CHECK(status IN ('proposed','active','inactive')),
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(user_id,workspace_id,generation_id,definition_id,version),
      UNIQUE(user_id,workspace_id,generation_id,decision_key,version),
      FOREIGN KEY(user_id,workspace_id,generation_id)
        REFERENCES vault_private.vault_decision_generations(user_id,workspace_id,generation_id) ON DELETE CASCADE
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_decision_examples (
      example_id text PRIMARY KEY,user_id text NOT NULL,workspace_id text NOT NULL,
      generation_id text NOT NULL,definition_id text NOT NULL,definition_version integer NOT NULL,
      example_text text NOT NULL,example_kind text NOT NULL CHECK(example_kind IN ('observed','synthetic','counterexample')),
      outcome_class text NOT NULL CHECK(outcome_class IN ('resolved','corrected','unresolved','unknown')),
      source_set_fingerprint text NOT NULL CHECK(source_set_fingerprint ~ '^[0-9a-f]{64}$'),
      source_review_id text NOT NULL,enabled boolean NOT NULL DEFAULT true,
      provider text,model text,dimensions integer,embedding vector,embedding_fingerprint text,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,generation_id,definition_id,definition_version,example_kind,source_set_fingerprint),
      FOREIGN KEY(user_id,workspace_id,generation_id,definition_id,definition_version)
        REFERENCES vault_private.vault_decision_definitions(user_id,workspace_id,generation_id,definition_id,version)
        ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,source_review_id)
        REFERENCES vault_private.vault_decision_reviews(user_id,workspace_id,review_id) ON DELETE CASCADE,
      CHECK((embedding IS NULL AND provider IS NULL AND model IS NULL AND dimensions IS NULL AND embedding_fingerprint IS NULL)
        OR (embedding IS NOT NULL AND provider IS NOT NULL AND model IS NOT NULL AND dimensions IS NOT NULL AND dimensions>0
          AND vector_dims(embedding)=dimensions AND embedding_fingerprint IS NOT NULL
          AND embedding_fingerprint ~ '^[0-9a-f]{64}$'))
    )
-- @statement
CREATE INDEX IF NOT EXISTS ix_vault_decision_definition_scope
       ON vault_private.vault_decision_definitions(user_id,workspace_id,generation_id,status,decision_key)
-- @statement
CREATE INDEX IF NOT EXISTS ix_vault_decision_example_scope
       ON vault_private.vault_decision_examples(user_id,workspace_id,generation_id,definition_id,enabled)
-- @statement ["fb77ae9be2e576b2f79068e85b97a5fb8754c6545bccc9cdf878a6945cc62f98"]
INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
      VALUES ('decision_rules_v1',%s) ON CONFLICT(schema_key) DO UPDATE SET
      schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement

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
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_notifications_scope_active
    ON vault_private.vault_notifications (user_id, workspace_id, dismissed_at, created_at DESC)
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_background_runs (
      run_id text PRIMARY KEY,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      local_session_id text NOT NULL REFERENCES vault_private.local_sessions(session_id) ON DELETE CASCADE,
      request_json jsonb NOT NULL,
      state text NOT NULL CHECK (state IN ('accepted','queued','running','reviewing','repairing','completed','failed','cancelled')),
      cancellation_requested boolean NOT NULL DEFAULT false,
      output_json jsonb,
      failure_code text,
      failure_message text,
      model_turns integer NOT NULL DEFAULT 0 CHECK (model_turns >= 0),
      tool_calls integer NOT NULL DEFAULT 0 CHECK (tool_calls >= 0),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      completed_at timestamptz
    )
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_background_runs_scope_created
    ON vault_private.vault_background_runs (workspace_id,user_id,created_at DESC)
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_background_run_events (
      run_id text NOT NULL REFERENCES vault_private.vault_background_runs(run_id) ON DELETE CASCADE,
      event_index integer NOT NULL CHECK (event_index >= 0),
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      event_type text NOT NULL,
      state text NOT NULL CHECK (state IN ('accepted','queued','running','reviewing','repairing','completed','failed','cancelled')),
      detail_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (run_id,event_index)
    )
    
-- @statement ["background_agent_v1", "cb75e8d62075a1162ba0c2a58003fd6b9341d881c120d85b60ee922140ec49fd"]

        INSERT INTO vault_private.local_schema_metadata (schema_key,schema_fingerprint)
        VALUES (%s,%s) ON CONFLICT (schema_key) DO UPDATE SET
          schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
        
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_execution_grants (
      grant_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      purpose text NOT NULL, policy_json jsonb NOT NULL CHECK (jsonb_typeof(policy_json)='object'),
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked')),
      version integer NOT NULL DEFAULT 1 CHECK (version>0), expires_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,grant_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_workers (
      worker_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      role_key text NOT NULL, spec_json jsonb NOT NULL CHECK (jsonb_typeof(spec_json)='object'),
      spec_hash text NOT NULL CHECK (length(spec_hash)=64), grant_id text,
      generation integer NOT NULL DEFAULT 1 CHECK (generation>0),
      status text NOT NULL DEFAULT 'idle' CHECK (status IN ('idle','active','paused','deleted')),
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,worker_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,grant_id) REFERENCES vault_private.vault_background_execution_grants(user_id,workspace_id,grant_id)
    )
-- @statement
CREATE UNIQUE INDEX IF NOT EXISTS uq_background_worker_role
       ON vault_private.vault_background_workers(user_id,workspace_id,role_key) WHERE status<>'deleted'
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_routines (
      routine_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      version integer NOT NULL DEFAULT 1 CHECK (version>0), rule_json jsonb NOT NULL,
      timezone text NOT NULL, next_due_at timestamptz, grant_id text NOT NULL, template_json jsonb NOT NULL,
      status text NOT NULL DEFAULT 'paused' CHECK (status IN ('active','paused','deleted')),
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,routine_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,grant_id) REFERENCES vault_private.vault_background_execution_grants(user_id,workspace_id,grant_id)
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_work (
      work_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      source_key text NOT NULL, intent_version integer NOT NULL DEFAULT 1 CHECK (intent_version>0),
      request_json jsonb NOT NULL CHECK (jsonb_typeof(request_json)='object'),
      state text NOT NULL DEFAULT 'proposed' CHECK (state IN ('proposed','ready','queued','running','waiting_approval','waiting_input','waiting_event','completed','failed','cancelled','unknown')),
      worker_id text, worker_generation integer, local_session_id text REFERENCES vault_private.local_sessions(session_id),
      grant_id text, task_id text, parent_work_id text, routine_id text,
      result_json jsonb, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      CHECK ((local_session_id IS NOT NULL) <> (grant_id IS NOT NULL)),
      CHECK ((worker_id IS NULL)=(worker_generation IS NULL)),
      UNIQUE(user_id,workspace_id,work_id), UNIQUE(user_id,workspace_id,source_key),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,worker_id) REFERENCES vault_private.vault_background_workers(user_id,workspace_id,worker_id),
      FOREIGN KEY(user_id,workspace_id,grant_id) REFERENCES vault_private.vault_background_execution_grants(user_id,workspace_id,grant_id),
      FOREIGN KEY(user_id,workspace_id,parent_work_id) REFERENCES vault_private.vault_background_work(user_id,workspace_id,work_id),
      FOREIGN KEY(user_id,workspace_id,routine_id) REFERENCES vault_private.vault_background_routines(user_id,workspace_id,routine_id)
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_sessions (
      session_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      worker_id text NOT NULL, work_id text NOT NULL, worker_generation integer NOT NULL CHECK (worker_generation>0),
      intent_version integer NOT NULL CHECK (intent_version>0), provider_key text, model_id text, adapter_version text,
      checkpoint_version integer NOT NULL DEFAULT 1, checkpoint_json jsonb,
      history_json jsonb NOT NULL DEFAULT '[]'::jsonb, source_refs_json jsonb NOT NULL DEFAULT '[]'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,session_id), UNIQUE(user_id,workspace_id,work_id,intent_version),
      CHECK ((provider_key IS NULL AND model_id IS NULL AND adapter_version IS NULL) OR
             (provider_key IS NOT NULL AND model_id IS NOT NULL AND adapter_version IS NOT NULL)),
      FOREIGN KEY(user_id,workspace_id,worker_id) REFERENCES vault_private.vault_background_workers(user_id,workspace_id,worker_id),
      FOREIGN KEY(user_id,workspace_id,work_id) REFERENCES vault_private.vault_background_work(user_id,workspace_id,work_id) ON DELETE CASCADE
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_occurrences (
      occurrence_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      routine_id text NOT NULL, routine_version integer NOT NULL, scheduled_for timestamptz NOT NULL, work_id text,
      UNIQUE(user_id,workspace_id,routine_id,routine_version,scheduled_for),
      FOREIGN KEY(user_id,workspace_id,routine_id) REFERENCES vault_private.vault_background_routines(user_id,workspace_id,routine_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,work_id) REFERENCES vault_private.vault_background_work(user_id,workspace_id,work_id)
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_events (
      event_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      source_kind text NOT NULL, source_id text NOT NULL, payload_json jsonb NOT NULL,
      state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','processed','cancelled')),
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,source_kind,source_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_actions (
      action_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      work_id text, intent_version integer, worker_generation integer, kind text NOT NULL,
      origin_json jsonb NOT NULL DEFAULT '{}'::jsonb, action_hash text NOT NULL CHECK (length(action_hash)=64),
      domain_ref text, resource_version text, arguments_json jsonb NOT NULL,
      title text NOT NULL, detail text NOT NULL, expires_at timestamptz NOT NULL,
      state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','approved','denied','expired','executing','completed','failed','unknown')),
      decision_id text, actor_user_id text, channel text, channel_generation text, receipt_json jsonb,
      operation_key text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      -- Owner approvals (2026-11-17): an approval asked during an interactive Chat turn or Voice call.
      -- Added inside CREATE TABLE before the first install had this table; later changes are migrations.
      origin_conversation_id text, origin_turn_id text, origin_voice_session_id text, origin_tool_call_id text,
      detail_lines jsonb NOT NULL DEFAULT '[]'::jsonb,
      CHECK ((origin_turn_id IS NULL)=(origin_conversation_id IS NULL)),
      CHECK ((origin_turn_id IS NOT NULL OR origin_voice_session_id IS NOT NULL)=(kind='owner_approval')),
      CHECK (kind<>'owner_approval' OR (work_id IS NULL AND origin_tool_call_id IS NOT NULL
             AND (origin_turn_id IS NULL)<>(origin_voice_session_id IS NULL))),
      CHECK (work_id IS NOT NULL OR kind IN ('worker_create','execution_grant','routine_create','owner_approval')),
      CHECK (actor_user_id IS NULL OR actor_user_id=user_id),
      UNIQUE(user_id,workspace_id,action_id), UNIQUE(user_id,workspace_id,operation_key),
      UNIQUE(user_id,workspace_id,decision_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,work_id) REFERENCES vault_private.vault_background_work(user_id,workspace_id,work_id)
    )
-- @statement
CREATE UNIQUE INDEX IF NOT EXISTS ux_owner_approval_pending ON vault_private.vault_background_actions(user_id,workspace_id)
      WHERE kind='owner_approval' AND state='pending'
-- @statement
CREATE INDEX IF NOT EXISTS ix_background_due ON vault_private.vault_background_routines(next_due_at) WHERE status='active'
-- @statement
CREATE INDEX IF NOT EXISTS ix_background_work_scope_state ON vault_private.vault_background_work(user_id,workspace_id,state,created_at)
-- @statement
ALTER TABLE vault_private.vault_background_runs ALTER COLUMN local_session_id DROP NOT NULL
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS work_id text
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS coordination_session_id text
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS execution_grant_id text
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS attempt_generation bigint NOT NULL DEFAULT 0
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS checkpoint_json jsonb
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS active_seconds double precision NOT NULL DEFAULT 0
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS first_started_at timestamptz
-- @statement
DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_background_run_authority'
                     AND conrelid='vault_private.vault_background_runs'::regclass) THEN
        ALTER TABLE vault_private.vault_background_runs ADD CONSTRAINT ck_background_run_authority
          CHECK ((local_session_id IS NOT NULL) <> (execution_grant_id IS NOT NULL));
        ALTER TABLE vault_private.vault_background_runs ADD CONSTRAINT fk_background_run_work
          FOREIGN KEY(user_id,workspace_id,work_id) REFERENCES vault_private.vault_background_work(user_id,workspace_id,work_id);
        ALTER TABLE vault_private.vault_background_runs ADD CONSTRAINT fk_background_run_session
          FOREIGN KEY(user_id,workspace_id,coordination_session_id) REFERENCES vault_private.vault_background_sessions(user_id,workspace_id,session_id);
        ALTER TABLE vault_private.vault_background_runs ADD CONSTRAINT fk_background_run_grant
          FOREIGN KEY(user_id,workspace_id,execution_grant_id) REFERENCES vault_private.vault_background_execution_grants(user_id,workspace_id,grant_id);
      END IF;
    END $$
-- @statement ["993aee392f9be696456c2d3b2f435c5af49f1806a7977d9dd2ab0b9182d6ee7e"]
INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
        VALUES ('background_coordination_v1',%s) ON CONFLICT(schema_key) DO UPDATE SET
        schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement
CREATE SCHEMA IF NOT EXISTS vault_background_queue
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS dispatch_job_id bigint
-- @step procrastinate_schema
-- Procrastinate Schema

DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS plpgsql WITH SCHEMA pg_catalog;
EXCEPTION
    WHEN OTHERS THEN
        -- On managed PostgreSQL services (e.g. Azure Database for PostgreSQL, Amazon RDS,
        -- Google Cloud SQL), CREATE EXTENSION may fail with various error codes:
        -- insufficient_privilege, feature_not_supported, or provider-specific errors.
        -- Before ignoring, verify the extension actually exists — if it does not exist
        -- and cannot be created, re-raise so the failure is explicit.
        IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'plpgsql') THEN
            RAISE NOTICE 'plpgsql extension already exists, skipping creation.';
        ELSE
            RAISE;
        END IF;
END;
$$;

-- Enums

CREATE TYPE procrastinate_job_status AS ENUM (
    'todo',  -- The job is queued
    'doing',  -- The job has been fetched by a worker
    'succeeded',  -- The job ended successfully
    'failed',  -- The job ended with an error
    'cancelled', -- The job was cancelled
    'aborting',  -- legacy, not used anymore since v3.0.0
    'aborted'  -- The job was aborted
);

CREATE TYPE procrastinate_job_event_type AS ENUM (
    'deferred',  -- Job created, in todo
    'started',  -- todo -> doing
    'deferred_for_retry',  -- doing -> todo
    'failed',  -- doing -> failed
    'succeeded',  -- doing -> succeeded
    'cancelled', -- todo -> cancelled
    'abort_requested', -- not a state transition, but set in a separate field
    'aborted', -- doing -> aborted (only allowed when abort_requested field is set)
    'scheduled', -- not a state transition, but recording when a task is scheduled for
    'retried' -- Manually retried failed job
);

-- Composite Types

CREATE TYPE procrastinate_job_to_defer_v1 AS (
    queue_name character varying,
    task_name character varying,
    priority integer,
    lock text,
    queueing_lock text,
    args jsonb,
    scheduled_at timestamp with time zone
);

-- Tables

CREATE TABLE procrastinate_workers(
    id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    last_heartbeat timestamp with time zone NOT NULL DEFAULT NOW()
);

CREATE TABLE procrastinate_jobs (
    id bigserial PRIMARY KEY,
    queue_name character varying(128) NOT NULL,
    task_name character varying(128) NOT NULL,
    priority integer DEFAULT 0 NOT NULL,
    lock text,
    queueing_lock text,
    args jsonb DEFAULT '{}' NOT NULL,
    status procrastinate_job_status DEFAULT 'todo'::procrastinate_job_status NOT NULL,
    scheduled_at timestamp with time zone NULL,
    attempts integer DEFAULT 0 NOT NULL,
    abort_requested boolean DEFAULT false NOT NULL,
    worker_id bigint REFERENCES procrastinate_workers(id) ON DELETE SET NULL,
    CONSTRAINT check_not_todo_abort_requested CHECK (NOT (status = 'todo' AND abort_requested = true))
);

CREATE TABLE procrastinate_periodic_defers (
    id bigserial PRIMARY KEY,
    task_name character varying(128) NOT NULL,
    defer_timestamp bigint,
    job_id bigint REFERENCES procrastinate_jobs(id) NULL,
    periodic_id character varying(128) NOT NULL DEFAULT '',
    CONSTRAINT procrastinate_periodic_defers_unique UNIQUE (task_name, periodic_id, defer_timestamp)
);

CREATE TABLE procrastinate_events (
    id bigserial PRIMARY KEY,
    job_id bigint NOT NULL REFERENCES procrastinate_jobs ON DELETE CASCADE,
    type procrastinate_job_event_type,
    at timestamp with time zone DEFAULT NOW() NULL
);

-- Constraints & Indices

-- this prevents from having several jobs with the same queueing lock in the "todo" state
CREATE UNIQUE INDEX procrastinate_jobs_queueing_lock_idx_v1 ON procrastinate_jobs (queueing_lock) WHERE status = 'todo';
-- this prevents from having several jobs with the same lock in the "doing" state
CREATE UNIQUE INDEX procrastinate_jobs_lock_idx_v1 ON procrastinate_jobs (lock) WHERE status = 'doing';

-- Index for select_stalled_jobs_by_heartbeat query
CREATE INDEX idx_procrastinate_jobs_worker_not_null ON procrastinate_jobs(worker_id) WHERE worker_id IS NOT NULL AND status = 'doing'::procrastinate_job_status;

CREATE INDEX procrastinate_jobs_queue_name_idx_v1 ON procrastinate_jobs(queue_name);
CREATE INDEX procrastinate_jobs_id_lock_idx_v1 ON procrastinate_jobs (id, lock) WHERE status = ANY (ARRAY['todo'::procrastinate_job_status, 'doing'::procrastinate_job_status]);
CREATE INDEX procrastinate_jobs_priority_idx_v1 ON procrastinate_jobs(priority desc, id asc) WHERE (status = 'todo'::procrastinate_job_status);

CREATE INDEX procrastinate_events_job_id_fkey_v1 ON procrastinate_events(job_id);

CREATE INDEX procrastinate_periodic_defers_job_id_fkey_v1 ON procrastinate_periodic_defers(job_id);

CREATE INDEX idx_procrastinate_workers_last_heartbeat ON procrastinate_workers(last_heartbeat);

-- Functions
CREATE FUNCTION procrastinate_defer_jobs_v1(
    jobs procrastinate_job_to_defer_v1[]
)
    RETURNS bigint[]
    LANGUAGE plpgsql
AS $$
DECLARE
    job_ids bigint[];
BEGIN
    WITH inserted_jobs AS (
        INSERT INTO procrastinate_jobs (queue_name, task_name, priority, lock, queueing_lock, args, scheduled_at)
        SELECT (job).queue_name,
               (job).task_name,
               (job).priority,
               (job).lock,
               (job).queueing_lock,
               (job).args,
               (job).scheduled_at
        FROM unnest(jobs) AS job
        RETURNING id
    )
    SELECT array_agg(id) FROM inserted_jobs INTO job_ids;

    RETURN job_ids;
END;
$$;

CREATE FUNCTION procrastinate_defer_periodic_job_v2(
    _queue_name character varying,
    _lock character varying,
    _queueing_lock character varying,
    _task_name character varying,
    _priority integer,
    _periodic_id character varying,
    _defer_timestamp bigint,
    _args jsonb
)
    RETURNS bigint
    LANGUAGE plpgsql
AS $$
DECLARE
	_job_id bigint;
	_defer_id bigint;
BEGIN
    INSERT
        INTO procrastinate_periodic_defers (task_name, periodic_id, defer_timestamp)
        VALUES (_task_name, _periodic_id, _defer_timestamp)
        ON CONFLICT DO NOTHING
        RETURNING id into _defer_id;

    IF _defer_id IS NULL THEN
        RETURN NULL;
    END IF;

    UPDATE procrastinate_periodic_defers
        SET job_id = (
            SELECT COALESCE((
                SELECT unnest(procrastinate_defer_jobs_v1(
                    ARRAY[
                        ROW(
                            _queue_name,
                            _task_name,
                            _priority,
                            _lock,
                            _queueing_lock,
                            _args,
                            NULL::timestamptz
                        )
                    ]::procrastinate_job_to_defer_v1[]
                ))
            ), NULL)
        )
        WHERE id = _defer_id
        RETURNING job_id INTO _job_id;

    DELETE
        FROM procrastinate_periodic_defers
        USING (
            SELECT id
            FROM procrastinate_periodic_defers
            WHERE procrastinate_periodic_defers.task_name = _task_name
            AND procrastinate_periodic_defers.periodic_id = _periodic_id
            AND procrastinate_periodic_defers.defer_timestamp < _defer_timestamp
            ORDER BY id
            FOR UPDATE
        ) to_delete
        WHERE procrastinate_periodic_defers.id = to_delete.id;

    RETURN _job_id;
END;
$$;

CREATE FUNCTION procrastinate_fetch_job_v2(
    target_queue_names character varying[],
    p_worker_id bigint
)
    RETURNS procrastinate_jobs
    LANGUAGE plpgsql
AS $$
DECLARE
	found_jobs procrastinate_jobs;
BEGIN
    WITH candidate AS (
        SELECT jobs.*
            FROM procrastinate_jobs AS jobs
            WHERE
                -- reject the job if its lock has earlier or higher priority jobs.
                -- Jobs without a lock are accepted before the subquery is considered:
                -- keeping "jobs.lock IS NOT NULL" inside the subquery lets Postgres
                -- plan a nested loop that scans every other job for each NULL-lock job.
                (
                    jobs.lock IS NULL
                    OR NOT EXISTS (
                        SELECT 1
                            FROM procrastinate_jobs AS other_jobs
                            WHERE
                                other_jobs.lock = jobs.lock
                                AND (
                                    -- job with same lock is already running
                                    other_jobs.status = 'doing'
                                    OR
                                    -- job with same lock is waiting and has higher priority (or same priority but was queued first)
                                    (
                                        other_jobs.status = 'todo'
                                        AND (
                                            other_jobs.priority > jobs.priority
                                            OR (
                                            other_jobs.priority = jobs.priority
                                            AND other_jobs.id < jobs.id
                                            )
                                        )
                                    )
                                )
                    )
                )
                AND jobs.status = 'todo'
                AND (target_queue_names IS NULL OR jobs.queue_name = ANY( target_queue_names ))
                AND (jobs.scheduled_at IS NULL OR jobs.scheduled_at <= now())
            ORDER BY jobs.priority DESC, jobs.id ASC LIMIT 1
            FOR UPDATE OF jobs SKIP LOCKED
    )
    UPDATE procrastinate_jobs
        SET status = 'doing', worker_id = p_worker_id
        FROM candidate
        WHERE procrastinate_jobs.id = candidate.id
        RETURNING procrastinate_jobs.* INTO found_jobs;

 RETURN found_jobs;
END;
$$;

CREATE FUNCTION procrastinate_finish_job_v1(job_id bigint, end_status procrastinate_job_status, delete_job boolean)
    RETURNS void
    LANGUAGE plpgsql
AS $$
DECLARE
    _job_id bigint;
BEGIN
    IF end_status NOT IN ('succeeded', 'failed', 'aborted') THEN
        RAISE 'End status should be either "succeeded", "failed" or "aborted" (job id: %)', job_id;
    END IF;
    IF delete_job THEN
        DELETE FROM procrastinate_jobs
        WHERE id = job_id AND status IN ('todo', 'doing')
        RETURNING id INTO _job_id;
    ELSE
        UPDATE procrastinate_jobs
        SET status = end_status,
            abort_requested = false,
            attempts = CASE status
                WHEN 'doing' THEN attempts + 1 ELSE attempts
            END
        WHERE id = job_id AND status IN ('todo', 'doing')
        RETURNING id INTO _job_id;
    END IF;
    IF _job_id IS NULL THEN
        RAISE 'Job was not found or not in "doing" or "todo" status (job id: %)', job_id;
    END IF;
END;
$$;

CREATE FUNCTION procrastinate_cancel_job_v1(job_id bigint, abort boolean, delete_job boolean)
    RETURNS bigint
    LANGUAGE plpgsql
AS $$
DECLARE
    _job_id bigint;
BEGIN
    IF delete_job THEN
        DELETE FROM procrastinate_jobs
        WHERE id = job_id AND status = 'todo'
        RETURNING id INTO _job_id;
    END IF;
    IF _job_id IS NULL THEN
        IF abort THEN
            UPDATE procrastinate_jobs
            SET abort_requested = true,
                status = CASE status
                    WHEN 'todo' THEN 'cancelled'::procrastinate_job_status ELSE status
                END
            WHERE id = job_id AND status IN ('todo', 'doing')
            RETURNING id INTO _job_id;
        ELSE
            UPDATE procrastinate_jobs
            SET status = 'cancelled'::procrastinate_job_status
            WHERE id = job_id AND status = 'todo'
            RETURNING id INTO _job_id;
        END IF;
    END IF;
    RETURN _job_id;
END;
$$;

CREATE FUNCTION procrastinate_retry_job_v1(
    job_id bigint,
    retry_at timestamp with time zone,
    new_priority integer,
    new_queue_name character varying,
    new_lock character varying
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    _job_id bigint;
    _abort_requested boolean;
BEGIN
    SELECT abort_requested FROM procrastinate_jobs
    WHERE id = job_id AND status = 'doing'
    FOR UPDATE
    INTO _abort_requested;
    IF _abort_requested THEN
        UPDATE procrastinate_jobs
        SET status = 'failed'::procrastinate_job_status
        WHERE id = job_id AND status = 'doing'
        RETURNING id INTO _job_id;
    ELSE
        UPDATE procrastinate_jobs
        SET status = 'todo'::procrastinate_job_status,
            attempts = attempts + 1,
            scheduled_at = retry_at,
            priority = COALESCE(new_priority, priority),
            queue_name = COALESCE(new_queue_name, queue_name),
            lock = COALESCE(new_lock, lock)
        WHERE id = job_id AND status = 'doing'
        RETURNING id INTO _job_id;
    END IF;

    IF _job_id IS NULL THEN
        RAISE 'Job was not found or not in "doing" status (job id: %)', job_id;
    END IF;
END;
$$;

CREATE FUNCTION procrastinate_retry_job_v2(
    job_id bigint,
    retry_at timestamp with time zone,
    new_priority integer,
    new_queue_name character varying,
    new_lock character varying
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    _job_id bigint;
    _abort_requested boolean;
    _current_status procrastinate_job_status;
BEGIN
    SELECT status, abort_requested FROM procrastinate_jobs
    WHERE id = job_id AND status IN ('doing', 'failed')
    FOR UPDATE
    INTO _current_status, _abort_requested;
    IF _current_status = 'doing' AND _abort_requested THEN
        UPDATE procrastinate_jobs
        SET status = 'failed'::procrastinate_job_status
        WHERE id = job_id AND status = 'doing'
        RETURNING id INTO _job_id;
    ELSE
        UPDATE procrastinate_jobs
        SET status = 'todo'::procrastinate_job_status,
            attempts = attempts + 1,
            scheduled_at = retry_at,
            priority = COALESCE(new_priority, priority),
            queue_name = COALESCE(new_queue_name, queue_name),
            lock = COALESCE(new_lock, lock)
        WHERE id = job_id AND status IN ('doing', 'failed')
        RETURNING id INTO _job_id;
    END IF;

    IF _job_id IS NULL THEN
        RAISE 'Job was not found or has an invalid status to retry (job id: %)', job_id;
    END IF;

END;
$$;

CREATE FUNCTION procrastinate_notify_queue_job_inserted_v1()
    RETURNS trigger
    LANGUAGE plpgsql
AS $$
DECLARE
    payload TEXT;
BEGIN
    SELECT json_build_object('type', 'job_inserted', 'job_id', NEW.id)::text INTO payload;
	PERFORM pg_notify('procrastinate_queue_v1#' || NEW.queue_name, payload);
	PERFORM pg_notify('procrastinate_any_queue_v1', payload);
	RETURN NEW;
END;
$$;

CREATE FUNCTION procrastinate_notify_queue_abort_job_v1()
RETURNS trigger
    LANGUAGE plpgsql
AS $$
DECLARE
    payload TEXT;
BEGIN
    SELECT json_build_object('type', 'abort_job_requested', 'job_id', NEW.id)::text INTO payload;
	PERFORM pg_notify('procrastinate_queue_v1#' || NEW.queue_name, payload);
	PERFORM pg_notify('procrastinate_any_queue_v1', payload);
	RETURN NEW;
END;
$$;

CREATE FUNCTION procrastinate_trigger_function_status_events_insert_v1()
    RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO procrastinate_events(job_id, type)
        VALUES (NEW.id, 'deferred'::procrastinate_job_event_type);
	RETURN NEW;
END;
$$;

CREATE FUNCTION procrastinate_trigger_function_status_events_update_v1()
    RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    WITH t AS (
        SELECT CASE
            WHEN OLD.status = 'todo'::procrastinate_job_status
                AND NEW.status = 'doing'::procrastinate_job_status
                THEN 'started'::procrastinate_job_event_type
            WHEN OLD.status = 'doing'::procrastinate_job_status
                AND NEW.status = 'todo'::procrastinate_job_status
                THEN 'deferred_for_retry'::procrastinate_job_event_type
            WHEN OLD.status = 'doing'::procrastinate_job_status
                AND NEW.status = 'failed'::procrastinate_job_status
                THEN 'failed'::procrastinate_job_event_type
            WHEN OLD.status = 'doing'::procrastinate_job_status
                AND NEW.status = 'succeeded'::procrastinate_job_status
                THEN 'succeeded'::procrastinate_job_event_type
            WHEN OLD.status = 'todo'::procrastinate_job_status
                AND (
                    NEW.status = 'cancelled'::procrastinate_job_status
                    OR NEW.status = 'failed'::procrastinate_job_status
                    OR NEW.status = 'succeeded'::procrastinate_job_status
                )
                THEN 'cancelled'::procrastinate_job_event_type
            WHEN OLD.status = 'doing'::procrastinate_job_status
                AND NEW.status = 'aborted'::procrastinate_job_status
                THEN 'aborted'::procrastinate_job_event_type
            WHEN OLD.status = 'failed'::procrastinate_job_status
                AND NEW.status = 'todo'::procrastinate_job_status
                THEN 'retried'::procrastinate_job_event_type
            ELSE NULL
        END as event_type
    )
    INSERT INTO procrastinate_events(job_id, type)
        SELECT NEW.id, t.event_type
        FROM t
        WHERE t.event_type IS NOT NULL;
	RETURN NEW;
END;
$$;

CREATE FUNCTION procrastinate_trigger_function_scheduled_events_v1()
    RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO procrastinate_events(job_id, type, at)
        VALUES (NEW.id, 'scheduled'::procrastinate_job_event_type, NEW.scheduled_at);

	RETURN NEW;
END;
$$;

CREATE FUNCTION procrastinate_trigger_abort_requested_events_procedure_v1()
    RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO procrastinate_events(job_id, type)
        VALUES (NEW.id, 'abort_requested'::procrastinate_job_event_type);
    RETURN NEW;
END;
$$;

CREATE FUNCTION procrastinate_unlink_periodic_defers_v1()
    RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE procrastinate_periodic_defers
    SET job_id = NULL
    WHERE job_id = OLD.id;
    RETURN OLD;
END;
$$;

CREATE FUNCTION procrastinate_register_worker_v1()
    RETURNS TABLE(worker_id bigint)
    LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    INSERT INTO procrastinate_workers DEFAULT VALUES
    RETURNING procrastinate_workers.id;
END;
$$;

CREATE FUNCTION procrastinate_unregister_worker_v1(worker_id bigint)
    RETURNS void
    LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM procrastinate_workers
    WHERE id = worker_id;
END;
$$;

CREATE FUNCTION procrastinate_update_heartbeat_v1(worker_id bigint)
    RETURNS void
    LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE procrastinate_workers
    SET last_heartbeat = NOW()
    WHERE id = worker_id;
END;
$$;

CREATE FUNCTION procrastinate_prune_stalled_workers_v1(seconds_since_heartbeat float)
    RETURNS TABLE(worker_id bigint)
    LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    DELETE FROM procrastinate_workers
    WHERE last_heartbeat < NOW() - (seconds_since_heartbeat || 'SECOND')::INTERVAL
    RETURNING procrastinate_workers.id;
END;
$$;

-- Triggers

CREATE TRIGGER procrastinate_jobs_notify_queue_job_inserted_v1
    AFTER INSERT ON procrastinate_jobs
    FOR EACH ROW WHEN ((new.status = 'todo'::procrastinate_job_status))
    EXECUTE PROCEDURE procrastinate_notify_queue_job_inserted_v1();

CREATE TRIGGER procrastinate_jobs_notify_queue_job_aborted_v1
    AFTER UPDATE OF abort_requested ON procrastinate_jobs
    FOR EACH ROW WHEN ((old.abort_requested = false AND new.abort_requested = true AND new.status = 'doing'::procrastinate_job_status))
    EXECUTE PROCEDURE procrastinate_notify_queue_abort_job_v1();

CREATE TRIGGER procrastinate_trigger_status_events_update_v1
    AFTER UPDATE OF status ON procrastinate_jobs
    FOR EACH ROW
    EXECUTE PROCEDURE procrastinate_trigger_function_status_events_update_v1();

CREATE TRIGGER procrastinate_trigger_status_events_insert_v1
    AFTER INSERT ON procrastinate_jobs
    FOR EACH ROW WHEN ((new.status = 'todo'::procrastinate_job_status))
    EXECUTE PROCEDURE procrastinate_trigger_function_status_events_insert_v1();

CREATE TRIGGER procrastinate_trigger_scheduled_events_v1
    AFTER UPDATE OR INSERT ON procrastinate_jobs
    FOR EACH ROW WHEN ((new.scheduled_at IS NOT NULL AND new.status = 'todo'::procrastinate_job_status))
    EXECUTE PROCEDURE procrastinate_trigger_function_scheduled_events_v1();

CREATE TRIGGER procrastinate_trigger_abort_requested_events_v1
    AFTER UPDATE OF abort_requested ON procrastinate_jobs
    FOR EACH ROW WHEN ((new.abort_requested = true))
    EXECUTE PROCEDURE procrastinate_trigger_abort_requested_events_procedure_v1();

CREATE TRIGGER procrastinate_trigger_delete_jobs_v1
    BEFORE DELETE ON procrastinate_jobs
    FOR EACH ROW EXECUTE PROCEDURE procrastinate_unlink_periodic_defers_v1();

-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_coordinator_scratchpad (
      item_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      conversation_id text NOT NULL,
      title text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
      status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','parked','done')),
      notes text NOT NULL DEFAULT '' CHECK (char_length(notes) <= 4000),
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE
    )
-- @statement
CREATE INDEX IF NOT EXISTS ix_coordinator_scratchpad_chat
      ON vault_private.vault_coordinator_scratchpad(user_id,workspace_id,conversation_id,status,updated_at)
-- @statement
CREATE SCHEMA IF NOT EXISTS vault_private
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.external_memory_integrations (
      integration_id text PRIMARY KEY,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      display_name text NOT NULL,
      adapter_kind text NOT NULL,
      token_hash text NOT NULL UNIQUE,
      grants_json jsonb NOT NULL,
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
      created_at timestamptz NOT NULL DEFAULT now(),
      revoked_at timestamptz
    )
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_external_memory_integrations_scope
    ON vault_private.external_memory_integrations (workspace_id, user_id, status)
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.external_memory_pairings (
      pairing_id text PRIMARY KEY,
      pairing_code text NOT NULL UNIQUE,
      poll_token_hash text NOT NULL,
      runtime_token_hash text NOT NULL,
      display_name text NOT NULL,
      adapter_kind text NOT NULL,
      grants_json jsonb NOT NULL,
      status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'expired')),
      integration_id text REFERENCES vault_private.external_memory_integrations(integration_id) ON DELETE SET NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      expires_at timestamptz NOT NULL,
      approved_at timestamptz
    )
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_external_memory_pairings_expiry
    ON vault_private.external_memory_pairings (status, expires_at)
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.external_memory_requests (
      integration_id text NOT NULL REFERENCES vault_private.external_memory_integrations(integration_id) ON DELETE CASCADE,
      request_id text NOT NULL,
      operation text NOT NULL CHECK (operation IN ('search', 'propose')),
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (integration_id, request_id)
    )
    
-- @statement

    ALTER TABLE vault_private.external_memory_requests
      DROP CONSTRAINT IF EXISTS external_memory_requests_operation_check
    
-- @statement

    ALTER TABLE vault_private.external_memory_requests
      ADD CONSTRAINT external_memory_requests_operation_check
      CHECK (operation IN ('search', 'propose', 'correct', 'forget'))
    
-- @statement

    DROP TABLE IF EXISTS
      vault_private.host_filesystem_mounts,
      vault_private.host_filesystem_pairings,
      vault_private.host_filesystem_integrations,
      vault_private.host_filesystem_settings
    CASCADE
    
-- @statement
CREATE SCHEMA IF NOT EXISTS vault_private
-- @statement

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
    
-- @statement

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
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_user_folders_grant
    ON vault_private.user_folders (grant_id)
    
-- @statement

    ALTER TABLE vault_private.folder_grants
      ADD COLUMN IF NOT EXISTS include_hidden boolean NOT NULL DEFAULT false
    
-- @statement

    ALTER TABLE vault_private.user_folders
      ADD COLUMN IF NOT EXISTS include_hidden boolean NOT NULL DEFAULT false
    
-- @statement ["folders_v1", "4dac0f025cdcb92dd61f0d12a227a486446b71bc3a767f0a94e08297b11a4a37"]

        INSERT INTO vault_private.local_schema_metadata (schema_key, schema_fingerprint)
        VALUES (%s, %s)
        ON CONFLICT (schema_key) DO UPDATE SET
          schema_fingerprint = EXCLUDED.schema_fingerprint,
          updated_at = now()
        
-- @statement
CREATE SCHEMA IF NOT EXISTS vault_private
-- @statement

        CREATE TABLE IF NOT EXISTS vault_private.link_companion_pairings (
            pairing_id text PRIMARY KEY,
            pairing_code text NOT NULL UNIQUE,
            display_name text NOT NULL,
            poll_token_hash text NOT NULL,
            status text NOT NULL,
            expires_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        
-- @statement

        CREATE TABLE IF NOT EXISTS vault_private.link_companion_link (
            id integer PRIMARY KEY CHECK (id = 1),
            display_name text NOT NULL,
            pairing_id text NOT NULL,
            paired_at timestamptz NOT NULL DEFAULT now()
        )
        
-- @statement
ALTER TABLE vault_private.link_companion_pairings ADD COLUMN IF NOT EXISTS session_id text
-- @statement
ALTER TABLE vault_private.link_companion_pairings ADD COLUMN IF NOT EXISTS delivery_token text
-- @statement
ALTER TABLE vault_private.link_companion_pairings ADD COLUMN IF NOT EXISTS revoked_at timestamptz
-- @statement
ALTER TABLE vault_private.link_companion_pairings ADD COLUMN IF NOT EXISTS revocation_reason text
-- @statement
ALTER TABLE vault_private.link_companion_link ADD COLUMN IF NOT EXISTS session_id text
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_a2a_connections (
      connection_id text PRIMARY KEY,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      display_name text NOT NULL,
      card_url text NOT NULL,
      rpc_url text NOT NULL,
      agent_card jsonb NOT NULL,
      credential_nonce bytea,
      credential_ciphertext bytea,
      enabled boolean NOT NULL DEFAULT true,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
-- @statement
CREATE INDEX IF NOT EXISTS ix_vault_a2a_connections_scope
       ON vault_private.vault_a2a_connections(workspace_id,user_id,created_at)
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_a2a_conversations (
      connection_id text NOT NULL REFERENCES vault_private.vault_a2a_connections(connection_id) ON DELETE CASCADE,
      user_id text NOT NULL,
      workspace_id text NOT NULL,
      owner_kind text NOT NULL CHECK (owner_kind IN ('voice','background')),
      owner_id text NOT NULL,
      context_id text NOT NULL,
      updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(connection_id,user_id,workspace_id,owner_kind,owner_id)
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_a2a_tasks (
      task_record_id text PRIMARY KEY,
      connection_id text NOT NULL REFERENCES vault_private.vault_a2a_connections(connection_id) ON DELETE CASCADE,
      user_id text NOT NULL,
      workspace_id text NOT NULL,
      owner_kind text NOT NULL CHECK (owner_kind IN ('voice','background')),
      owner_id text NOT NULL,
      remote_task_id text,
      context_id text NOT NULL,
      state text NOT NULL,
      summary text NOT NULL DEFAULT '',
      issue text,
      notified boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      completed_at timestamptz
    )
-- @statement
CREATE INDEX IF NOT EXISTS ix_vault_a2a_tasks_scope_updated
       ON vault_private.vault_a2a_tasks(workspace_id,user_id,updated_at DESC)
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_a2a_inbound (
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      inbound_session_id text NOT NULL REFERENCES vault_private.local_sessions(session_id) ON DELETE CASCADE,
      credential_nonce bytea NOT NULL,
      credential_ciphertext bytea NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (workspace_id, user_id)
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_a2a_inbound_tasks (
      task_id text PRIMARY KEY,
      user_id text NOT NULL,
      workspace_id text NOT NULL,
      local_session_id text NOT NULL,
      run_id text NOT NULL,
      context_id text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )
-- @statement
ALTER TABLE vault_private.vault_a2a_connections
         ADD COLUMN IF NOT EXISTS link_grant_id text
-- @statement
CREATE UNIQUE INDEX IF NOT EXISTS ux_vault_a2a_connections_link_grant
         ON vault_private.vault_a2a_connections(workspace_id,user_id,link_grant_id)
         WHERE link_grant_id IS NOT NULL
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_a2a_link_accept (
      grant_id text NOT NULL,
      user_id text NOT NULL,
      workspace_id text NOT NULL,
      credential_nonce bytea NOT NULL,
      credential_ciphertext bytea NOT NULL,
      PRIMARY KEY (workspace_id, user_id, grant_id)
    )
-- @statement ["agent_network_a2a_v1", "0dcbbda884e30198109744ead47c63df15384fb2c5083faeb4358896b1568915"]
INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
           VALUES (%s,%s) ON CONFLICT(schema_key) DO UPDATE SET
           schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_background_runs (
      run_id text PRIMARY KEY,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      local_session_id text NOT NULL REFERENCES vault_private.local_sessions(session_id) ON DELETE CASCADE,
      request_json jsonb NOT NULL,
      state text NOT NULL CHECK (state IN ('accepted','queued','running','reviewing','repairing','completed','failed','cancelled')),
      cancellation_requested boolean NOT NULL DEFAULT false,
      output_json jsonb,
      failure_code text,
      failure_message text,
      model_turns integer NOT NULL DEFAULT 0 CHECK (model_turns >= 0),
      tool_calls integer NOT NULL DEFAULT 0 CHECK (tool_calls >= 0),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      completed_at timestamptz
    )
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_background_runs_scope_created
    ON vault_private.vault_background_runs (workspace_id,user_id,created_at DESC)
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_background_run_events (
      run_id text NOT NULL REFERENCES vault_private.vault_background_runs(run_id) ON DELETE CASCADE,
      event_index integer NOT NULL CHECK (event_index >= 0),
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      event_type text NOT NULL,
      state text NOT NULL CHECK (state IN ('accepted','queued','running','reviewing','repairing','completed','failed','cancelled')),
      detail_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (run_id,event_index)
    )
    
-- @statement ["background_agent_v1", "cb75e8d62075a1162ba0c2a58003fd6b9341d881c120d85b60ee922140ec49fd"]

        INSERT INTO vault_private.local_schema_metadata (schema_key,schema_fingerprint)
        VALUES (%s,%s) ON CONFLICT (schema_key) DO UPDATE SET
          schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
        
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_execution_grants (
      grant_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      purpose text NOT NULL, policy_json jsonb NOT NULL CHECK (jsonb_typeof(policy_json)='object'),
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked')),
      version integer NOT NULL DEFAULT 1 CHECK (version>0), expires_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,grant_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_workers (
      worker_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      role_key text NOT NULL, spec_json jsonb NOT NULL CHECK (jsonb_typeof(spec_json)='object'),
      spec_hash text NOT NULL CHECK (length(spec_hash)=64), grant_id text,
      generation integer NOT NULL DEFAULT 1 CHECK (generation>0),
      status text NOT NULL DEFAULT 'idle' CHECK (status IN ('idle','active','paused','deleted')),
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,worker_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,grant_id) REFERENCES vault_private.vault_background_execution_grants(user_id,workspace_id,grant_id)
    )
-- @statement
CREATE UNIQUE INDEX IF NOT EXISTS uq_background_worker_role
       ON vault_private.vault_background_workers(user_id,workspace_id,role_key) WHERE status<>'deleted'
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_routines (
      routine_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      version integer NOT NULL DEFAULT 1 CHECK (version>0), rule_json jsonb NOT NULL,
      timezone text NOT NULL, next_due_at timestamptz, grant_id text NOT NULL, template_json jsonb NOT NULL,
      status text NOT NULL DEFAULT 'paused' CHECK (status IN ('active','paused','deleted')),
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,routine_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,grant_id) REFERENCES vault_private.vault_background_execution_grants(user_id,workspace_id,grant_id)
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_work (
      work_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      source_key text NOT NULL, intent_version integer NOT NULL DEFAULT 1 CHECK (intent_version>0),
      request_json jsonb NOT NULL CHECK (jsonb_typeof(request_json)='object'),
      state text NOT NULL DEFAULT 'proposed' CHECK (state IN ('proposed','ready','queued','running','waiting_approval','waiting_input','waiting_event','completed','failed','cancelled','unknown')),
      worker_id text, worker_generation integer, local_session_id text REFERENCES vault_private.local_sessions(session_id),
      grant_id text, task_id text, parent_work_id text, routine_id text,
      result_json jsonb, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      CHECK ((local_session_id IS NOT NULL) <> (grant_id IS NOT NULL)),
      CHECK ((worker_id IS NULL)=(worker_generation IS NULL)),
      UNIQUE(user_id,workspace_id,work_id), UNIQUE(user_id,workspace_id,source_key),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,worker_id) REFERENCES vault_private.vault_background_workers(user_id,workspace_id,worker_id),
      FOREIGN KEY(user_id,workspace_id,grant_id) REFERENCES vault_private.vault_background_execution_grants(user_id,workspace_id,grant_id),
      FOREIGN KEY(user_id,workspace_id,parent_work_id) REFERENCES vault_private.vault_background_work(user_id,workspace_id,work_id),
      FOREIGN KEY(user_id,workspace_id,routine_id) REFERENCES vault_private.vault_background_routines(user_id,workspace_id,routine_id)
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_sessions (
      session_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      worker_id text NOT NULL, work_id text NOT NULL, worker_generation integer NOT NULL CHECK (worker_generation>0),
      intent_version integer NOT NULL CHECK (intent_version>0), provider_key text, model_id text, adapter_version text,
      checkpoint_version integer NOT NULL DEFAULT 1, checkpoint_json jsonb,
      history_json jsonb NOT NULL DEFAULT '[]'::jsonb, source_refs_json jsonb NOT NULL DEFAULT '[]'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,session_id), UNIQUE(user_id,workspace_id,work_id,intent_version),
      CHECK ((provider_key IS NULL AND model_id IS NULL AND adapter_version IS NULL) OR
             (provider_key IS NOT NULL AND model_id IS NOT NULL AND adapter_version IS NOT NULL)),
      FOREIGN KEY(user_id,workspace_id,worker_id) REFERENCES vault_private.vault_background_workers(user_id,workspace_id,worker_id),
      FOREIGN KEY(user_id,workspace_id,work_id) REFERENCES vault_private.vault_background_work(user_id,workspace_id,work_id) ON DELETE CASCADE
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_occurrences (
      occurrence_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      routine_id text NOT NULL, routine_version integer NOT NULL, scheduled_for timestamptz NOT NULL, work_id text,
      UNIQUE(user_id,workspace_id,routine_id,routine_version,scheduled_for),
      FOREIGN KEY(user_id,workspace_id,routine_id) REFERENCES vault_private.vault_background_routines(user_id,workspace_id,routine_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,work_id) REFERENCES vault_private.vault_background_work(user_id,workspace_id,work_id)
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_events (
      event_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      source_kind text NOT NULL, source_id text NOT NULL, payload_json jsonb NOT NULL,
      state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','processed','cancelled')),
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,source_kind,source_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_background_actions (
      action_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      work_id text, intent_version integer, worker_generation integer, kind text NOT NULL,
      origin_json jsonb NOT NULL DEFAULT '{}'::jsonb, action_hash text NOT NULL CHECK (length(action_hash)=64),
      domain_ref text, resource_version text, arguments_json jsonb NOT NULL,
      title text NOT NULL, detail text NOT NULL, expires_at timestamptz NOT NULL,
      state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','approved','denied','expired','executing','completed','failed','unknown')),
      decision_id text, actor_user_id text, channel text, channel_generation text, receipt_json jsonb,
      operation_key text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      -- Owner approvals (2026-11-17): an approval asked during an interactive Chat turn or Voice call.
      -- Added inside CREATE TABLE before the first install had this table; later changes are migrations.
      origin_conversation_id text, origin_turn_id text, origin_voice_session_id text, origin_tool_call_id text,
      detail_lines jsonb NOT NULL DEFAULT '[]'::jsonb,
      CHECK ((origin_turn_id IS NULL)=(origin_conversation_id IS NULL)),
      CHECK ((origin_turn_id IS NOT NULL OR origin_voice_session_id IS NOT NULL)=(kind='owner_approval')),
      CHECK (kind<>'owner_approval' OR (work_id IS NULL AND origin_tool_call_id IS NOT NULL
             AND (origin_turn_id IS NULL)<>(origin_voice_session_id IS NULL))),
      CHECK (work_id IS NOT NULL OR kind IN ('worker_create','execution_grant','routine_create','owner_approval')),
      CHECK (actor_user_id IS NULL OR actor_user_id=user_id),
      UNIQUE(user_id,workspace_id,action_id), UNIQUE(user_id,workspace_id,operation_key),
      UNIQUE(user_id,workspace_id,decision_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,work_id) REFERENCES vault_private.vault_background_work(user_id,workspace_id,work_id)
    )
-- @statement
CREATE UNIQUE INDEX IF NOT EXISTS ux_owner_approval_pending ON vault_private.vault_background_actions(user_id,workspace_id)
      WHERE kind='owner_approval' AND state='pending'
-- @statement
CREATE INDEX IF NOT EXISTS ix_background_due ON vault_private.vault_background_routines(next_due_at) WHERE status='active'
-- @statement
CREATE INDEX IF NOT EXISTS ix_background_work_scope_state ON vault_private.vault_background_work(user_id,workspace_id,state,created_at)
-- @statement
ALTER TABLE vault_private.vault_background_runs ALTER COLUMN local_session_id DROP NOT NULL
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS work_id text
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS coordination_session_id text
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS execution_grant_id text
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS attempt_generation bigint NOT NULL DEFAULT 0
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS checkpoint_json jsonb
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS active_seconds double precision NOT NULL DEFAULT 0
-- @statement
ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS first_started_at timestamptz
-- @statement
DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_background_run_authority'
                     AND conrelid='vault_private.vault_background_runs'::regclass) THEN
        ALTER TABLE vault_private.vault_background_runs ADD CONSTRAINT ck_background_run_authority
          CHECK ((local_session_id IS NOT NULL) <> (execution_grant_id IS NOT NULL));
        ALTER TABLE vault_private.vault_background_runs ADD CONSTRAINT fk_background_run_work
          FOREIGN KEY(user_id,workspace_id,work_id) REFERENCES vault_private.vault_background_work(user_id,workspace_id,work_id);
        ALTER TABLE vault_private.vault_background_runs ADD CONSTRAINT fk_background_run_session
          FOREIGN KEY(user_id,workspace_id,coordination_session_id) REFERENCES vault_private.vault_background_sessions(user_id,workspace_id,session_id);
        ALTER TABLE vault_private.vault_background_runs ADD CONSTRAINT fk_background_run_grant
          FOREIGN KEY(user_id,workspace_id,execution_grant_id) REFERENCES vault_private.vault_background_execution_grants(user_id,workspace_id,grant_id);
      END IF;
    END $$
-- @statement ["993aee392f9be696456c2d3b2f435c5af49f1806a7977d9dd2ab0b9182d6ee7e"]
INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
        VALUES ('background_coordination_v1',%s) ON CONFLICT(schema_key) DO UPDATE SET
        schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement

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
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_workspace_folder_shares_grantee
    ON vault_private.vault_workspace_folder_shares (grantee_user_id, status)
    
-- @statement

    ALTER TABLE vault_private.vault_workspace_folder_shares
    ADD COLUMN IF NOT EXISTS share_kind text NOT NULL DEFAULT 'folder'
    
-- @statement

    ALTER TABLE vault_private.vault_workspace_folder_shares
    ADD COLUMN IF NOT EXISTS share_mount_name text
    
-- @statement

    UPDATE vault_private.vault_workspace_folder_shares
    SET share_mount_name = split_part(folder_path, '/', array_length(string_to_array(folder_path, '/'), 1))
    WHERE share_mount_name IS NULL OR share_mount_name = ''
    
-- @statement

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
    
-- @step workspace_file_projections
-- @statement
DROP TABLE IF EXISTS vault_private.vault_workspace_file_projections
-- @statement
CREATE SCHEMA IF NOT EXISTS vault_private
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.vault_settings (
      setting_key text PRIMARY KEY,
      value jsonb NOT NULL,
      updated_by text REFERENCES vault_private.local_users(user_id) ON DELETE SET NULL,
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    
-- @statement

    CREATE TABLE IF NOT EXISTS vault_private.command_requests (
      request_id text PRIMARY KEY,
      user_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL,
      agent text NOT NULL CHECK (agent IN ('chat', 'background')),
      conversation_id text,
      directory text NOT NULL,
      command text NOT NULL,
      state text NOT NULL CHECK (state IN ('pending', 'approved', 'denied', 'running', 'completed', 'expired', 'failed')),
      outcome jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      decided_at timestamptz,
      completed_at timestamptz,
      expires_at timestamptz NOT NULL
    )
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_command_requests_conversation
    ON vault_private.command_requests (user_id, conversation_id, state)
    
-- @statement

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
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_conversations_scope_updated
    ON vault_private.vault_conversations (user_id,workspace_id,updated_at DESC,conversation_id)
    
-- @statement

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
    
-- @statement

    CREATE UNIQUE INDEX IF NOT EXISTS uq_vault_conversation_open_segment
    ON vault_private.vault_conversation_segments (user_id,workspace_id,conversation_id)
    WHERE state='open'
    
-- @statement

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
    
-- @statement
ALTER TABLE vault_private.vault_conversation_turns ADD COLUMN IF NOT EXISTS explicit_remember boolean NOT NULL DEFAULT false
-- @statement ["conversation_v1", "ce701b9fbb951d965b5b17afaa6694b8421d1238c61e9900e7b05223579f3475"]
INSERT INTO vault_private.local_schema_metadata (schema_key,schema_fingerprint)
           VALUES (%s,%s) ON CONFLICT (schema_key) DO UPDATE SET
             schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement
ALTER TABLE vault_private.vault_conversations
       ADD COLUMN IF NOT EXISTS source_voice_session_id text,
       ADD COLUMN IF NOT EXISTS activity_at timestamptz,
       ADD COLUMN IF NOT EXISTS activity_session_id text
-- @statement
ALTER TABLE vault_private.vault_conversation_segments
       ADD COLUMN IF NOT EXISTS first_review_ordinal bigint,
       ADD COLUMN IF NOT EXISTS last_review_ordinal bigint,
       ADD COLUMN IF NOT EXISTS memory_review_result_json jsonb,
       ADD COLUMN IF NOT EXISTS decision_review_result_json jsonb,
       ADD COLUMN IF NOT EXISTS memory_review_state text NOT NULL DEFAULT 'not_requested'
         CHECK(memory_review_state IN ('not_requested','pending','completed','failed','disabled')),
       ADD COLUMN IF NOT EXISTS decision_review_state text NOT NULL DEFAULT 'not_requested'
         CHECK(decision_review_state IN ('not_requested','pending','completed','failed','disabled'))
-- @statement
ALTER TABLE vault_private.vault_conversation_segments
       ADD COLUMN IF NOT EXISTS review_state text NOT NULL DEFAULT 'not_requested'
         CHECK(review_state IN ('not_requested','queued','running','completed','failed','blocked_authority')),
       ADD COLUMN IF NOT EXISTS review_session_id text,
       ADD COLUMN IF NOT EXISTS review_attempts integer NOT NULL DEFAULT 0,
       ADD COLUMN IF NOT EXISTS review_due_at timestamptz NOT NULL DEFAULT now()
-- @statement
CREATE INDEX IF NOT EXISTS idx_conversation_review_due
       ON vault_private.vault_conversation_segments(review_due_at)
       WHERE review_state IN ('queued','running') AND state='sealed'
-- @statement
ALTER TABLE vault_private.vault_conversation_turns
       ADD COLUMN IF NOT EXISTS run_owner text,
       ADD COLUMN IF NOT EXISTS cancel_requested boolean NOT NULL DEFAULT false,
       ADD COLUMN IF NOT EXISTS source_coverage text NOT NULL DEFAULT 'unknown'
         CHECK(source_coverage IN ('unknown','complete','incomplete')),
       ADD COLUMN IF NOT EXISTS event_sequence bigint NOT NULL DEFAULT 0,
       ADD COLUMN IF NOT EXISTS event_bytes bigint NOT NULL DEFAULT 0
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_conversation_events (
       user_id text NOT NULL,workspace_id text NOT NULL,conversation_id text NOT NULL,
       turn_id text NOT NULL,sequence bigint NOT NULL CHECK(sequence>0),
       kind text NOT NULL CHECK(kind IN ('waiting','context','model_response','tool_status',
         'text_delta','assistant_final','error','terminal','ui_hint','ui','title')),
       payload jsonb NOT NULL CHECK(octet_length(payload::text)<=131072),
       created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(turn_id,sequence),
       FOREIGN KEY(user_id,workspace_id,conversation_id,turn_id) REFERENCES
         vault_private.vault_conversation_turns(user_id,workspace_id,conversation_id,turn_id) ON DELETE CASCADE)
-- @statement
DO $$ BEGIN
       IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='vault_conversation_events_kind_check'
         AND conrelid='vault_private.vault_conversation_events'::regclass
         AND pg_get_constraintdef(oid) LIKE '%''title''%') THEN
         ALTER TABLE vault_private.vault_conversation_events DROP CONSTRAINT IF EXISTS vault_conversation_events_kind_check;
         ALTER TABLE vault_private.vault_conversation_events ADD CONSTRAINT vault_conversation_events_kind_check
           CHECK(kind IN ('waiting','context','model_response','tool_status','text_delta','assistant_final',
             'error','terminal','ui_hint','ui','title'));
       END IF; END $$
-- @statement
ALTER TABLE vault_private.vault_voice_tool_invocations
       ALTER COLUMN voice_session_id DROP NOT NULL,
       ADD COLUMN IF NOT EXISTS conversation_id text,
       ADD COLUMN IF NOT EXISTS turn_id text
-- @statement
CREATE UNIQUE INDEX IF NOT EXISTS uq_tool_invocation_conversation_call
       ON vault_private.vault_voice_tool_invocations(conversation_id,turn_id,tool_call_id)
-- @statement
DO $$ BEGIN
       IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='fk_tool_invocation_conversation_turn'
         AND conrelid='vault_private.vault_voice_tool_invocations'::regclass) THEN
         ALTER TABLE vault_private.vault_voice_tool_invocations ADD CONSTRAINT fk_tool_invocation_conversation_turn
         FOREIGN KEY(user_id,workspace_id,conversation_id,turn_id) REFERENCES
           vault_private.vault_conversation_turns(user_id,workspace_id,conversation_id,turn_id) ON DELETE CASCADE;
       END IF;
       IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='ck_tool_invocation_channel'
         AND conrelid='vault_private.vault_voice_tool_invocations'::regclass) THEN
         ALTER TABLE vault_private.vault_voice_tool_invocations ADD CONSTRAINT ck_tool_invocation_channel CHECK(
           (voice_session_id IS NOT NULL AND conversation_id IS NULL AND turn_id IS NULL) OR
           (voice_session_id IS NULL AND conversation_id IS NOT NULL AND turn_id IS NOT NULL));
       END IF; END $$
-- @statement
CREATE UNIQUE INDEX IF NOT EXISTS uq_voice_session_review_scope
      ON vault_private.vault_voice_sessions(user_id,workspace_id,voice_session_id)
-- @statement
ALTER TABLE vault_private.vault_conversations
      ADD COLUMN IF NOT EXISTS source_voice_session_id text
-- @statement
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE
      conname='fk_conversation_voice_review_source' AND conrelid='vault_private.vault_conversations'::regclass)
      THEN ALTER TABLE vault_private.vault_conversations ADD CONSTRAINT fk_conversation_voice_review_source
      FOREIGN KEY(user_id,workspace_id,source_voice_session_id) REFERENCES
        vault_private.vault_voice_sessions(user_id,workspace_id,voice_session_id) ON DELETE CASCADE;
      END IF; END $$
-- @statement ["voice_decision_review_bridge_v1", "67d76e694e455e1c6930960e4219ffe975fa0ebc95c0cce1312c5d065431c2dc"]
INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
      VALUES (%s,%s) ON CONFLICT(schema_key) DO UPDATE SET
      schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement ["conversation_runtime_v1", "574a1e1b3347c3c9af5ab9a5c08d240edf2bf562c59898446e961d8810ff9f75"]
INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
      VALUES(%s,%s) ON CONFLICT(schema_key) DO UPDATE SET
      schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_genui_feedback (
       feedback_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
       conversation_id text NOT NULL, turn_id text NOT NULL,
       verdict text CHECK(verdict IN ('up','down')), chosen_layout text,
       predicted jsonb, shown jsonb NOT NULL DEFAULT '[]'::jsonb, previews jsonb,
       embedding jsonb, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
       UNIQUE(user_id,workspace_id,turn_id),
       FOREIGN KEY(user_id,workspace_id,conversation_id,turn_id) REFERENCES
         vault_private.vault_conversation_turns(user_id,workspace_id,conversation_id,turn_id) ON DELETE CASCADE)
-- @statement
CREATE INDEX IF NOT EXISTS idx_genui_feedback_scope
       ON vault_private.vault_genui_feedback(user_id,workspace_id,updated_at DESC)
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_genui_presentation_config (
       user_id text NOT NULL, workspace_id text NOT NULL, version integer NOT NULL CHECK(version>0),
       config jsonb NOT NULL, state text NOT NULL CHECK(state IN ('active','undone')),
       notice jsonb, notice_pending boolean NOT NULL DEFAULT false,
       created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(user_id,workspace_id,version))
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_conversation_attachments (
              attachment_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
              conversation_id text NOT NULL, upload_key text NOT NULL, name text NOT NULL,
              mime text NOT NULL, content_hash text NOT NULL, size_bytes integer NOT NULL,
              extracted_text text, coverage text NOT NULL, turn_id text,
              created_at timestamptz NOT NULL DEFAULT now(),
              UNIQUE(user_id,workspace_id,conversation_id,upload_key),
              FOREIGN KEY(user_id,workspace_id,conversation_id) REFERENCES
                vault_private.vault_conversations(user_id,workspace_id,conversation_id) ON DELETE CASCADE,
              FOREIGN KEY(user_id,workspace_id,conversation_id,turn_id) REFERENCES
                vault_private.vault_conversation_turns(user_id,workspace_id,conversation_id,turn_id) ON DELETE CASCADE
            )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_chat_memory_reviews (
          user_id text NOT NULL, workspace_id text NOT NULL, conversation_id text NOT NULL,
          segment_id text NOT NULL, source_fingerprint text NOT NULL CHECK(length(source_fingerprint)=64),
          reviewer_model text NOT NULL, reviewer_contract_version integer NOT NULL,
          summary text NOT NULL, dispositions_json jsonb NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY(user_id,workspace_id,conversation_id,segment_id),
          FOREIGN KEY(user_id,workspace_id,conversation_id,segment_id) REFERENCES
            vault_private.vault_conversation_segments(user_id,workspace_id,conversation_id,segment_id)
            ON DELETE CASCADE)
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_chat_memory_analysis_steps (
              user_id text NOT NULL,workspace_id text NOT NULL,conversation_id text NOT NULL,segment_id text NOT NULL,
              step_key text NOT NULL,source_fingerprint text NOT NULL,input_fingerprint text NOT NULL,
              provider text NOT NULL,model text NOT NULL,analysis_contract integer NOT NULL,
              output_json jsonb NOT NULL CHECK(octet_length(output_json::text)<=1048576),
              PRIMARY KEY(user_id,workspace_id,conversation_id,segment_id,step_key),
              FOREIGN KEY(user_id,workspace_id,conversation_id,segment_id) REFERENCES
                vault_private.vault_conversation_segments(user_id,workspace_id,conversation_id,segment_id) ON DELETE CASCADE)
-- @statement
ALTER TABLE vault_private.vault_chat_memory_reviews ADD COLUMN IF NOT EXISTS state text NOT NULL DEFAULT 'completed' CHECK(state IN ('reviewed','completed'))
-- @statement
ALTER TABLE vault_private.vault_chat_memory_reviews ADD COLUMN IF NOT EXISTS provider text
-- @statement
ALTER TABLE vault_private.vault_chat_memory_reviews ADD COLUMN IF NOT EXISTS review_json jsonb
-- @statement
ALTER TABLE vault_private.vault_chat_memory_reviews ADD COLUMN IF NOT EXISTS coverage_json jsonb
-- @statement ["b76693c6c1574fed51d41376e53a2f8dd9926a04072a9ea6f700434a26f67ae9"]
INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
              VALUES('chat_memory_reviews_v1',%s) ON CONFLICT(schema_key) DO UPDATE SET
              schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement

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
    
-- @statement

    CREATE INDEX IF NOT EXISTS ix_vault_conversations_scope_updated
    ON vault_private.vault_conversations (user_id,workspace_id,updated_at DESC,conversation_id)
    
-- @statement

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
    
-- @statement

    CREATE UNIQUE INDEX IF NOT EXISTS uq_vault_conversation_open_segment
    ON vault_private.vault_conversation_segments (user_id,workspace_id,conversation_id)
    WHERE state='open'
    
-- @statement

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
    
-- @statement
ALTER TABLE vault_private.vault_conversation_turns ADD COLUMN IF NOT EXISTS explicit_remember boolean NOT NULL DEFAULT false
-- @statement ["conversation_v1", "ce701b9fbb951d965b5b17afaa6694b8421d1238c61e9900e7b05223579f3475"]
INSERT INTO vault_private.local_schema_metadata (schema_key,schema_fingerprint)
           VALUES (%s,%s) ON CONFLICT (schema_key) DO UPDATE SET
             schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_decision_reviews (
      review_id text PRIMARY KEY,
      user_id text NOT NULL,
      workspace_id text NOT NULL,
      conversation_id text NOT NULL,
      segment_id text NOT NULL,
      source_snapshot_fingerprint text NOT NULL CHECK (source_snapshot_fingerprint ~ '^[0-9a-f]{64}$'),
      learner_contract_version integer NOT NULL CHECK (learner_contract_version > 0),
      provider text NOT NULL DEFAULT '',
      model text NOT NULL DEFAULT '',
      state text NOT NULL CHECK (state IN ('queued','running','retryable','failed','completed')),
      lease_owner text,
      lease_until timestamptz,
      attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
      proposals_json jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(proposals_json)='array'),
      source_coverage_json jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(source_coverage_json)='object'),
      output_fingerprint text CHECK (output_fingerprint IS NULL OR output_fingerprint ~ '^[0-9a-f]{64}$'),
      error_code text,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      completed_at timestamptz,
      UNIQUE(user_id,workspace_id,conversation_id,segment_id,source_snapshot_fingerprint,learner_contract_version),
      FOREIGN KEY(user_id,workspace_id,conversation_id,segment_id)
        REFERENCES vault_private.vault_conversation_segments(user_id,workspace_id,conversation_id,segment_id)
        ON DELETE CASCADE,
      CHECK (state <> 'running' OR (lease_owner IS NOT NULL AND lease_until IS NOT NULL)),
      CHECK ((state='completed') = (completed_at IS NOT NULL)),
      CHECK (state <> 'completed' OR output_fingerprint IS NOT NULL)
    )
-- @statement
ALTER TABLE vault_private.vault_decision_reviews ADD COLUMN IF NOT EXISTS assessments_json
      jsonb NOT NULL DEFAULT '[]'::jsonb CHECK(jsonb_typeof(assessments_json)='array')
-- @statement
CREATE INDEX IF NOT EXISTS ix_vault_decision_reviews_scope_lease
       ON vault_private.vault_decision_reviews(user_id,workspace_id,state,lease_until)
-- @statement ["dab0bee2855a4fed529ce9e25403423b289e58c99d05f06d072145726f5e68a2"]
INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
      VALUES ('decision_reviews_v1',%s) ON CONFLICT(schema_key) DO UPDATE SET
      schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement
CREATE EXTENSION IF NOT EXISTS vector
-- @statement
CREATE UNIQUE INDEX IF NOT EXISTS uq_vault_decision_review_scope_id
       ON vault_private.vault_decision_reviews(user_id,workspace_id,review_id)
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_decision_generations (
      generation_id text PRIMARY KEY,user_id text NOT NULL,workspace_id text NOT NULL,
      review_id text NOT NULL,schema_version integer NOT NULL CHECK(schema_version>0),
      compiler_version text NOT NULL,source_snapshot_fingerprint text NOT NULL
        CHECK(source_snapshot_fingerprint ~ '^[0-9a-f]{64}$'),
      state text NOT NULL CHECK(state IN ('building','validated','active','retired','failed')),
      created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,generation_id),UNIQUE(user_id,workspace_id,review_id),
      FOREIGN KEY(user_id,workspace_id,review_id)
        REFERENCES vault_private.vault_decision_reviews(user_id,workspace_id,review_id) ON DELETE CASCADE
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_decision_definitions (
      definition_id text NOT NULL,generation_id text NOT NULL,version integer NOT NULL CHECK(version>0),
      user_id text NOT NULL,workspace_id text NOT NULL,decision_key text NOT NULL,
      conditions_json jsonb NOT NULL CHECK(jsonb_typeof(conditions_json)='object'),
      required_slots_json jsonb NOT NULL CHECK(jsonb_typeof(required_slots_json)='array'),
      capability_refs_json jsonb NOT NULL CHECK(jsonb_typeof(capability_refs_json)='array'),
      action_description text NOT NULL,exclusions_json jsonb NOT NULL CHECK(jsonb_typeof(exclusions_json)='array'),
      status text NOT NULL CHECK(status IN ('proposed','active','inactive')),
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(user_id,workspace_id,generation_id,definition_id,version),
      UNIQUE(user_id,workspace_id,generation_id,decision_key,version),
      FOREIGN KEY(user_id,workspace_id,generation_id)
        REFERENCES vault_private.vault_decision_generations(user_id,workspace_id,generation_id) ON DELETE CASCADE
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_decision_examples (
      example_id text PRIMARY KEY,user_id text NOT NULL,workspace_id text NOT NULL,
      generation_id text NOT NULL,definition_id text NOT NULL,definition_version integer NOT NULL,
      example_text text NOT NULL,example_kind text NOT NULL CHECK(example_kind IN ('observed','synthetic','counterexample')),
      outcome_class text NOT NULL CHECK(outcome_class IN ('resolved','corrected','unresolved','unknown')),
      source_set_fingerprint text NOT NULL CHECK(source_set_fingerprint ~ '^[0-9a-f]{64}$'),
      source_review_id text NOT NULL,enabled boolean NOT NULL DEFAULT true,
      provider text,model text,dimensions integer,embedding vector,embedding_fingerprint text,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,generation_id,definition_id,definition_version,example_kind,source_set_fingerprint),
      FOREIGN KEY(user_id,workspace_id,generation_id,definition_id,definition_version)
        REFERENCES vault_private.vault_decision_definitions(user_id,workspace_id,generation_id,definition_id,version)
        ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,source_review_id)
        REFERENCES vault_private.vault_decision_reviews(user_id,workspace_id,review_id) ON DELETE CASCADE,
      CHECK((embedding IS NULL AND provider IS NULL AND model IS NULL AND dimensions IS NULL AND embedding_fingerprint IS NULL)
        OR (embedding IS NOT NULL AND provider IS NOT NULL AND model IS NOT NULL AND dimensions IS NOT NULL AND dimensions>0
          AND vector_dims(embedding)=dimensions AND embedding_fingerprint IS NOT NULL
          AND embedding_fingerprint ~ '^[0-9a-f]{64}$'))
    )
-- @statement
CREATE INDEX IF NOT EXISTS ix_vault_decision_definition_scope
       ON vault_private.vault_decision_definitions(user_id,workspace_id,generation_id,status,decision_key)
-- @statement
CREATE INDEX IF NOT EXISTS ix_vault_decision_example_scope
       ON vault_private.vault_decision_examples(user_id,workspace_id,generation_id,definition_id,enabled)
-- @statement ["fb77ae9be2e576b2f79068e85b97a5fb8754c6545bccc9cdf878a6945cc62f98"]
INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
      VALUES ('decision_rules_v1',%s) ON CONFLICT(schema_key) DO UPDATE SET
      schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_decision_reviews (
      review_id text PRIMARY KEY,
      user_id text NOT NULL,
      workspace_id text NOT NULL,
      conversation_id text NOT NULL,
      segment_id text NOT NULL,
      source_snapshot_fingerprint text NOT NULL CHECK (source_snapshot_fingerprint ~ '^[0-9a-f]{64}$'),
      learner_contract_version integer NOT NULL CHECK (learner_contract_version > 0),
      provider text NOT NULL DEFAULT '',
      model text NOT NULL DEFAULT '',
      state text NOT NULL CHECK (state IN ('queued','running','retryable','failed','completed')),
      lease_owner text,
      lease_until timestamptz,
      attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
      proposals_json jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(proposals_json)='array'),
      source_coverage_json jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(source_coverage_json)='object'),
      output_fingerprint text CHECK (output_fingerprint IS NULL OR output_fingerprint ~ '^[0-9a-f]{64}$'),
      error_code text,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      completed_at timestamptz,
      UNIQUE(user_id,workspace_id,conversation_id,segment_id,source_snapshot_fingerprint,learner_contract_version),
      FOREIGN KEY(user_id,workspace_id,conversation_id,segment_id)
        REFERENCES vault_private.vault_conversation_segments(user_id,workspace_id,conversation_id,segment_id)
        ON DELETE CASCADE,
      CHECK (state <> 'running' OR (lease_owner IS NOT NULL AND lease_until IS NOT NULL)),
      CHECK ((state='completed') = (completed_at IS NOT NULL)),
      CHECK (state <> 'completed' OR output_fingerprint IS NOT NULL)
    )
-- @statement
ALTER TABLE vault_private.vault_decision_reviews ADD COLUMN IF NOT EXISTS assessments_json
      jsonb NOT NULL DEFAULT '[]'::jsonb CHECK(jsonb_typeof(assessments_json)='array')
-- @statement
CREATE INDEX IF NOT EXISTS ix_vault_decision_reviews_scope_lease
       ON vault_private.vault_decision_reviews(user_id,workspace_id,state,lease_until)
-- @statement ["dab0bee2855a4fed529ce9e25403423b289e58c99d05f06d072145726f5e68a2"]
INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
      VALUES ('decision_reviews_v1',%s) ON CONFLICT(schema_key) DO UPDATE SET
      schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement
CREATE EXTENSION IF NOT EXISTS vector
-- @statement
CREATE UNIQUE INDEX IF NOT EXISTS uq_vault_decision_review_scope_id
       ON vault_private.vault_decision_reviews(user_id,workspace_id,review_id)
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_decision_generations (
      generation_id text PRIMARY KEY,user_id text NOT NULL,workspace_id text NOT NULL,
      review_id text NOT NULL,schema_version integer NOT NULL CHECK(schema_version>0),
      compiler_version text NOT NULL,source_snapshot_fingerprint text NOT NULL
        CHECK(source_snapshot_fingerprint ~ '^[0-9a-f]{64}$'),
      state text NOT NULL CHECK(state IN ('building','validated','active','retired','failed')),
      created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,generation_id),UNIQUE(user_id,workspace_id,review_id),
      FOREIGN KEY(user_id,workspace_id,review_id)
        REFERENCES vault_private.vault_decision_reviews(user_id,workspace_id,review_id) ON DELETE CASCADE
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_decision_definitions (
      definition_id text NOT NULL,generation_id text NOT NULL,version integer NOT NULL CHECK(version>0),
      user_id text NOT NULL,workspace_id text NOT NULL,decision_key text NOT NULL,
      conditions_json jsonb NOT NULL CHECK(jsonb_typeof(conditions_json)='object'),
      required_slots_json jsonb NOT NULL CHECK(jsonb_typeof(required_slots_json)='array'),
      capability_refs_json jsonb NOT NULL CHECK(jsonb_typeof(capability_refs_json)='array'),
      action_description text NOT NULL,exclusions_json jsonb NOT NULL CHECK(jsonb_typeof(exclusions_json)='array'),
      status text NOT NULL CHECK(status IN ('proposed','active','inactive')),
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(user_id,workspace_id,generation_id,definition_id,version),
      UNIQUE(user_id,workspace_id,generation_id,decision_key,version),
      FOREIGN KEY(user_id,workspace_id,generation_id)
        REFERENCES vault_private.vault_decision_generations(user_id,workspace_id,generation_id) ON DELETE CASCADE
    )
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_decision_examples (
      example_id text PRIMARY KEY,user_id text NOT NULL,workspace_id text NOT NULL,
      generation_id text NOT NULL,definition_id text NOT NULL,definition_version integer NOT NULL,
      example_text text NOT NULL,example_kind text NOT NULL CHECK(example_kind IN ('observed','synthetic','counterexample')),
      outcome_class text NOT NULL CHECK(outcome_class IN ('resolved','corrected','unresolved','unknown')),
      source_set_fingerprint text NOT NULL CHECK(source_set_fingerprint ~ '^[0-9a-f]{64}$'),
      source_review_id text NOT NULL,enabled boolean NOT NULL DEFAULT true,
      provider text,model text,dimensions integer,embedding vector,embedding_fingerprint text,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,generation_id,definition_id,definition_version,example_kind,source_set_fingerprint),
      FOREIGN KEY(user_id,workspace_id,generation_id,definition_id,definition_version)
        REFERENCES vault_private.vault_decision_definitions(user_id,workspace_id,generation_id,definition_id,version)
        ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,source_review_id)
        REFERENCES vault_private.vault_decision_reviews(user_id,workspace_id,review_id) ON DELETE CASCADE,
      CHECK((embedding IS NULL AND provider IS NULL AND model IS NULL AND dimensions IS NULL AND embedding_fingerprint IS NULL)
        OR (embedding IS NOT NULL AND provider IS NOT NULL AND model IS NOT NULL AND dimensions IS NOT NULL AND dimensions>0
          AND vector_dims(embedding)=dimensions AND embedding_fingerprint IS NOT NULL
          AND embedding_fingerprint ~ '^[0-9a-f]{64}$'))
    )
-- @statement
CREATE INDEX IF NOT EXISTS ix_vault_decision_definition_scope
       ON vault_private.vault_decision_definitions(user_id,workspace_id,generation_id,status,decision_key)
-- @statement
CREATE INDEX IF NOT EXISTS ix_vault_decision_example_scope
       ON vault_private.vault_decision_examples(user_id,workspace_id,generation_id,definition_id,enabled)
-- @statement ["fb77ae9be2e576b2f79068e85b97a5fb8754c6545bccc9cdf878a6945cc62f98"]
INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
      VALUES ('decision_rules_v1',%s) ON CONFLICT(schema_key) DO UPDATE SET
      schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_decision_activations (
      user_id text NOT NULL, workspace_id text NOT NULL, generation_id text,
      epoch bigint NOT NULL DEFAULT 0 CHECK(epoch>=0), policy_version text NOT NULL,
      actor_user_id text NOT NULL, changed_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(user_id,workspace_id),
      FOREIGN KEY(user_id,workspace_id) REFERENCES
        vault_private.local_workspace_memberships(user_id,workspace_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,generation_id) REFERENCES
        vault_private.vault_decision_generations(user_id,workspace_id,generation_id)
        ON DELETE SET NULL (generation_id)
    )
-- @statement
CREATE OR REPLACE FUNCTION vault_private.invalidate_decision_review_catalog()
      RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        UPDATE vault_private.vault_decision_generations g SET state='retired',updated_at=now()
        FROM vault_private.vault_decision_activations a
        WHERE a.user_id=OLD.user_id AND a.workspace_id=OLD.workspace_id
          AND g.generation_id=a.generation_id AND (
            g.review_id=OLD.review_id OR EXISTS (
              SELECT 1 FROM vault_private.vault_decision_examples e
              WHERE e.user_id=a.user_id AND e.workspace_id=a.workspace_id
                AND e.generation_id=a.generation_id AND e.source_review_id=OLD.review_id));
        UPDATE vault_private.vault_decision_activations a
          SET generation_id=NULL,epoch=epoch+1,changed_at=now()
        WHERE a.user_id=OLD.user_id AND a.workspace_id=OLD.workspace_id
          AND a.generation_id IS NOT NULL AND EXISTS (
            SELECT 1 FROM vault_private.vault_decision_generations g
            WHERE g.generation_id=a.generation_id AND (g.review_id=OLD.review_id OR EXISTS (
              SELECT 1 FROM vault_private.vault_decision_examples e
              WHERE e.user_id=a.user_id AND e.workspace_id=a.workspace_id
                AND e.generation_id=a.generation_id AND e.source_review_id=OLD.review_id)));
        RETURN OLD;
      END $$
-- @statement
CREATE OR REPLACE FUNCTION vault_private.invalidate_decision_generation_pointer()
      RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        UPDATE vault_private.vault_decision_activations SET generation_id=NULL,
          epoch=epoch+1,changed_at=now() WHERE generation_id=OLD.generation_id;
        RETURN OLD;
      END $$
-- @statement
DROP TRIGGER IF EXISTS decision_review_catalog_erasure ON vault_private.vault_decision_reviews
-- @statement
CREATE TRIGGER decision_review_catalog_erasure BEFORE DELETE ON
      vault_private.vault_decision_reviews FOR EACH ROW EXECUTE FUNCTION
      vault_private.invalidate_decision_review_catalog()
-- @statement
DROP TRIGGER IF EXISTS decision_generation_pointer_erasure ON vault_private.vault_decision_generations
-- @statement
CREATE TRIGGER decision_generation_pointer_erasure BEFORE DELETE ON
      vault_private.vault_decision_generations FOR EACH ROW EXECUTE FUNCTION
      vault_private.invalidate_decision_generation_pointer()
-- @statement ["7feee2c1dab0fdb6831b0d4dfb19278d53580a49ea2acd3b5f4525baecb3b125"]
INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
      VALUES ('decision_activation_v1',%s) ON CONFLICT(schema_key) DO UPDATE SET
      schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()
-- @statement
CREATE TABLE IF NOT EXISTS vault_private.vault_live_tool_routing_preferences (
   user_id text NOT NULL,
   workspace_id text NOT NULL,
   enabled boolean NOT NULL DEFAULT true,
   updated_at timestamptz NOT NULL DEFAULT now(),
   PRIMARY KEY (user_id, workspace_id),
   FOREIGN KEY (workspace_id, user_id)
     REFERENCES vault_private.local_workspace_memberships(workspace_id, user_id)
     ON DELETE CASCADE
)
