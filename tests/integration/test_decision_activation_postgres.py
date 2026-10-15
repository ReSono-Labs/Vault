from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import psycopg
import pytest

from app.vault_runtime.decision_learning.activation import CatalogActivator, Activation
from app.vault_runtime.decision_learning.repository import source_fingerprint, ReviewConflictError
from app.vault_runtime.decision_learning.reviewer import ReviewInput, ReviewOutput, ProceduralReview
from app.vault_runtime.decision_routing.capabilities import CapabilitySnapshot, ResolvedCapability
from tests.integration.test_conversation_identity_postgres import context, share
from tests.integration.test_decision_rules_postgres import published, VECTOR
from tests.unit.test_decision_learning_reviewer import output


def embedded(rules,owner,source,generation):
    for example_id,text,_ in rules.examples(owner.principal,generation):
        rules.store_vector(owner.principal,generation_id=generation,example_id=example_id,snapshot=source,
            example_text=text,vector=VECTOR,provider="ollama",model="embeddinggemma:300m")


def next_generation(context,rules,source,*,description="Balance lookup",target=None,version=1,disposition=None):
    _,_,owner,_,conversations = context
    conversation = conversations.create(owner.principal,description+str(version))
    data = source.model_dump()
    data.update(conversation_id=conversation.conversation_id,segment_id=conversation.segments[0].segment_id)
    if target:
        data["existing_decisions"] = [dict(definition_id=target,version=version,description="prior")]
    source = ReviewInput.model_validate(data)
    review = ProceduralReview(source_fingerprint(source),"synthetic-model",ReviewOutput.model_validate(output(
        description=description,target_definition_id=target,disposition=disposition or ("revise" if target else "create"))))
    claim = rules.claim(owner.principal,source,lease_seconds=30)
    rules.complete(owner.principal,claim,source,review,provider="synthetic")
    generation = rules.publish(owner.principal,review_id=claim.review_id,snapshot=source,review=review)
    embedded(rules,owner,source,generation)
    return source,generation


def activator(rules,*,qualify=None,capabilities=None):
    capability = CapabilitySnapshot("synthetic-current",(ResolvedCapability("accounting.invoice.read",
        "tool","Invoice lookup","synthetic","read","{}"),),())
    result = CatalogActivator(repository=rules,qualify_rule=qualify or (lambda *_:True),
        current_capabilities=capabilities or (lambda *_:capability))
    result.ensure_schema()
    result.ensure_schema()
    return result


def test_additive_activation_revision_retry_and_source_erasure(context):
    url,_,owner,_,_ = context
    rules,source,_,claim,first = published(context)
    embedded(rules,owner,source,first)
    catalog = activator(rules)
    args = dict(generation_id=first,expected_epoch=0,policy_version="test-read-only-v1")
    assert catalog.activate(owner.principal,**args) == Activation(first,1)
    assert catalog.activate(owner.principal,**args) == Activation(first,1)
    _,second = next_generation(context,rules,source)
    assert catalog.activate(owner.principal,generation_id=second,expected_epoch=1,policy_version="test-read-only-v1") == Activation(second,2)
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_decision_definitions WHERE generation_id=%s AND status='active'",(second,)).fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM vault_private.vault_decision_examples WHERE generation_id=%s",(second,)).fetchone()[0] == 4
        definition = connection.execute("SELECT definition_id FROM vault_private.vault_decision_definitions WHERE generation_id=%s",(first,)).fetchone()[0]
    _,third = next_generation(context,rules,source,description="Invoice lookup revised",target=definition)
    catalog.activate(owner.principal,generation_id=third,expected_epoch=2,policy_version="test-read-only-v1")
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT version FROM vault_private.vault_decision_definitions WHERE generation_id=%s AND definition_id=%s",(third,definition)).fetchone() == (2,)
        assert connection.execute("SELECT count(*) FROM vault_private.vault_decision_definitions WHERE generation_id=%s",(third,)).fetchone()[0] == 2
        # Delete a retained rule's original source, not the newest generation review.
        retained = connection.execute("SELECT source_review_id FROM vault_private.vault_decision_examples WHERE generation_id=%s AND definition_id<>%s LIMIT 1",(third,definition)).fetchone()[0]
        connection.execute("DELETE FROM vault_private.vault_decision_reviews WHERE review_id=%s",(retained,))
    assert catalog.current(owner.principal) == Activation(None,4)
    with psycopg.connect(url) as connection:
        connection.execute("DELETE FROM vault_private.vault_conversations WHERE conversation_id=%s",(source.conversation_id,))
    assert catalog.current(owner.principal) == Activation(None,4)


