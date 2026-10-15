from types import SimpleNamespace

import pytest

from app.vault_runtime.decision_learning.finalization import review_session
from app.vault_runtime.decision_learning.reviewer import (
    DecisionReviewer, DecisionReviewError, ReviewInput, ReviewOutput,
)
from app.vault_runtime.memory.openai_reviewer import OpenAIMemoryReviewer


class Credentials:
    def selected_provider(self, **scope):
        assert scope == {"user_id": "u", "workspace_id": "w"}
        return "openai"

    def background_access(self, **scope):
        assert scope == {"user_id": "u", "workspace_id": "w", "provider_key": "openai"}
        return SimpleNamespace(value="synthetic-key", auth_method="api_key"), "configured-model"


def snapshot(**changes):
    data = dict(conversation_id="c", segment_id="s", coverage="complete",
        sources=[dict(source_id="final", kind="user_final", text="Check invoice 482"),
                 dict(source_id="result", kind="tool_result", text="Paid; answered the request"),
                 dict(source_id="answer", kind="assistant_final", text="Invoice 482 is paid")],
        observations=[dict(point_id="p", final_source_id="final", proposal_source_id=None,
            result_source_id="result", capability_id="accounting.invoice.read",
            context_source_ids=[],feedback_source_ids=[],reasoning_source_ids=[],answer_source_id="answer",
            execution="completed", tool_report="non_error", request_outcome="resolved")],
        capabilities=[dict(capability_id="accounting.invoice.read", description="Invoice lookup", effect="read")],
        existing_decisions=[dict(definition_id="existing", version=1, description="Invoice status")])
    data.update(changes)
    return ReviewInput.model_validate(data)


def output(**changes):
    proposal = dict(disposition="create", target_definition_id=None, description="Invoice status lookup",
        conditions=["Invoice or customer identified"], required_slots=["invoice_id"], exclusions=[],
        capability_ids=["accounting.invoice.read"], point_ids=["p"], source_ids=["final", "result"],
        examples=["Has this invoice been paid?"])
    proposal.update(changes)
    return dict(contract_version=3, proposals=[proposal],assessments=[dict(point_id="p",
        request_resolution=dict(judgment="resolved",evidence_source_ids=["final","result","answer"],explanation="Result and answer satisfy invoice request"),
        usefulness=dict(judgment="necessary",evidence_source_ids=["final","result"],explanation="Lookup supplies requested status"),
        tool_selection=dict(judgment="correct",evidence_source_ids=["final","result"],explanation="Matching lookup"),
        context_selection=dict(judgment="not_required",evidence_source_ids=["final"],explanation="Explicit invoice identifier"),
        result_quality=dict(judgment="correct",evidence_source_ids=["final","result"],explanation="Result matches requested invoice"),
        user_satisfaction=dict(judgment="unknown",evidence_source_ids=[],explanation="No captured feedback"),
        tool_satisfaction=dict(judgment="unknown",evidence_source_ids=[],explanation="No captured tool feedback"),
        context_satisfaction=dict(judgment="unknown",evidence_source_ids=[],explanation="No captured context feedback"),
        result_satisfaction=dict(judgment="unknown",evidence_source_ids=[],explanation="No captured result feedback"),failure_stage="none")])


def runner(execute):
    return OpenAIMemoryReviewer(credentials=Credentials(), user_id="u", workspace_id="w", executor=execute)


def test_memory_and_decisions_reuse_exact_model_executor_with_separate_prompt_and_schema():
    calls = []
    def execute(**kwargs):
        calls.append(kwargs)
        if kwargs["agent_name"] == "Vault Memory Review":
            return {"contractVersion": 2, "summary": "Memory complete", "candidates": []}
        return output()
    shared = runner(execute)
    result = review_session(memory_review=lambda: shared.review("Completed session"),
        decision_review=lambda: DecisionReviewer(model_runner=shared).review(snapshot()))
    assert result.memory.state == result.decisions.state == "completed"
    assert result.memory.result.model == result.decisions.result.model == "configured-model"
    assert [c["agent_name"] for c in calls] == ["Vault Memory Review", "Vault Decisions Review"]
    assert calls[0]["instructions"] != calls[1]["instructions"]
    assert calls[1]["output_type"] is ReviewOutput
    from app.vault_runtime.decision_learning.prompt_examples import FORMAT_EXAMPLES
    assert FORMAT_EXAMPLES in calls[1]["instructions"]
    assert all(c["api_key"] == "synthetic-key" and c["max_turns"] == 4 for c in calls)
    assert result.decisions.result.output.proposals[0].disposition == "create"


@pytest.mark.parametrize("changes", [dict(source_ids=["fabricated"]), dict(point_ids=["missing"]),
    dict(capability_ids=["invented"]), dict(target_definition_id="missing"),
    dict(disposition="revise"), dict(source_ids=["final", "final"]), dict(extra="bad")])
def test_fabricated_references_targets_and_extra_fields_fail(changes):
    with pytest.raises(DecisionReviewError):
        DecisionReviewer(model_runner=runner(lambda **_: output(**changes))).review(snapshot())


