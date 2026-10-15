"""Inactive immutable rule publication and checked real example vectors."""
from contextlib import nullcontext
from hashlib import sha256
import json
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.vault_runtime.memory_search.postgres import vector_literal
from .repository import DecisionReviewRepository, ReviewConflictError, source_fingerprint
from .reviewer import _validate_output
from .rule_schema import ensure_rule_schema


def text_hash(text):
    return sha256(text.encode()).hexdigest()


class DecisionRuleRepository(DecisionReviewRepository):
    def ensure_schema(self):
        super().ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            ensure_rule_schema(cursor)

    def publish(self, principal, *, review_id, snapshot, review, _connection=None):
        if snapshot.coverage!="complete":
            raise ReviewConflictError("Rule publication requires qualified complete capture.")
        fingerprint = source_fingerprint(snapshot)
        if review.source_fingerprint != fingerprint:
            raise ReviewConflictError("Publication source changed.")
        _validate_output(review.output, snapshot)
        output_hash = text_hash(review.output.model_dump_json())
        scope = (principal.user_id, principal.workspace_id)
        with (nullcontext(_connection) if _connection is not None else self._connect()) as connection, connection.cursor() as cursor:
            self._require_source(cursor, principal, snapshot)
            cursor.execute("""SELECT state,output_fingerprint,source_snapshot_fingerprint,model
              FROM vault_private.vault_decision_reviews WHERE review_id=%s AND user_id=%s AND workspace_id=%s
              AND conversation_id=%s AND segment_id=%s FOR UPDATE""",
              (review_id, *scope, snapshot.conversation_id, snapshot.segment_id))
            row = cursor.fetchone()
            if row != ("completed", output_hash, fingerprint, review.model):
                raise ReviewConflictError("Publication requires the exact completed owned review.")
            cursor.execute("""SELECT generation_id FROM vault_private.vault_decision_generations
              WHERE user_id=%s AND workspace_id=%s AND review_id=%s""", (*scope, review_id))
            previous = cursor.fetchone()
            if previous:
                return previous[0]
            generation_id = str(uuid4())
            cursor.execute("""INSERT INTO vault_private.vault_decision_generations
              (generation_id,user_id,workspace_id,review_id,schema_version,compiler_version,source_snapshot_fingerprint,state)
              VALUES (%s,%s,%s,%s,1,'procedural-v3',%s,'building')""",
              (generation_id, *scope, review_id, fingerprint))
            existing = {d.definition_id: d.version for d in snapshot.existing_decisions}
            sources = {s.source_id: s for s in snapshot.sources}
            points = {p.point_id: p for p in snapshot.observations}
            seen = set()
            for proposal in review.output.proposals:
                if proposal.disposition not in {"create", "add_example", "revise"}:
                    continue
                content = dict(description=proposal.description, conditions=proposal.conditions,
                    slots=proposal.required_slots, capabilities=proposal.capability_ids, exclusions=proposal.exclusions)
                key = text_hash(json.dumps(content, sort_keys=True, separators=(",", ":")))
                definition_id = proposal.target_definition_id or key
                version = existing.get(definition_id, 0) + 1
                identity = (definition_id, version)
                if identity in seen:
                    raise ReviewConflictError("Conflicting duplicate rule proposals require consolidation.")
                seen.add(identity)
                cursor.execute("""INSERT INTO vault_private.vault_decision_definitions
                  (definition_id,generation_id,version,user_id,workspace_id,decision_key,conditions_json,
                   required_slots_json,capability_refs_json,action_description,exclusions_json,status)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'proposed')""",
                  (definition_id, generation_id, version, *scope, key, Jsonb({"all": list(proposal.conditions)}),
                   Jsonb(list(proposal.required_slots)), Jsonb(list(proposal.capability_ids)),
                   proposal.description, Jsonb(list(proposal.exclusions))))
                examples = {("observed", sources[points[p].final_source_id].text,
                    text_hash(json.dumps([points[p].final_source_id, points[p].result_source_id, fingerprint])))
                    for p in proposal.point_ids}
                examples.update(("synthetic", text, text_hash(fingerprint + "\n" + text)) for text in proposal.examples)
                for kind, text, source_hash in examples:
                    if not text.strip() or len(text) > 20000:
                        raise ReviewConflictError("Bounded nonempty example text required.")
                    cursor.execute("""INSERT INTO vault_private.vault_decision_examples
                      (example_id,user_id,workspace_id,generation_id,definition_id,definition_version,
                       example_text,example_kind,outcome_class,source_set_fingerprint,source_review_id)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                      (str(uuid4()), *scope, generation_id, definition_id, version, text, kind,
                       "resolved" if kind == "observed" else "unknown", source_hash, review_id))
            return generation_id  # building/inactive until vector/source/capability validation.

    def examples(self, principal, generation_id, *, _connection=None):
        with (nullcontext(_connection) if _connection is not None else self._connect()) as connection, connection.cursor() as cursor:
            self._require_authority(cursor, principal)
            cursor.execute("""SELECT example_id,example_text,embedding IS NOT NULL FROM vault_private.vault_decision_examples
              WHERE user_id=%s AND workspace_id=%s AND generation_id=%s ORDER BY example_id LIMIT 1025""",
              (principal.user_id, principal.workspace_id, generation_id))
            rows = cursor.fetchall()
            if len(rows) > 1024:
                raise ReviewConflictError("Generation requires paginated example maintenance.")
            return tuple(rows)

    @staticmethod
    def _require_authority(cursor, principal):
        from app.vault_runtime.conversation.repository import ConversationRepository
        ConversationRepository._require_authority(cursor, principal)

    def store_vector(self, principal, *, generation_id, example_id, snapshot,
                     example_text, vector, provider, model, _connection=None):
        if provider != "ollama" or model != "embeddinggemma:300m":
            raise ValueError("Current indexed embedding identity required.")
        literal = vector_literal(vector)
        with (nullcontext(_connection) if _connection is not None else self._connect()) as connection, connection.cursor() as cursor:
            self._require_source(cursor, principal, snapshot)
            cursor.execute("""SELECT e.example_text,g.source_snapshot_fingerprint
              FROM vault_private.vault_decision_examples e JOIN vault_private.vault_decision_generations g
                USING(user_id,workspace_id,generation_id)
              WHERE e.user_id=%s AND e.workspace_id=%s AND e.generation_id=%s AND e.example_id=%s
              AND e.enabled AND g.state='building' FOR UPDATE OF e FOR SHARE OF g""",
              (principal.user_id, principal.workspace_id, generation_id, example_id))
            row = cursor.fetchone()
            if row != (example_text, source_fingerprint(snapshot)):
                raise ReviewConflictError("Example or qualified source changed.")
            cursor.execute("""UPDATE vault_private.vault_decision_examples SET provider=%s,model=%s,
              dimensions=768,embedding=%s::vector,embedding_fingerprint=%s WHERE example_id=%s""",
              (provider, model, literal, text_hash(example_text), example_id))

    def drop_inactive(self, principal, generation_id):
        with self._connect() as connection, connection.cursor() as cursor:
            self._require_authority(cursor, principal)
            cursor.execute("""DELETE FROM vault_private.vault_decision_generations
              WHERE user_id=%s AND workspace_id=%s AND generation_id=%s AND state IN ('building','failed','retired')
              RETURNING generation_id""", (principal.user_id, principal.workspace_id, generation_id))
            if cursor.fetchone() is None:
                raise ReviewConflictError("Owned inactive generation required.")
