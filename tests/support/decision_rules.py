"""Shared test helpers moved out of test modules (TST-01)."""

from app.vault_runtime.decision_learning.rules import DecisionRuleRepository
from tests.support.decision_review_repository import setup


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
