from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import psycopg
import pytest

from app.vault_runtime.conversation.contracts import AuthorizationError
from app.vault_runtime.decision_learning.repository import DecisionReviewRepository, ReviewConflictError, source_fingerprint
from app.vault_runtime.decision_learning.reviewer import ProceduralReview, ReviewOutput
from tests.integration.test_conversation_identity_postgres import context, share
from tests.unit.test_decision_learning_reviewer import snapshot, output


def setup(context, *, principal=None, gate=None, key="decisions-review"):
    url, service, owner, second, conversations = context
    principal = principal or owner.principal
    conversation = conversations.create(principal, key)
    data = snapshot().model_dump()
    data.update(conversation_id=conversation.conversation_id, segment_id=conversation.segments[0].segment_id)
    from app.vault_runtime.decision_learning.reviewer import ReviewInput
    source = ReviewInput.model_validate(data)
    repository = DecisionReviewRepository(database_url=url, source_current=gate or (lambda *_: True))
    repository.ensure_schema()
    repository.ensure_schema()
    review = ProceduralReview(source_fingerprint(source), "synthetic-model", ReviewOutput.model_validate(output()))
    return repository, source, review


def test_concurrent_claim_exact_retry_conflict_and_no_source_payload_duplication(context):
    url, service, owner, second, conversations = context
    repository, source, review = setup(context)
    barrier = Barrier(2)
    def claim():
        barrier.wait()
        return repository.claim(owner.principal, source, lease_seconds=30)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: claim(), range(2)))
    acquired = [c for c in claims if c is not None]
    assert len(acquired) == 1
    claim = acquired[0]
    assert repository.complete(owner.principal, claim, source, review, provider="synthetic") is False
    assert repository.complete(owner.principal, claim, source, review, provider="synthetic") is True
    assert repository.claim(owner.principal, source, lease_seconds=30) is None
    state, model, result = repository.get(owner.principal, claim.review_id)
    assert state == "completed" and model == "synthetic-model" and result == review.output
    different = ProceduralReview(review.source_fingerprint, review.model, ReviewOutput.model_validate(output(description="changed")))
    with pytest.raises(ReviewConflictError):
        repository.complete(owner.principal, claim, source, different, provider="synthetic")
    shared = share(service, owner, second)
    with pytest.raises(ReviewConflictError):
        repository.get(shared, claim.review_id)
    with pytest.raises(ReviewConflictError):
        repository.claim(shared, source, lease_seconds=30)
    with psycopg.connect(url) as connection:
        row = connection.execute("SELECT count(*),max(attempts) FROM vault_private.vault_decision_reviews").fetchone()
        assert row == (1, 1)
        stored = connection.execute("SELECT learner_contract_version,assessments_json FROM vault_private.vault_decision_reviews").fetchone()
        assert stored[0] == 3 and stored[1] == review.output.model_dump(mode="json")["assessments"]
        columns = {r[0] for r in connection.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='vault_private' AND table_name='vault_decision_reviews'")}
        assert "input_text" not in columns and "source_payload" not in columns


def test_model_stage_checkpoint_survives_retry_and_fences_old_worker(context):
    _, _, owner, _, _ = context
    current = [True]
    repository, source, review = setup(context, gate=lambda *_: current[0])
    first = repository.claim(owner.principal, source, lease_seconds=30)
    value = {"provider": "synthetic", "model": review.model, "output": review.output.model_dump(mode="json")}
    assert repository.stage(owner.principal, first, source, name="analysis", value=value) == value
    assert repository.stage(owner.principal, first, source, name="analysis") == value
    with pytest.raises(ReviewConflictError):
        repository.stage(owner.principal, first, source, name="analysis", value={"changed": True})
    repository.retryable(owner.principal, first)
    second = repository.claim(owner.principal, source, lease_seconds=30)
    assert repository.stage(owner.principal, second, source, name="analysis") == value
    with pytest.raises(ReviewConflictError):
        repository.stage(owner.principal, first, source, name="analysis")
    current[0] = False
    with pytest.raises(ReviewConflictError):
        repository.stage(owner.principal, second, source, name="analysis")


def test_failed_outcome_assessments_survive_checkpoint_and_cannot_be_overwritten(context):
    from copy import deepcopy
    url,_,owner,_,_ = context
    repository,source,original = setup(context)
    data = original.output.model_dump(mode="json")
    data["proposals"][0]["disposition"] = "insufficient_evidence"
    data["assessments"][0]["context_selection"]["judgment"] = "incorrect"
    data["assessments"][0]["failure_stage"] = "context_selection"
    review = ProceduralReview(source_fingerprint(source),"synthetic-model",ReviewOutput.model_validate(data))
    claim = repository.claim(owner.principal,source,lease_seconds=30)
    repository.complete(owner.principal,claim,source,review,provider="synthetic")
    assert repository.get(owner.principal,claim.review_id)[2].assessments[0].context_selection.judgment == "incorrect"
    assert repository.for_source(owner.principal,source)[4] == review.output
    different = deepcopy(data)
    different["assessments"][0]["context_selection"]["explanation"] = "Altered assessment"
    with pytest.raises(ReviewConflictError,match="overwritten"):
        repository.complete(owner.principal,claim,source,ProceduralReview(source_fingerprint(source),"synthetic-model",ReviewOutput.model_validate(different)),provider="synthetic")
    # Old checkpoints stay stored but are not fabricated into the new contract.
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE vault_private.vault_decision_reviews SET learner_contract_version=1 WHERE review_id=%s",(claim.review_id,))
    with pytest.raises(ReviewConflictError,match="Historical"):
        repository.get(owner.principal,claim.review_id)


def test_expired_and_retryable_leases_fence_previous_workers_and_source_changes(context):
    url, _, owner, _, _ = context
    current = [True]
    repository, source, review = setup(context, gate=lambda *_: current[0])
    first = repository.claim(owner.principal, source, lease_seconds=30)
    repository.retryable(owner.principal, first)
    second = repository.claim(owner.principal, source, lease_seconds=30)
    assert second.review_id == first.review_id and second.attempt == 2 and second.token != first.token
    with pytest.raises(ReviewConflictError):
        repository.complete(owner.principal, first, source, review, provider="synthetic")
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE vault_private.vault_decision_reviews SET lease_until=clock_timestamp()-interval '1 second'")
    with pytest.raises(ReviewConflictError):
        repository.complete(owner.principal, second, source, review, provider="synthetic")
    third = repository.claim(owner.principal, source, lease_seconds=30)
    assert third.attempt == 3
    changed = source.model_copy(update={"segment_id": "changed"})
    with pytest.raises(ReviewConflictError, match="source changed"):
        repository.complete(owner.principal, third, changed, review, provider="synthetic")
    bad_review = ProceduralReview(review.source_fingerprint, review.model,
        review.output.model_copy(update={"contract_version": 4}))
    with pytest.raises(ValueError):
        repository.complete(owner.principal, third, source, bad_review, provider="synthetic")
    current[0] = False
    with pytest.raises(ReviewConflictError):
        repository.complete(owner.principal, third, source, review, provider="synthetic")
    assert repository.get(owner.principal, third.review_id)[0] == "running"
    current[0] = True
    assert repository.complete(owner.principal, third, source, review, provider="synthetic") is False


def test_current_authority_and_existing_conversation_erasure_cascade(context):
    url, service, owner, second, conversations = context
    repository, source, review = setup(context, principal=second.principal)
    claim = repository.claim(second.principal, source, lease_seconds=30)
    repository.complete(second.principal, claim, source, review, provider="synthetic")
    owner_conversation = conversations.create(owner.principal, "retained-owner")
    service.remove_user(actor=owner.principal, user_id=second.principal.user_id)
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_decision_reviews").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM vault_private.vault_conversations WHERE conversation_id=%s", (owner_conversation.conversation_id,)).fetchone()[0] == 1
    with pytest.raises(AuthorizationError):
        repository.get(second.principal, claim.review_id)


