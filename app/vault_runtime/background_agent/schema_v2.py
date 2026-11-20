"""Additive coordination records; initialization grants no execution capability."""
from hashlib import sha256

from app.vault_runtime.local_identity.schema import Cursor
from .coordination_contracts import WorkState

_STATES = ",".join(f"'{state.value}'" for state in WorkState)
SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS vault_private.vault_background_execution_grants (
      grant_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      purpose text NOT NULL, policy_json jsonb NOT NULL CHECK (jsonb_typeof(policy_json)='object'),
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked')),
      version integer NOT NULL DEFAULT 1 CHECK (version>0), expires_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,grant_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS vault_private.vault_background_workers (
      worker_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      role_key text NOT NULL, spec_json jsonb NOT NULL CHECK (jsonb_typeof(spec_json)='object'),
      spec_hash text NOT NULL CHECK (length(spec_hash)=64), grant_id text,
      generation integer NOT NULL DEFAULT 1 CHECK (generation>0),
      status text NOT NULL DEFAULT 'idle' CHECK (status IN ('idle','active','paused','deleted')),
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,worker_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,grant_id) REFERENCES vault_private.vault_background_execution_grants(user_id,workspace_id,grant_id)
    )""",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_background_worker_role
       ON vault_private.vault_background_workers(user_id,workspace_id,role_key) WHERE status<>'deleted'""",
    """CREATE TABLE IF NOT EXISTS vault_private.vault_background_routines (
      routine_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      version integer NOT NULL DEFAULT 1 CHECK (version>0), rule_json jsonb NOT NULL,
      timezone text NOT NULL, next_due_at timestamptz, grant_id text NOT NULL, template_json jsonb NOT NULL,
      status text NOT NULL DEFAULT 'paused' CHECK (status IN ('active','paused','deleted')),
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,routine_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,grant_id) REFERENCES vault_private.vault_background_execution_grants(user_id,workspace_id,grant_id)
    )""",
    f"""CREATE TABLE IF NOT EXISTS vault_private.vault_background_work (
      work_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      source_key text NOT NULL, intent_version integer NOT NULL DEFAULT 1 CHECK (intent_version>0),
      request_json jsonb NOT NULL CHECK (jsonb_typeof(request_json)='object'),
      state text NOT NULL DEFAULT 'proposed' CHECK (state IN ({_STATES})),
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
    )""",
    """CREATE TABLE IF NOT EXISTS vault_private.vault_background_sessions (
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
    )""",
    """CREATE TABLE IF NOT EXISTS vault_private.vault_background_occurrences (
      occurrence_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      routine_id text NOT NULL, routine_version integer NOT NULL, scheduled_for timestamptz NOT NULL, work_id text,
      UNIQUE(user_id,workspace_id,routine_id,routine_version,scheduled_for),
      FOREIGN KEY(user_id,workspace_id,routine_id) REFERENCES vault_private.vault_background_routines(user_id,workspace_id,routine_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,work_id) REFERENCES vault_private.vault_background_work(user_id,workspace_id,work_id)
    )""",
    """CREATE TABLE IF NOT EXISTS vault_private.vault_background_events (
      event_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
      source_kind text NOT NULL, source_id text NOT NULL, payload_json jsonb NOT NULL,
      state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','processed','cancelled')),
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,source_kind,source_id),
      FOREIGN KEY(workspace_id,user_id) REFERENCES vault_private.local_workspace_memberships(workspace_id,user_id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS vault_private.vault_background_actions (
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
    )""",
    # One waiting owner approval per account at a time (Link shows one question per turn).
    """CREATE UNIQUE INDEX IF NOT EXISTS ux_owner_approval_pending ON vault_private.vault_background_actions(user_id,workspace_id)
      WHERE kind='owner_approval' AND state='pending'""",
    "CREATE INDEX IF NOT EXISTS ix_background_due ON vault_private.vault_background_routines(next_due_at) WHERE status='active'",
    "CREATE INDEX IF NOT EXISTS ix_background_work_scope_state ON vault_private.vault_background_work(user_id,workspace_id,state,created_at)",
    "ALTER TABLE vault_private.vault_background_runs ALTER COLUMN local_session_id DROP NOT NULL",
    "ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS work_id text",
    "ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS coordination_session_id text",
    "ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS execution_grant_id text",
    "ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS attempt_generation bigint NOT NULL DEFAULT 0",
    "ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS checkpoint_json jsonb",
    "ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS active_seconds double precision NOT NULL DEFAULT 0",
    "ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS first_started_at timestamptz",
    """DO $$ BEGIN
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
    END $$""",
)
SCHEMA_FINGERPRINT = sha256("\n".join(SCHEMA_STATEMENTS).encode()).hexdigest()


def ensure_coordination_schema(cursor: Cursor) -> None:
    for statement in SCHEMA_STATEMENTS:
        cursor.execute(statement)
    cursor.execute("""INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
        VALUES ('background_coordination_v1',%s) ON CONFLICT(schema_key) DO UPDATE SET
        schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()""", (SCHEMA_FINGERPRINT,))
