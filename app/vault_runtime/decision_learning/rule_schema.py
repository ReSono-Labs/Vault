"""Derived procedural generations; separate from canonical memory schema."""
from hashlib import sha256

SCHEMA_STATEMENTS = (
    "CREATE EXTENSION IF NOT EXISTS vector",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_vault_decision_review_scope_id
       ON vault_private.vault_decision_reviews(user_id,workspace_id,review_id)""",
    """CREATE TABLE IF NOT EXISTS vault_private.vault_decision_generations (
      generation_id text PRIMARY KEY,user_id text NOT NULL,workspace_id text NOT NULL,
      review_id text NOT NULL,schema_version integer NOT NULL CHECK(schema_version>0),
      compiler_version text NOT NULL,source_snapshot_fingerprint text NOT NULL
        CHECK(source_snapshot_fingerprint ~ '^[0-9a-f]{64}$'),
      state text NOT NULL CHECK(state IN ('building','validated','active','retired','failed')),
      created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id,workspace_id,generation_id),UNIQUE(user_id,workspace_id,review_id),
      FOREIGN KEY(user_id,workspace_id,review_id)
        REFERENCES vault_private.vault_decision_reviews(user_id,workspace_id,review_id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS vault_private.vault_decision_definitions (
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
    )""",
    """CREATE TABLE IF NOT EXISTS vault_private.vault_decision_examples (
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
    )""",
    """CREATE INDEX IF NOT EXISTS ix_vault_decision_definition_scope
       ON vault_private.vault_decision_definitions(user_id,workspace_id,generation_id,status,decision_key)""",
    """CREATE INDEX IF NOT EXISTS ix_vault_decision_example_scope
       ON vault_private.vault_decision_examples(user_id,workspace_id,generation_id,definition_id,enabled)""",
)
SCHEMA_FINGERPRINT = sha256("\n".join(SCHEMA_STATEMENTS).encode()).hexdigest()


def ensure_rule_schema(cursor):
    for statement in SCHEMA_STATEMENTS:
        cursor.execute(statement)
    cursor.execute("""INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
      VALUES ('decision_rules_v1',%s) ON CONFLICT(schema_key) DO UPDATE SET
      schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()""", (SCHEMA_FINGERPRINT,))
