"""Scoped catalog pointer and source-erasure invalidation; no startup migration."""
from hashlib import sha256

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS vault_private.vault_decision_activations (
      user_id text NOT NULL, workspace_id text NOT NULL, generation_id text,
      epoch bigint NOT NULL DEFAULT 0 CHECK(epoch>=0), policy_version text NOT NULL,
      actor_user_id text NOT NULL, changed_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(user_id,workspace_id),
      FOREIGN KEY(user_id,workspace_id) REFERENCES
        vault_private.local_workspace_memberships(user_id,workspace_id) ON DELETE CASCADE,
      FOREIGN KEY(user_id,workspace_id,generation_id) REFERENCES
        vault_private.vault_decision_generations(user_id,workspace_id,generation_id)
        ON DELETE SET NULL (generation_id)
    )""",
    """CREATE OR REPLACE FUNCTION vault_private.invalidate_decision_review_catalog()
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
      END $$""",
    """CREATE OR REPLACE FUNCTION vault_private.invalidate_decision_generation_pointer()
      RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        UPDATE vault_private.vault_decision_activations SET generation_id=NULL,
          epoch=epoch+1,changed_at=now() WHERE generation_id=OLD.generation_id;
        RETURN OLD;
      END $$""",
    "DROP TRIGGER IF EXISTS decision_review_catalog_erasure ON vault_private.vault_decision_reviews",
    """CREATE TRIGGER decision_review_catalog_erasure BEFORE DELETE ON
      vault_private.vault_decision_reviews FOR EACH ROW EXECUTE FUNCTION
      vault_private.invalidate_decision_review_catalog()""",
    "DROP TRIGGER IF EXISTS decision_generation_pointer_erasure ON vault_private.vault_decision_generations",
    """CREATE TRIGGER decision_generation_pointer_erasure BEFORE DELETE ON
      vault_private.vault_decision_generations FOR EACH ROW EXECUTE FUNCTION
      vault_private.invalidate_decision_generation_pointer()""",
)


def ensure_activation_schema(cursor):
    for statement in STATEMENTS:
        cursor.execute(statement)
    cursor.execute("""INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
      VALUES ('decision_activation_v1',%s) ON CONFLICT(schema_key) DO UPDATE SET
      schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()""",
      (sha256("\n".join(STATEMENTS).encode()).hexdigest(),))
