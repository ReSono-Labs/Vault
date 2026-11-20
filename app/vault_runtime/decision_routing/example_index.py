"""Real SQL example nearest-neighbors and guarded active catalog reads."""
from dataclasses import dataclass
from app.vault_runtime.conversation.repository import ConversationRepository
from app.vault_runtime.memory_search.postgres import QueryOptions, vector_literal, vector_version
from app.vault_runtime.memory_search.indexes import _state, _normalized, IndexMigrationError
from .contracts import CandidateChoice

NAME = "ix_vault_decision_example_hnsw_768"
PREDICATE = """enabled AND provider='ollama' AND model='embeddinggemma:300m' AND dimensions=768
    AND vector_dims(embedding)=768 AND vector_norm(embedding)>0"""
DDL = f"""CREATE INDEX CONCURRENTLY {NAME} ON vault_private.vault_decision_examples
    USING hnsw ((embedding::vector(768)) vector_cosine_ops) WHERE {PREDICATE}"""
EXPECTED = f"""CREATE INDEX {NAME} ON vault_private.vault_decision_examples USING hnsw
    (((embedding)::vector(768)) vector_cosine_ops) WHERE (enabled AND (provider = 'ollama'::text)
    AND (model = 'embeddinggemma:300m'::text) AND (dimensions = 768)
    AND (vector_dims(embedding) = 768) AND (vector_norm(embedding) > (0)::double precision))"""


def ensure_example_index(connection):
    if not connection.autocommit or connection.info.transaction_status != 0:
        raise IndexMigrationError("Concurrent example index needs autocommit.")
    with connection.cursor() as cursor:
        vector_version(cursor)
        cursor.execute("SELECT pg_try_advisory_lock(73102714)")
        if not cursor.fetchone()[0]:
            raise IndexMigrationError("Example migration is already running.")
        try:
            state = _state(cursor, NAME)
            if state:
                if state[1] is None or _normalized(state[1]) != _normalized(EXPECTED):
                    raise IndexMigrationError("Example index name has conflicting definition.")
                if state[0]:
                    return
                cursor.execute(f"DROP INDEX CONCURRENTLY vault_private.{NAME}")
            cursor.execute(DDL)
            state = _state(cursor, NAME)
            if not state or not state[0] or _normalized(state[1]) != _normalized(EXPECTED):
                raise IndexMigrationError("Example index did not match the owned definition.")
        finally:
            cursor.execute("SELECT pg_advisory_unlock(73102714)")


def candidate_statement(*, exact=False, active=False):
    base = f"""SELECT e.definition_id,e.definition_version,d.action_description,
      e.embedding::vector(768) AS embedding FROM vault_private.vault_decision_examples e
      JOIN vault_private.vault_decision_definitions d ON d.user_id=e.user_id AND d.workspace_id=e.workspace_id
        AND d.generation_id=e.generation_id AND d.definition_id=e.definition_id AND d.version=e.definition_version
      WHERE e.user_id=%s AND e.workspace_id=%s AND e.generation_id=%s AND {PREDICATE}
        AND e.embedding_fingerprint=encode(sha256(convert_to(e.example_text,'UTF8')),'hex')
        {"AND d.status='active'" if active else ""}"""
    # Materialization disables ANN only for the explicit bounded underfill retry.
    return f"""WITH eligible AS {'MATERIALIZED' if exact else 'NOT MATERIALIZED'} ({base}),
      nearest AS (SELECT definition_id,definition_version,action_description,
        embedding <=> %s::vector(768) AS distance FROM eligible
        ORDER BY embedding <=> %s::vector(768) LIMIT %s),
      collapsed AS (SELECT definition_id,definition_version,action_description,min(distance) distance
        FROM nearest GROUP BY definition_id,definition_version,action_description)
      SELECT definition_id,definition_version,action_description,distance FROM collapsed
      ORDER BY distance,definition_id LIMIT %s"""


class DecisionExampleQueries:
    def __init__(self, *, repository, options: QueryOptions):
        self.repository, self.options = repository, options

    def candidates(self, principal, *, generation_id, vector, example_limit, decision_limit):
        if (type(example_limit) is not int or type(decision_limit) is not int
                or not 1 <= decision_limit <= example_limit <= 25):
            raise ValueError("Explicit bounded example/decision limits required.")
        literal = vector_literal(vector)
        with self.repository._connect() as connection, connection.cursor() as cursor:
            ConversationRepository._require_authority(cursor, principal)
            vector_version(cursor)
            cursor.execute("""SELECT set_config('statement_timeout',%s,true),
              set_config('hnsw.iterative_scan','strict_order',true),set_config('hnsw.ef_search',%s,true),
              set_config('hnsw.max_scan_tuples',%s,true)""",
              (str(self.options.timeout_ms),str(self.options.ef_search),str(self.options.max_scan_tuples)))
            parameters = (principal.user_id,principal.workspace_id,generation_id,literal,literal,example_limit,decision_limit)
            cursor.execute(candidate_statement(), parameters)
            rows = cursor.fetchall()
            if len(rows) < decision_limit:
                cursor.execute(candidate_statement(exact=True), parameters)
                rows = cursor.fetchall()
            return tuple(CandidateChoice(f"{row[0]}:{row[1]}",row[0],row[1],row[2]) for row in rows)


