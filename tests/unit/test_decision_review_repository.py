import pytest

from app.vault_runtime.decision_learning.repository import DecisionReviewRepository, source_fingerprint
from tests.unit.test_decision_learning_reviewer import snapshot


@pytest.mark.parametrize("duration", [True, 0, -1, 1.5])
def test_invalid_lease_does_not_open_database(duration):
    def forbidden(*_):
        pytest.fail("Invalid configuration must not open DB")
    repository = DecisionReviewRepository(database_url="unused", source_current=lambda *_: True, connector=forbidden)
    with pytest.raises(ValueError):
        repository.claim(None, snapshot(), lease_seconds=duration)


def test_required_source_gate_and_unchecked_input_are_rejected():
    with pytest.raises(ValueError):
        DecisionReviewRepository(database_url="unused", source_current=None)
    source = snapshot()
    assert len(source_fingerprint(source)) == 64
    assert source_fingerprint(source) == source_fingerprint(source)
    bad_source = source.sources[0].model_copy(update={"kind": "draft"})
    with pytest.raises(ValueError):
        source_fingerprint(source.model_copy(update={"sources": (bad_source, source.sources[1])}))
