"""Atomic additive catalog compiler. Mandatory current-source/capability gates."""
from contextlib import nullcontext
from dataclasses import dataclass
import json
from uuid import uuid4

from app.vault_runtime.decision_routing.capabilities import CapabilitySnapshot
from .activation_schema import ensure_activation_schema
from .repository import ReviewConflictError


@dataclass(frozen=True, slots=True)
class CatalogRule:
    definition_id: str
    version: int
    description: str
    conditions: dict
    required_slots: tuple
    capability_ids: tuple
    exclusions: tuple
    source_review_ids: tuple


@dataclass(frozen=True, slots=True)
class Activation:
    generation_id: str | None
    epoch: int


class NoQualifiedRuleError(ReviewConflictError):
    pass


class CatalogActivator:
    def __init__(self, *, repository, qualify_rule, current_capabilities):
        if not callable(qualify_rule) or not callable(current_capabilities):
            raise ValueError("Current transactional qualification and capability gates required.")
        self.repository = repository
        self.qualify_rule = qualify_rule
        self.current_capabilities = current_capabilities

    def ensure_schema(self):
        self.repository.ensure_schema()
        with self.repository._connect() as connection, connection.cursor() as cursor:
            ensure_activation_schema(cursor)

    def current(self, principal, *, _connection=None):
        with (nullcontext(_connection) if _connection is not None else self.repository._connect()) as connection, connection.cursor() as cursor:
            self.repository._require_authority(cursor, principal)
            cursor.execute("""SELECT generation_id,epoch FROM vault_private.vault_decision_activations
              WHERE user_id=%s AND workspace_id=%s""", (principal.user_id,principal.workspace_id))
            row = cursor.fetchone()
            return Activation(*row) if row else Activation(None,0)

    def activate(self, principal, *, generation_id, expected_epoch, policy_version, _connection=None, _replacement=False):
        if type(expected_epoch) is not int or expected_epoch < 0:
            raise ValueError("Explicit nonnegative activation epoch required.")
        if type(policy_version) is not str or not policy_version.strip() or len(policy_version)>256:
            raise ValueError("Explicit bounded activation policy identity required.")
        if _replacement and _connection is None:
            raise ValueError('A complete replacement requires the caller rebuild transaction.')
        scope = (principal.user_id,principal.workspace_id)
        with (nullcontext(_connection) if _connection is not None else self.repository._connect()) as connection, connection.cursor() as cursor:
            self.repository._require_authority(cursor,principal)
            # Serialize absent-pointer creation and concurrent catalog compilation.
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,73102715))",
                           (json.dumps(scope,separators=(",", ":")),))
            cursor.execute("""SELECT generation_id,epoch,policy_version FROM vault_private.vault_decision_activations
              WHERE user_id=%s AND workspace_id=%s FOR UPDATE""",scope)
            pointer = cursor.fetchone()
            previous, epoch = pointer[:2] if pointer else (None,0)
            if previous == generation_id and epoch == expected_epoch+1 and pointer[2] == policy_version:
                return Activation(previous,epoch)  # exact acknowledged retry; not an execution grant.
            if epoch != expected_epoch:
                raise ReviewConflictError("Active catalog changed; recompile against current epoch.")
            cursor.execute("""SELECT state FROM vault_private.vault_decision_generations
              WHERE user_id=%s AND workspace_id=%s AND generation_id=%s FOR UPDATE""",(*scope,generation_id))
            if cursor.fetchone() != ("building",):
                raise ReviewConflictError("Owned building generation required.")
            capabilities = self.current_capabilities(cursor,principal)
            if type(capabilities) is not CapabilitySnapshot:
                raise ReviewConflictError("Current capabilities unavailable.")
            if previous and not _replacement:
                self._merge(cursor,scope,previous,generation_id)
            elif not _replacement:
                cursor.execute("""SELECT 1 FROM vault_private.vault_decision_definitions
                  WHERE user_id=%s AND workspace_id=%s AND generation_id=%s AND version<>1 LIMIT 1""",
                  (*scope,generation_id))
                if cursor.fetchone():
                    raise ReviewConflictError("A revision requires a current active predecessor.")
            cursor.execute("""SELECT definition_id,version,action_description,conditions_json,
              required_slots_json,capability_refs_json,exclusions_json FROM vault_private.vault_decision_definitions
              WHERE user_id=%s AND workspace_id=%s AND generation_id=%s ORDER BY definition_id LIMIT 1025""",
              (*scope,generation_id))
            definitions = cursor.fetchall()
            if len(definitions)>1024:
                raise ReviewConflictError("Catalog requires bounded paginated compilation.")
            active = 0
            for row in definitions:
                cursor.execute("""SELECT DISTINCT source_review_id FROM vault_private.vault_decision_examples
                  WHERE user_id=%s AND workspace_id=%s AND generation_id=%s AND definition_id=%s
                  AND definition_version=%s AND enabled ORDER BY source_review_id""",
                  (*scope,generation_id,row[0],row[1]))
                sources = tuple(r[0] for r in cursor.fetchall())
                rule = CatalogRule(row[0],row[1],row[2],row[3],tuple(row[4]),tuple(row[5]),tuple(row[6]),sources)
                # Always evaluate source/suppression/quality, including retained rules.
                qualified = self.qualify_rule(cursor,principal,rule) is True
                eligible = qualified and bool(sources) and capabilities.read_only(rule.capability_ids)
                if eligible:
                    cursor.execute("""SELECT count(*),count(*) FILTER (WHERE example_kind='observed' AND outcome_class='resolved'),
                      bool_and(provider='ollama' AND model='embeddinggemma:300m' AND dimensions=768
                        AND embedding IS NOT NULL AND vector_dims(embedding)=768 AND vector_norm(embedding)>0
                        AND embedding_fingerprint=encode(sha256(convert_to(example_text,'UTF8')),'hex'))
                      FROM vault_private.vault_decision_examples WHERE user_id=%s AND workspace_id=%s
                        AND generation_id=%s AND definition_id=%s AND definition_version=%s AND enabled""",
                      (*scope,generation_id,row[0],row[1]))
                    count,observed,vectors_current = cursor.fetchone()
                    if not count or not observed or vectors_current is not True:
                        raise ReviewConflictError("Qualified rule requires observed evidence and current indexed examples.")
                    active += 1
                cursor.execute("""UPDATE vault_private.vault_decision_definitions SET status=%s
                  WHERE user_id=%s AND workspace_id=%s AND generation_id=%s AND definition_id=%s AND version=%s""",
                  ("active" if eligible else "inactive",*scope,generation_id,row[0],row[1]))
            if not active:
                raise NoQualifiedRuleError("No qualified read-only rule; current catalog retained.")
            if self.current_capabilities(cursor,principal) != capabilities:
                raise ReviewConflictError("Capabilities changed during compilation.")
            cursor.execute("""UPDATE vault_private.vault_decision_generations SET state='retired',updated_at=now()
              WHERE user_id=%s AND workspace_id=%s AND generation_id=%s""",(*scope,previous))
            cursor.execute("""UPDATE vault_private.vault_decision_generations SET state='active',updated_at=now()
              WHERE user_id=%s AND workspace_id=%s AND generation_id=%s""",(*scope,generation_id))
            cursor.execute("""INSERT INTO vault_private.vault_decision_activations
              (user_id,workspace_id,generation_id,epoch,policy_version,actor_user_id)
              VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(user_id,workspace_id) DO UPDATE SET
              generation_id=EXCLUDED.generation_id,epoch=EXCLUDED.epoch,policy_version=EXCLUDED.policy_version,
              actor_user_id=EXCLUDED.actor_user_id,changed_at=now()""",
              (*scope,generation_id,epoch+1,policy_version,principal.user_id))
            return Activation(generation_id,epoch+1)

    @staticmethod
    def _merge(cursor,scope,previous,target):
        cursor.execute("""SELECT proposal->>'target_definition_id'
          FROM vault_private.vault_decision_generations g JOIN vault_private.vault_decision_reviews r
            USING(user_id,workspace_id,review_id),jsonb_array_elements(r.proposals_json) proposal
          WHERE g.user_id=%s AND g.workspace_id=%s AND g.generation_id=%s
            AND proposal->>'disposition'='add_example'""",(*scope,target))
        example_only = [r[0] for r in cursor.fetchall()]
        if example_only:
            cursor.execute("""SELECT 1 FROM vault_private.vault_decision_definitions n
              JOIN vault_private.vault_decision_definitions p USING(user_id,workspace_id,definition_id)
              WHERE n.user_id=%s AND n.workspace_id=%s AND n.generation_id=%s AND p.generation_id=%s
                AND n.definition_id=ANY(%s) AND ROW(n.action_description,n.conditions_json,n.required_slots_json,
                  n.capability_refs_json,n.exclusions_json) IS DISTINCT FROM ROW(p.action_description,
                  p.conditions_json,p.required_slots_json,p.capability_refs_json,p.exclusions_json) LIMIT 1""",
              (*scope,target,previous,example_only))
            if cursor.fetchone():
                raise ReviewConflictError("Example-only learning cannot change authoritative behavior.")
        cursor.execute("""SELECT 1 FROM vault_private.vault_decision_definitions n
          WHERE n.user_id=%s AND n.workspace_id=%s AND n.generation_id=%s AND n.version<>1
            AND NOT EXISTS (SELECT 1 FROM vault_private.vault_decision_definitions p
              WHERE p.user_id=n.user_id AND p.workspace_id=n.workspace_id
                AND p.generation_id=%s AND p.definition_id=n.definition_id) LIMIT 1""",
          (*scope,target,previous))
        if cursor.fetchone():
            raise ReviewConflictError("A revision requires a current active predecessor.")
        cursor.execute("""SELECT n.definition_id FROM vault_private.vault_decision_definitions n
          JOIN vault_private.vault_decision_definitions p USING(user_id,workspace_id,definition_id)
          WHERE n.user_id=%s AND n.workspace_id=%s AND n.generation_id=%s AND p.generation_id=%s
            AND n.version<>p.version+1 LIMIT 1""",(*scope,target,previous))
        if cursor.fetchone():
            raise ReviewConflictError("Rule revision must advance the current active version exactly once.")
        cursor.execute("""INSERT INTO vault_private.vault_decision_definitions
          (user_id,workspace_id,generation_id,definition_id,version,decision_key,conditions_json,
           required_slots_json,capability_refs_json,action_description,exclusions_json,status)
          SELECT p.user_id,p.workspace_id,%s,p.definition_id,p.version,p.decision_key,p.conditions_json,
            p.required_slots_json,p.capability_refs_json,p.action_description,p.exclusions_json,'proposed'
          FROM vault_private.vault_decision_definitions p WHERE p.user_id=%s AND p.workspace_id=%s
            AND p.generation_id=%s AND NOT EXISTS (SELECT 1 FROM vault_private.vault_decision_definitions n
              WHERE n.user_id=p.user_id AND n.workspace_id=p.workspace_id AND n.generation_id=%s
                AND n.definition_id=p.definition_id)""",(target,*scope,previous,target))
        cursor.execute("""SELECT e.example_id,n.version FROM vault_private.vault_decision_examples e
          JOIN vault_private.vault_decision_definitions n ON n.user_id=e.user_id AND n.workspace_id=e.workspace_id
            AND n.definition_id=e.definition_id AND n.generation_id=%s
            AND (n.version=e.definition_version OR (n.version=e.definition_version+1 AND n.definition_id=ANY(%s)))
          WHERE e.user_id=%s AND e.workspace_id=%s AND e.generation_id=%s ORDER BY e.example_id LIMIT 32769""",
          (target,example_only,*scope,previous))
        rows = cursor.fetchall()
        if len(rows)>32768:
            raise ReviewConflictError("Catalog requires bounded example pagination.")
        for example_id,version in rows:
            cursor.execute("""INSERT INTO vault_private.vault_decision_examples
              (example_id,user_id,workspace_id,generation_id,definition_id,definition_version,example_text,
               example_kind,outcome_class,source_set_fingerprint,source_review_id,enabled,
               provider,model,dimensions,embedding,embedding_fingerprint)
              SELECT %s,user_id,workspace_id,%s,definition_id,%s,example_text,
                example_kind,outcome_class,source_set_fingerprint,source_review_id,enabled,
                provider,model,dimensions,embedding,embedding_fingerprint
              FROM vault_private.vault_decision_examples WHERE example_id=%s
              ON CONFLICT(user_id,workspace_id,generation_id,definition_id,definition_version,example_kind,source_set_fingerprint)
                DO NOTHING""",
              (str(uuid4()),target,version,example_id))