@dataclass(frozen=True, slots=True)
class ActiveCandidateSet:
    generation_id: str | None
    activation_epoch: int
    capability_fingerprint: str
    choices: tuple[CandidateChoice,...]


class ActiveDecisionQueries(DecisionExampleQueries):
    def __init__(self, *, activator, options: QueryOptions):
        super().__init__(repository=activator.repository,options=options)
        self.activator = activator

    def retrieve(self, principal, *, vector, example_limit, decision_limit):
        from app.vault_runtime.decision_learning.activation import CatalogRule
        from app.vault_runtime.decision_learning.repository import ReviewConflictError
        from .capabilities import CapabilitySnapshot
        if (type(example_limit) is not int or type(decision_limit) is not int
                or not 1 <= decision_limit <= example_limit <= 25):
            raise ValueError("Explicit bounded example/decision limits required.")
        literal = vector_literal(vector)
        scope = (principal.user_id,principal.workspace_id)
        with self.repository._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            ConversationRepository._require_authority(cursor,principal)
            vector_version(cursor)
            cursor.execute("""SELECT set_config('statement_timeout',%s,true),
              set_config('hnsw.iterative_scan','strict_order',true),set_config('hnsw.ef_search',%s,true),
              set_config('hnsw.max_scan_tuples',%s,true)""",
              (str(self.options.timeout_ms),str(self.options.ef_search),str(self.options.max_scan_tuples)))
            cursor.execute("""SELECT a.generation_id,a.epoch,g.state FROM vault_private.vault_decision_activations a
              LEFT JOIN vault_private.vault_decision_generations g USING(user_id,workspace_id,generation_id)
              WHERE a.user_id=%s AND a.workspace_id=%s FOR SHARE OF a""",scope)
            pointer = cursor.fetchone()
            capabilities = self.activator.current_capabilities(cursor,principal)
            if type(capabilities) is not CapabilitySnapshot:
                raise ReviewConflictError("Current capabilities unavailable.")
            if not pointer or not pointer[0] or pointer[2]!="active":
                return ActiveCandidateSet(None,pointer[1] if pointer else 0,capabilities.fingerprint,())
            generation_id,epoch,_ = pointer
            parameters = (*scope,generation_id,literal,literal,example_limit,decision_limit)
            cursor.execute(candidate_statement(active=True),parameters)
            rows = cursor.fetchall()
            if len(rows)<decision_limit:
                cursor.execute(candidate_statement(exact=True,active=True),parameters)
                rows = cursor.fetchall()
            choices = []
            for definition_id,version,description,_ in rows:
                cursor.execute("""SELECT conditions_json,required_slots_json,capability_refs_json,exclusions_json
                  FROM vault_private.vault_decision_definitions WHERE user_id=%s AND workspace_id=%s
                    AND generation_id=%s AND definition_id=%s AND version=%s AND status='active' FOR SHARE""",
                  (*scope,generation_id,definition_id,version))
                definition = cursor.fetchone()
                if not definition:
                    continue
                cursor.execute("""SELECT DISTINCT source_review_id FROM vault_private.vault_decision_examples
                  WHERE user_id=%s AND workspace_id=%s AND generation_id=%s AND definition_id=%s
                    AND definition_version=%s AND enabled ORDER BY source_review_id""",
                  (*scope,generation_id,definition_id,version))
                sources = tuple(r[0] for r in cursor.fetchall())
                rule = CatalogRule(definition_id,version,description,definition[0],tuple(definition[1]),
                    tuple(definition[2]),tuple(definition[3]),sources)
                if sources and capabilities.read_only(rule.capability_ids) and self.activator.qualify_rule(cursor,principal,rule) is True:
                    import json
                    applicability = json.dumps(dict(description=description,conditions=rule.conditions,
                        required_slots=rule.required_slots,capabilities=rule.capability_ids,
                        exclusions=rule.exclusions),ensure_ascii=False,sort_keys=True)
                    choices.append(CandidateChoice(f"{definition_id}:{version}",definition_id,version,applicability))
            if self.activator.current_capabilities(cursor,principal) != capabilities:
                raise ReviewConflictError("Capabilities changed during retrieval.")
            return ActiveCandidateSet(generation_id,epoch,capabilities.fingerprint,tuple(choices))
