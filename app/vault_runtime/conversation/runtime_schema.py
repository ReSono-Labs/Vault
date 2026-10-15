"""Necessary response/stream sources; immutable final input remains C03A-owned."""
from hashlib import sha256

STATEMENTS = (
    """ALTER TABLE vault_private.vault_conversations
       ADD COLUMN IF NOT EXISTS source_voice_session_id text,
       ADD COLUMN IF NOT EXISTS activity_at timestamptz,
       ADD COLUMN IF NOT EXISTS activity_session_id text""",
    """ALTER TABLE vault_private.vault_conversation_segments
       ADD COLUMN IF NOT EXISTS first_review_ordinal bigint,
       ADD COLUMN IF NOT EXISTS last_review_ordinal bigint,
       ADD COLUMN IF NOT EXISTS memory_review_result_json jsonb,
       ADD COLUMN IF NOT EXISTS decision_review_result_json jsonb,
       ADD COLUMN IF NOT EXISTS memory_review_state text NOT NULL DEFAULT 'not_requested'
         CHECK(memory_review_state IN ('not_requested','pending','completed','failed','disabled')),
       ADD COLUMN IF NOT EXISTS decision_review_state text NOT NULL DEFAULT 'not_requested'
         CHECK(decision_review_state IN ('not_requested','pending','completed','failed','disabled'))""",
    """ALTER TABLE vault_private.vault_conversation_segments
       ADD COLUMN IF NOT EXISTS review_state text NOT NULL DEFAULT 'not_requested'
         CHECK(review_state IN ('not_requested','queued','running','completed','failed','blocked_authority')),
       ADD COLUMN IF NOT EXISTS review_session_id text,
       ADD COLUMN IF NOT EXISTS review_attempts integer NOT NULL DEFAULT 0,
       ADD COLUMN IF NOT EXISTS review_due_at timestamptz NOT NULL DEFAULT now()""",
    """CREATE INDEX IF NOT EXISTS idx_conversation_review_due
       ON vault_private.vault_conversation_segments(review_due_at)
       WHERE review_state IN ('queued','running') AND state='sealed'""",
    """ALTER TABLE vault_private.vault_conversation_turns
       ADD COLUMN IF NOT EXISTS run_owner text,
       ADD COLUMN IF NOT EXISTS cancel_requested boolean NOT NULL DEFAULT false,
       ADD COLUMN IF NOT EXISTS source_coverage text NOT NULL DEFAULT 'unknown'
         CHECK(source_coverage IN ('unknown','complete','incomplete')),
       ADD COLUMN IF NOT EXISTS event_sequence bigint NOT NULL DEFAULT 0,
       ADD COLUMN IF NOT EXISTS event_bytes bigint NOT NULL DEFAULT 0""",
    """CREATE TABLE IF NOT EXISTS vault_private.vault_conversation_events (
       user_id text NOT NULL,workspace_id text NOT NULL,conversation_id text NOT NULL,
       turn_id text NOT NULL,sequence bigint NOT NULL CHECK(sequence>0),
       kind text NOT NULL CHECK(kind IN ('waiting','context','model_response','tool_status',
         'text_delta','assistant_final','error','terminal')),
       payload jsonb NOT NULL CHECK(octet_length(payload::text)<=131072),
       created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(turn_id,sequence),
       FOREIGN KEY(user_id,workspace_id,conversation_id,turn_id) REFERENCES
         vault_private.vault_conversation_turns(user_id,workspace_id,conversation_id,turn_id) ON DELETE CASCADE)""",
    """ALTER TABLE vault_private.vault_voice_tool_invocations
       ALTER COLUMN voice_session_id DROP NOT NULL,
       ADD COLUMN IF NOT EXISTS conversation_id text,
       ADD COLUMN IF NOT EXISTS turn_id text""",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_tool_invocation_conversation_call
       ON vault_private.vault_voice_tool_invocations(conversation_id,turn_id,tool_call_id)""",
    """DO $$ BEGIN
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
       END IF; END $$""",
)


def ensure_runtime_schema(cursor):
    for statement in STATEMENTS:
        cursor.execute(statement)
    ensure_voice_review_bridge(cursor)
    cursor.execute("""INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
      VALUES(%s,%s) ON CONFLICT(schema_key) DO UPDATE SET
      schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()""",
      ("conversation_runtime_v1",sha256("\n".join(STATEMENTS).encode()).hexdigest()))


def ensure_voice_review_bridge(cursor):
    statements = ("""CREATE UNIQUE INDEX IF NOT EXISTS uq_voice_session_review_scope
      ON vault_private.vault_voice_sessions(user_id,workspace_id,voice_session_id)""",
      """ALTER TABLE vault_private.vault_conversations
      ADD COLUMN IF NOT EXISTS source_voice_session_id text""",
      """DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE
      conname='fk_conversation_voice_review_source' AND conrelid='vault_private.vault_conversations'::regclass)
      THEN ALTER TABLE vault_private.vault_conversations ADD CONSTRAINT fk_conversation_voice_review_source
      FOREIGN KEY(user_id,workspace_id,source_voice_session_id) REFERENCES
        vault_private.vault_voice_sessions(user_id,workspace_id,voice_session_id) ON DELETE CASCADE;
      END IF; END $$""")
    for statement in statements:
        cursor.execute(statement)
    cursor.execute("""INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
      VALUES (%s,%s) ON CONFLICT(schema_key) DO UPDATE SET
      schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()""",
      ("voice_decision_review_bridge_v1",sha256("\n".join(statements).encode()).hexdigest()))