def test_failed_compilation_rolls_back_merge_and_pointer_and_requalifies_old_rules(context):
    url,_,owner,_,_ = context
    rules,source,_,_,first = published(context)
    embedded(rules,owner,source,first)
    catalog = activator(rules)
    catalog.activate(owner.principal,generation_id=first,expected_epoch=0,policy_version="test")
    _,second = next_generation(context,rules,source)
    seen = []
    def fail(cursor,principal,rule):
        seen.append(rule.description)
        if rule.description == "Invoice status lookup":
            raise RuntimeError("synthetic source gate failure")
        return True
    failing = activator(rules,qualify=fail)
    with pytest.raises(RuntimeError):
        failing.activate(owner.principal,generation_id=second,expected_epoch=1,policy_version="test")
    assert "Invoice status lookup" in seen
    assert catalog.current(owner.principal) == Activation(first,1)
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_decision_definitions WHERE generation_id=%s",(second,)).fetchone()[0] == 1
        assert connection.execute("SELECT state FROM vault_private.vault_decision_generations WHERE generation_id=%s",(second,)).fetchone() == ("building",)
    # Suppressed old source stays stored but inactive, while qualified new read rule activates.
    selective = activator(rules,qualify=lambda c,p,r:r.description!="Invoice status lookup")
    selective.activate(owner.principal,generation_id=second,expected_epoch=1,policy_version="test")
    with psycopg.connect(url) as connection:
        assert set(connection.execute("SELECT action_description,status FROM vault_private.vault_decision_definitions WHERE generation_id=%s",(second,))) == {("Invoice status lookup","inactive"),("Balance lookup","active")}


def test_missing_vectors_writes_scope_and_current_capability_change_fail_closed(context):
    _,service,owner,second,_ = context
    rules,source,_,_,generation = published(context)
    catalog = activator(rules)
    args = dict(generation_id=generation,expected_epoch=0,policy_version="test")
    with pytest.raises(ReviewConflictError,match="indexed examples"):
        catalog.activate(owner.principal,**args)
    embedded(rules,owner,source,generation)
    write = CapabilitySnapshot("write",(ResolvedCapability("accounting.invoice.read","tool","Name","provider","write","{}"),),())
    with pytest.raises(ReviewConflictError,match="No qualified"):
        activator(rules,capabilities=lambda *_:write).activate(owner.principal,**args)
    shared = share(service,owner,second)
    with pytest.raises(ReviewConflictError,match="Owned"):
        catalog.activate(shared,**args)
    captures = iter((CapabilitySnapshot("a",(ResolvedCapability("accounting.invoice.read","tool","Name","provider","read","{}"),),()),write))
    with pytest.raises(ReviewConflictError,match="changed during"):
        activator(rules,capabilities=lambda *_:next(captures)).activate(owner.principal,**args)
    assert catalog.current(owner.principal) == Activation(None,0)


def test_concurrent_cas_one_winner_preserves_catalog(context):
    _,_,owner,_,_ = context
    rules,source,_,_,first = published(context)
    embedded(rules,owner,source,first)
    _,second = next_generation(context,rules,source)
    catalog = activator(rules)
    barrier = Barrier(2)
    def attempt(generation):
        barrier.wait()
        try:
            return catalog.activate(owner.principal,generation_id=generation,expected_epoch=0,policy_version="test")
        except ReviewConflictError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt,(first,second)))
    assert sum(r is not None for r in results)==1
    assert catalog.current(owner.principal).epoch==1


