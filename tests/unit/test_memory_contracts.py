import pytest

from app.vault_runtime.memory.contracts import (
    MemoryCandidate,
    MemoryContractError,
    MemoryReview,
    ReviewedMemoryCandidate,
)


def candidate(**changes: str) -> MemoryCandidate:
    values = {
        "subject_id": "user",
        "domain": "personal",
        "memory_type": "preference",
        "memory_key": "drink",
        "content_text": "Prefers tea",
        "source_authority": "user_asserted",
        "confidence": "high",
        "sensitivity": "normal",
        "intent": "create",
        "visibility": "private",
    }
    values.update(changes)
    return MemoryCandidate(**values)


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("domain", "misc"),
        ("memory_type", "note"),
        ("source_authority", "internet"),
        ("confidence", "certain"),
        ("sensitivity", "secret"),
        ("intent", "update"),
        ("visibility", "public"),
    ],
)
def test_unknown_labels_are_rejected(field: str, bad: str) -> None:
    with pytest.raises(MemoryContractError):
        candidate(**{field: bad}).validated()


def test_candidate_is_trimmed_and_keeps_exact_r1_labels() -> None:
    result = candidate(subject_id=" user ", memory_key=" drink ", content_text=" Prefers tea ").validated()
    assert (result.subject_id, result.memory_key, result.content_text) == ("user", "drink", "Prefers tea")
    assert (result.domain, result.memory_type, result.intent) == ("personal", "preference", "create")


def test_contract_v2_review_requires_explicit_citations() -> None:
    with pytest.raises(MemoryContractError, match="citations"):
        MemoryReview(
            summary="Summary", model="reviewer",
            memories=(ReviewedMemoryCandidate(candidate(), ()),),
        ).validated()


def test_older_reviewer_contract_is_not_silently_accepted() -> None:
    with pytest.raises(MemoryContractError, match="version"):
        MemoryReview(summary="Summary", model="reviewer", memories=(), contract_version=1).validated()
