from dataclasses import replace
import math

import psycopg
import pytest

from app.vault_runtime.decision_learning.rules import DecisionRuleRepository
from app.vault_runtime.decision_learning.repository import source_fingerprint, ReviewConflictError
from app.vault_runtime.decision_learning.reviewer import ReviewInput, ReviewOutput, ProceduralReview
from app.vault_runtime.decision_routing.example_index import DecisionExampleQueries, ensure_example_index, NAME, candidate_statement
from app.vault_runtime.memory_search.postgres import QueryOptions, vector_literal
from tests.integration.test_conversation_identity_postgres import context, share
from tests.integration.test_decision_review_repository_postgres import setup
from tests.unit.test_decision_learning_reviewer import output


VECTOR = (1.0,) + (0.0,) * 767


def published(context, *, gate=None):
    url, _, owner, _, _ = context
    checkpoint, source, review = setup(context)
    claim = checkpoint.claim(owner.principal, source, lease_seconds=30)
    checkpoint.complete(owner.principal, claim, source, review, provider="synthetic")
    rules = DecisionRuleRepository(database_url=url, source_current=gate or (lambda *_: True))
    rules.ensure_schema()
    rules.ensure_schema()
    generation = rules.publish(owner.principal, review_id=claim.review_id, snapshot=source, review=review)
    return rules, source, review, claim, generation


def test_real_publication_vector_index_and_sql_private_retrieval(context):
    url, service, owner, second, conversations = context
    rules, source, review, claim, generation = published(context)
    assert rules.publish(owner.principal, review_id=claim.review_id, snapshot=source, review=review) == generation
    examples = rules.examples(owner.principal, generation)
    assert len(examples) == 2 and all(not e[2] for e in examples)
    query = DecisionExampleQueries(repository=rules, options=QueryOptions(timeout_ms=3000,ef_search=40,max_scan_tuples=1000))
    assert query.candidates(owner.principal,generation_id=generation,vector=VECTOR,example_limit=20,decision_limit=5) == ()
    for example_id, text, _ in examples:
        rules.store_vector(owner.principal,generation_id=generation,example_id=example_id,snapshot=source,
            example_text=text,vector=VECTOR,provider="ollama",model="embeddinggemma:300m")
    with psycopg.connect(url, autocommit=True) as connection:
        ensure_example_index(connection)
        ensure_example_index(connection)
        definition = connection.execute("SELECT pg_get_indexdef(indexrelid) FROM pg_index JOIN pg_class ON oid=indexrelid WHERE relname=%s",(NAME,)).fetchone()[0]
        assert "USING hnsw" in definition
    candidates = query.candidates(owner.principal,generation_id=generation,vector=VECTOR,example_limit=20,decision_limit=5)
    assert len(candidates) == 1 and candidates[0].applicability_description == "Invoice status lookup"
    shared = share(service, owner, second)
    assert query.candidates(shared,generation_id=generation,vector=VECTOR,example_limit=20,decision_limit=5) == ()
    with psycopg.connect(url) as connection:
        rows = connection.execute("SELECT example_kind,outcome_class FROM vault_private.vault_decision_examples").fetchall()
        assert set(rows) == {("observed","resolved"),("synthetic","unknown")}
        assert connection.execute("SELECT state FROM vault_private.vault_decision_generations").fetchone()[0] == "building"
        connection.execute("SET enable_seqscan=off")
        # Direct ANN expression proves this actual owned partial index is usable;
        # tiny test data does not prove production's naturally selected plan.
        from app.vault_runtime.decision_routing.example_index import PREDICATE
        plan = connection.execute(f"EXPLAIN SELECT example_id FROM vault_private.vault_decision_examples WHERE {PREDICATE} ORDER BY embedding::vector(768) <=> %s::vector(768) LIMIT 5",(vector_literal(VECTOR),)).fetchall()
        assert NAME in "\n".join(r[0] for r in plan)


def test_vector_identity_content_freshness_and_module_removal(context):
    url, _, owner, _, _ = context
    current = [True]
    rules, source, review, claim, generation = published(context, gate=lambda *_: current[0])
    example_id, text, _ = rules.examples(owner.principal,generation)[0]
    args = dict(generation_id=generation,example_id=example_id,snapshot=source,example_text=text,
        vector=VECTOR,provider="ollama",model="embeddinggemma:300m")
    for changes in (dict(vector=(1.0,)),dict(vector=(0.0,)*768),dict(vector=(math.nan,)+(0.0,)*767),dict(model="different")):
        with pytest.raises(ValueError):
            rules.store_vector(owner.principal,**(args|changes))
    with pytest.raises(ReviewConflictError):
        rules.store_vector(owner.principal,**(args|dict(example_text="changed")))
    current[0] = False
    with pytest.raises(ReviewConflictError):
        rules.store_vector(owner.principal,**args)
    current[0] = True
    rules.store_vector(owner.principal,**args)
    rules.drop_inactive(owner.principal,generation)
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_decision_examples").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM vault_private.vault_decision_reviews").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM vault_private.vault_conversations").fetchone()[0] == 1


def test_publication_requires_exact_review_and_source_and_erasure_cascades(context):
    url, _, owner, _, _ = context
    rules, source, review, claim, generation = published(context)
    with pytest.raises(ReviewConflictError):
        rules.publish(owner.principal,review_id=claim.review_id,snapshot=source,
            review=replace(review,output=ReviewOutput.model_validate(output(description="changed"))))
    with psycopg.connect(url) as connection:
        connection.execute("DELETE FROM vault_private.vault_conversations WHERE conversation_id=%s",(source.conversation_id,))
        for table in ("vault_decision_reviews","vault_decision_generations","vault_decision_definitions","vault_decision_examples"):
            assert connection.execute(f"SELECT count(*) FROM vault_private.{table}").fetchone()[0] == 0