def test_active_indexed_reads_recheck_sources_capabilities_scope_and_erasure(context):
    from app.vault_runtime.decision_routing.example_index import ActiveDecisionQueries,ensure_example_index
    from app.vault_runtime.memory_search.postgres import QueryOptions
    url,service,owner,second,_ = context
    rules,source,_,_,generation = published(context)
    embedded(rules,owner,source,generation)
    qualified = [True]
    available = [True]
    read = CapabilitySnapshot("read-current",(ResolvedCapability("accounting.invoice.read","tool","Name","provider","read","{}"),),())
    empty = CapabilitySnapshot("revoked",(),("accounting.invoice.read",))
    catalog = activator(rules,qualify=lambda *_:qualified[0],capabilities=lambda *_:read if available[0] else empty)
    catalog.activate(owner.principal,generation_id=generation,expected_epoch=0,policy_version="test")
    with psycopg.connect(url,autocommit=True) as connection:
        ensure_example_index(connection)
    query = ActiveDecisionQueries(activator=catalog,options=QueryOptions(timeout_ms=3000,ef_search=40,max_scan_tuples=1000))
    def retrieve(principal=owner.principal):
        return query.retrieve(principal,vector=VECTOR,example_limit=20,decision_limit=5)
    result = retrieve()
    assert result.generation_id == generation and result.activation_epoch == 1
    assert result.capability_fingerprint == "read-current" and len(result.choices)==1
    qualified[0] = False
    assert retrieve().choices == ()
    qualified[0] = True
    available[0] = False
    assert retrieve().choices == ()
    available[0] = True
    shared = share(service,owner,second)
    assert retrieve(shared).generation_id is None and retrieve(shared).choices == ()
    with psycopg.connect(url) as connection:
        connection.execute("DELETE FROM vault_private.vault_conversations WHERE conversation_id=%s",(source.conversation_id,))
    result = retrieve()
    assert result.generation_id is None and result.activation_epoch==2 and result.choices==()


def test_stale_revision_and_account_erasure(context):
    url,service,owner,second,_ = context
    rules,source,_,_,first = published(context)
    embedded(rules,owner,source,first)
    catalog = activator(rules)
    with psycopg.connect(url) as connection:
        definition = connection.execute("SELECT definition_id FROM vault_private.vault_decision_definitions WHERE generation_id=%s",(first,)).fetchone()[0]
    _,revision = next_generation(context,rules,source,description="revision",target=definition)
    with pytest.raises(ReviewConflictError,match="predecessor"):
        catalog.activate(owner.principal,generation_id=revision,expected_epoch=0,policy_version="test")
    catalog.activate(owner.principal,generation_id=first,expected_epoch=0,policy_version="test")
    _,bad = next_generation(context,rules,source,description="stale revision",target=definition,version=3)
    with pytest.raises(ReviewConflictError,match="advance"):
        catalog.activate(owner.principal,generation_id=bad,expected_epoch=1,policy_version="test")
    assert catalog.current(owner.principal)==Activation(first,1)
    from tests.integration.test_decision_review_repository_postgres import setup
    from app.vault_runtime.decision_learning.rules import DecisionRuleRepository
    checkpoint,other_source,review = setup(context,principal=second.principal)
    claim = checkpoint.claim(second.principal,other_source,lease_seconds=30)
    checkpoint.complete(second.principal,claim,other_source,review,provider="synthetic")
    other_rules = DecisionRuleRepository(database_url=url,source_current=lambda *_:True)
    other = other_rules.publish(second.principal,review_id=claim.review_id,snapshot=other_source,review=review)
    embedded(other_rules,second,other_source,other)
    catalog.activate(second.principal,generation_id=other,expected_epoch=0,policy_version="test")
    service.remove_user(actor=owner.principal,user_id=second.principal.user_id)
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_decision_activations WHERE user_id=%s",(second.principal.user_id,)).fetchone()[0]==0
    assert catalog.current(owner.principal)==Activation(first,1)


def test_example_only_learning_preserves_evidence_and_cannot_change_behavior(context):
    url,_,owner,_,_ = context
    rules,source,_,_,first = published(context)
    embedded(rules,owner,source,first)
    catalog = activator(rules)
    catalog.activate(owner.principal,generation_id=first,expected_epoch=0,policy_version="test")
    with psycopg.connect(url) as connection:
        definition = connection.execute("SELECT definition_id FROM vault_private.vault_decision_definitions WHERE generation_id=%s",(first,)).fetchone()[0]
    _,bad = next_generation(context,rules,source,description="Changed meaning",target=definition,disposition="add_example")
    with pytest.raises(ReviewConflictError,match="authoritative"):
        catalog.activate(owner.principal,generation_id=bad,expected_epoch=1,policy_version="test")
    _,second = next_generation(context,rules,source,description="Invoice status lookup",target=definition,disposition="add_example")
    catalog.activate(owner.principal,generation_id=second,expected_epoch=1,policy_version="test")
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT count(*),count(DISTINCT source_review_id) FROM vault_private.vault_decision_examples WHERE generation_id=%s",(second,)).fetchone() == (4,2)
        assert connection.execute("SELECT count(*),max(version) FROM vault_private.vault_decision_definitions WHERE generation_id=%s",(second,)).fetchone() == (1,2)