@pytest.mark.parametrize("field,value", [("execution", "effect_unknown"), ("execution", "denied"),
    ("tool_report", "error"), ("tool_report", "truncated"),
    ("request_outcome", "corrected")])
def test_non_successful_outcomes_cannot_teach_successful_rules(field, value):
    data = snapshot().model_dump()
    data["observations"][0][field] = value
    with pytest.raises(DecisionReviewError):
        DecisionReviewer(model_runner=runner(lambda **_: output())).review(ReviewInput.model_validate(data))
    safe = output(disposition="insufficient_evidence",capability_ids=[])
    safe["assessments"][0]["request_resolution"] = dict(judgment="unknown",evidence_source_ids=[],explanation="Outcome unqualified")
    safe["assessments"][0]["usefulness"] = dict(judgment="unknown",evidence_source_ids=[],explanation="Outcome unqualified")
    reviewed = DecisionReviewer(model_runner=runner(lambda **_: safe)).review(ReviewInput.model_validate(data))
    assert reviewed.output.proposals[0].disposition == "insufficient_evidence"


@pytest.mark.parametrize("coverage", ["incomplete"])
def test_incomplete_evidence_never_calls_model(coverage):
    def forbidden(**_):
        pytest.fail("No model call with unqualified evidence")
    with pytest.raises(DecisionReviewError):
        DecisionReviewer(model_runner=runner(forbidden)).review(snapshot(coverage=coverage))


def test_unknown_capture_is_analysis_only_never_successful_learning():
    with pytest.raises(DecisionReviewError,match="analysis-only"):
        DecisionReviewer(model_runner=runner(lambda **_:output())).review(snapshot(coverage="unknown"))
    reviewed = DecisionReviewer(model_runner=runner(lambda **_:output(disposition="insufficient_evidence"))).review(snapshot(coverage="unknown"))
    assert reviewed.output.proposals[0].disposition=="insufficient_evidence"


def test_drafts_overflow_wrong_contract_and_provider_errors_fail_without_truncation():
    data = snapshot().model_dump()
    data["sources"][0]["kind"] = "draft"
    with pytest.raises(ValueError):
        ReviewInput.model_validate(data)
    huge = snapshot(sources=[dict(source_id=f"s{i}", kind="user_final", text="x" * 20000) for i in range(6)], observations=[])
    with pytest.raises(DecisionReviewError, match="partitioning"):
        DecisionReviewer(model_runner=runner(lambda **_: pytest.fail("Overflow invoked provider"))).review(huge)
    for bad in ("not json", {"contract_version": True, "proposals": []},
                {"contract_version": 2, "proposals": []},
                output(examples=["x" * 100001]),
                {"contract_version": 1, "proposals": output()["proposals"] * 33}):
        with pytest.raises(DecisionReviewError):
            DecisionReviewer(model_runner=runner(lambda **_: bad)).review(snapshot())
    def failed(**_):
        raise RuntimeError("secret provider detail")
    with pytest.raises(DecisionReviewError) as exc:
        DecisionReviewer(model_runner=runner(failed)).review(snapshot())
    assert "secret" not in str(exc.value)


def test_independent_failures_and_disabled_branch_do_not_undo_other_result():
    calls = []
    def fail():
        calls.append("failed")
        raise RuntimeError("secret")
    def succeed():
        calls.append("success")
        return "published-memory"
    result = review_session(memory_review=succeed, decision_review=fail)
    assert result.memory.result == "published-memory" and result.decisions.state == "failed"
    result = review_session(memory_review=fail, decision_review=succeed)
    assert result.memory.state == "failed" and result.decisions.state == "completed"
    assert calls == ["success", "failed", "failed", "success"]
    assert review_session(memory_review=succeed, decision_review=None).decisions.state == "disabled"


def test_gemini_reuses_same_request_code_with_different_prompt_schema(monkeypatch):
    captured = []
    class GeminiCredentials(Credentials):
        def selected_provider(self, **scope):
            return "gemini"
        def background_access(self, **scope):
            return SimpleNamespace(value="synthetic-key", auth_method="gemini_oauth"), "configured-model"
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            import json
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(output())}]}}]}
    def post(*args, **kwargs):
        captured.append(kwargs)
        return Response()
    monkeypatch.setattr("app.vault_runtime.memory.openai_reviewer.httpx.post", post)
    shared = OpenAIMemoryReviewer(credentials=GeminiCredentials(), user_id="u", workspace_id="w")
    result = DecisionReviewer(model_runner=shared).review(snapshot())
    assert result.model == "configured-model"
    from app.vault_runtime.decision_learning.reviewer import INSTRUCTIONS
    assert captured[0]["json"]["systemInstruction"]["parts"][0]["text"] == INSTRUCTIONS
    assert captured[0]["json"]["generationConfig"]["responseJsonSchema"] == ReviewOutput.model_json_schema(by_alias=True)
    assert captured[0]["headers"]["Authorization"] == "Bearer synthetic-key"
