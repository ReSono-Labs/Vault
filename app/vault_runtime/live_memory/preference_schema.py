"""Scoped preparation preference only; no drafts or learning state."""
from hashlib import sha256

SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS vault_private.vault_live_memory_preferences (
       user_id text NOT NULL,
       workspace_id text NOT NULL,
       enabled boolean NOT NULL DEFAULT true,
       epoch bigint NOT NULL DEFAULT 1 CHECK (epoch > 0),
       PRIMARY KEY (user_id, workspace_id),
       FOREIGN KEY (workspace_id, user_id)
         REFERENCES vault_private.local_workspace_memberships(workspace_id, user_id)
         ON DELETE CASCADE
    )""",
)
SCHEMA_FINGERPRINT = sha256("\n".join(SCHEMA_STATEMENTS).encode()).hexdigest()


def ensure_preference_schema(cursor):
    for statement in SCHEMA_STATEMENTS:
        cursor.execute(statement)
    cursor.execute(
        """INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
           VALUES (%s,%s) ON CONFLICT(schema_key) DO UPDATE SET
           schema_fingerprint=EXCLUDED.schema_fingerprint, updated_at=now()""",
        ("live_memory_preference_v1", SCHEMA_FINGERPRINT),
    )
