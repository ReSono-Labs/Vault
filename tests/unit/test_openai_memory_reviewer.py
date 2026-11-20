from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.vault_runtime.memory.openai_reviewer import (
    MemoryReviewProviderError,
    OpenAIMemoryReviewer,
)


class _Credentials:
    def background_access(self, *, user_id: str, workspace_id: str):
        assert (user_id, workspace_id) == ("user-1", "workspace-1")
        return SimpleNamespace(value="secret"), "gpt-5.6-sol"


def test_window_reviewer_uses_typed_continuation_on_shared_runner():
    calls=[]
    def execute(**kwargs):
        calls.append(kwargs)
        return dict(contractVersion=2,summary='Reviewed window',candidates=[],hasMore=False)
    reviewer=OpenAIMemoryReviewer(credentials=_Credentials(),user_id='user-1',workspace_id='workspace-1',executor=execute)
    review,more=reviewer.review_page('{"evidence":"[entryIndex=7] user: hello","excludedKeys":[]}')
    assert not more and not review.memories
    assert calls[0]['agent_name']=='Vault Memory Window Review'
    assert 'hasMore' in calls[0]['output_type'].model_json_schema()['properties']


def _reviewer(output):
    def execute(**kwargs):
        assert kwargs["agent_name"] == "Vault Memory Review"
        assert kwargs["max_turns"] == 4
        assert kwargs["api_key"] == "secret"
        assert kwargs["reasoning_effort"] == "medium"
        return output
    return OpenAIMemoryReviewer(
        credentials=_Credentials(), user_id="user-1", workspace_id="workspace-1",
        executor=execute,
    )


def test_r1_reviewer_maps_cited_candidate_to_exact_contract() -> None:
    review = _reviewer({
        "contractVersion": 2, "summary": "User prefers tea.", "candidates": [{
            "domain": "personal", "memoryType": "preference", "stableKey": "drink.tea",
            "content": "Prefers tea", "sourceEntryIndexes": [3],
            "sourceAuthority": "user_asserted", "confidence": "high",
            "sensitivity": "normal", "reconciliationIntent": "create",
            "shouldStore": True,
        }],
    }).review("[entryIndex=3] [voice.user.final] user: I prefer tea")
    assert review.contract_version == 2
    assert review.model == "gpt-5.6-sol"
    assert review.memories[0].source_entry_indexes == (3,)
    assert review.memories[0].memory.subject_id == "user-1"
    assert review.memories[0].memory.domain == "personal"


def test_reviewer_rejects_wrong_contract_and_filters_secrets_or_uncited_items() -> None:
    with pytest.raises(MemoryReviewProviderError):
        _reviewer({"contractVersion": 1, "summary": "x", "candidates": []}).review("x")
    review = _reviewer({
        "contractVersion": 2, "summary": "Nothing safe.", "candidates": [
            {"domain": "personal", "memoryType": "fact", "stableKey": "secret",
             "content": "API key is abc", "sourceEntryIndexes": [0]},
            {"domain": "personal", "memoryType": "fact", "stableKey": "uncited",
             "content": "Uncited", "sourceEntryIndexes": []},
        ],
    }).review("[entryIndex=0] user: unsafe")
    assert review.memories == ()


def test_reviewer_surfaces_provider_failure_without_fabricating_learning() -> None:
    def fail(**_kwargs):
        raise RuntimeError("provider down")
    reviewer = OpenAIMemoryReviewer(
        credentials=_Credentials(), user_id="user-1", workspace_id="workspace-1",
        executor=fail,
    )
    with pytest.raises(MemoryReviewProviderError):
        reviewer.review("[entryIndex=0] user: remember tea")


def test_reviewer_bounds_candidates_and_rejects_empty_or_malformed_output() -> None:
    candidates = [{
        "domain": "personal", "memoryType": "fact", "stableKey": f"fact-{index}",
        "content": f"Fact {index}", "sourceEntryIndexes": [0],
        "sourceAuthority": "model_derived", "confidence": "medium",
        "sensitivity": "normal", "reconciliationIntent": "create",
        "shouldStore": True,
    } for index in range(33)]
    with pytest.raises(MemoryReviewProviderError,match="pagination"):
        _reviewer({"contractVersion":2,"summary":"Bounded","candidates":candidates}).review("[entryIndex=0] user: facts")
    review = _reviewer({"contractVersion":2,"summary":"Bounded","candidates":candidates[:32]}).review("[entryIndex=0] user: facts")
    assert len(review.memories)==32
    with pytest.raises(ValueError):
        _reviewer({}).review("  ")
    with pytest.raises(MemoryReviewProviderError):
        _reviewer("not json").review("[entryIndex=0] user: facts")


def test_oversized_transcript_never_calls_provider_or_reports_truncated_success():
    calls = []
    reviewer = OpenAIMemoryReviewer(credentials=_Credentials(),user_id="user-1",workspace_id="workspace-1",
        executor=lambda **kwargs:calls.append(kwargs))
    with pytest.raises(MemoryReviewProviderError,match="bounded-window"):
        reviewer.review("x"*100001)
    assert calls==[]
    with pytest.raises(MemoryReviewProviderError,match="consolidation"):
        _reviewer({"contractVersion":2,"summary":"x"*20001,"candidates":[]}).review("valid input")
