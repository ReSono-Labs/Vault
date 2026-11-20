"""Owned additive procedural review checkpoints, never canonical session payloads."""
from hashlib import sha256

SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS vault_private.vault_decision_reviews (
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
    )""",
    """ALTER TABLE vault_private.vault_decision_reviews ADD COLUMN IF NOT EXISTS assessments_json
      jsonb NOT NULL DEFAULT '[]'::jsonb CHECK(jsonb_typeof(assessments_json)='array')""",
    """CREATE INDEX IF NOT EXISTS ix_vault_decision_reviews_scope_lease
       ON vault_private.vault_decision_reviews(user_id,workspace_id,state,lease_until)""",
)
SCHEMA_FINGERPRINT = sha256("\n".join(SCHEMA_STATEMENTS).encode()).hexdigest()


def ensure_review_schema(cursor):
    for statement in SCHEMA_STATEMENTS:
        cursor.execute(statement)
    cursor.execute("""INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
      VALUES ('decision_reviews_v1',%s) ON CONFLICT(schema_key) DO UPDATE SET
      schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()""", (SCHEMA_FINGERPRINT,))
