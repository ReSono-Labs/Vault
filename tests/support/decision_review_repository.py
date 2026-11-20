"""Shared test helpers moved out of test modules (TST-01)."""

from app.vault_runtime.decision_learning.repository import DecisionReviewRepository, source_fingerprint
from app.vault_runtime.decision_learning.reviewer import ProceduralReview, ReviewOutput
from tests.support.decision_learning_reviewer import output, snapshot


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