def test_model_wait_renews_same_claim_and_rechecks_source(context, monkeypatch):
    import time
    from app.vault_runtime.decision_learning import repository as module
    url, _, owner, _, _ = context
    current=[True]
    repository, source, review=setup(context,gate=lambda *_:current[0])
    claim=repository.claim(owner.principal,source,lease_seconds=1)
    monkeypatch.setattr(module,'LEASE_RENEW_SECONDS',0.05)
    with repository.keepalive(owner.principal,claim,source):
        with psycopg.connect(url) as con:
            con.execute("UPDATE vault_private.vault_decision_reviews SET lease_until=clock_timestamp()+interval '0.1 seconds' WHERE review_id=%s",(claim.review_id,))
        time.sleep(0.2)
        with psycopg.connect(url) as con:
            row=con.execute("SELECT attempts,lease_owner,lease_until>clock_timestamp()+interval '100 seconds' FROM vault_private.vault_decision_reviews WHERE review_id=%s",(claim.review_id,)).fetchone()
        assert row==(claim.attempt,claim.token,True)
    assert repository.complete(owner.principal,claim,source,review,provider='synthetic') is False
    # Source invalidation cannot be overridden by lease renewal.
    repository, source, _=setup(context,gate=lambda *_:current[0],key="lease-revocation")
    claim=repository.claim(owner.principal,source,lease_seconds=1)
    with pytest.raises(ReviewConflictError):
        with repository.keepalive(owner.principal,claim,source):
            current[0]=False
