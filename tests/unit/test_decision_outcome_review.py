import pytest

from app.vault_runtime.decision_learning.reviewer import DecisionReviewer,DecisionReviewError,ReviewInput,INSTRUCTIONS,REVIEW_GOAL
from tests.unit.test_decision_learning_reviewer import snapshot,output,runner


def reviewed(data,source=None):
    return DecisionReviewer(model_runner=runner(lambda **_:data)).review(source or snapshot())


@pytest.mark.parametrize("judgment",["unnecessary","harmful","unknown"])
def test_correct_tool_and_result_do_not_teach_a_throwaway_or_unqualified_call(judgment):
    data = output()
    data["assessments"][0]["usefulness"]["judgment"] = judgment
    with pytest.raises(DecisionReviewError,match="handling"):
        reviewed(data)
    data["proposals"][0]["disposition"] = "no_change"
    assert reviewed(data).output.assessments[0].usefulness.judgment == judgment


def test_model_resolution_is_distinct_from_source_transport_state():
    source = snapshot().model_dump(mode="json")
    source["observations"][0]["request_outcome"] = "unknown"
    result = reviewed(output(),ReviewInput.model_validate(source))
    assert result.output.assessments[0].request_resolution.judgment == "resolved"
    data = output()
    data["assessments"][0]["request_resolution"]["judgment"] = "unknown"
    with pytest.raises(DecisionReviewError):
        reviewed(data,ReviewInput.model_validate(source))


@pytest.mark.parametrize("evidence",[["final","result"],["final","answer"],["result","answer"],["unrelated"]])
def test_resolution_requires_exact_final_request_result_and_answer(evidence):
    # Incomplete citations never yield "resolved": the claim becomes unknown and cannot teach.
    data = output()
    data["assessments"][0]["request_resolution"]["evidence_source_ids"] = evidence
    result = reviewed(data).output
    assert result.assessments[0].request_resolution.judgment == "unknown"
    assert result.proposals[0].disposition == "insufficient_evidence"


@pytest.mark.parametrize("dimension,judgment,stage",[
    ("tool_selection","incorrect","tool_selection"),
    ("context_selection","incorrect","context_selection"),
    ("result_quality","incorrect","answer_generation"),
    ("context_selection","unknown","unknown"),
    ("result_quality","mixed","answer_generation"),
])
def test_tool_success_cannot_override_bad_or_unknown_other_dimensions(dimension,judgment,stage):
    data = output()
    data["assessments"][0][dimension]["judgment"] = judgment
    data["assessments"][0]["failure_stage"] = stage
    with pytest.raises(DecisionReviewError,match="handling"):
        reviewed(data)
    data["proposals"][0]["disposition"] = "insufficient_evidence"
    result = reviewed(data)
    assert getattr(result.output.assessments[0],dimension).judgment == judgment


@pytest.mark.parametrize("judgment",["dissatisfied","mixed"])
def test_user_negative_feedback_retained_but_cannot_teach_success(judgment):
    source = snapshot().model_dump(mode="json")
    source["sources"].append(dict(source_id="feedback",kind="user_correction",text="Right tool, wrong customer"))
    source["observations"][0]["feedback_source_ids"] = ["feedback"]
    data = output()
    data["assessments"][0]["user_satisfaction"] = dict(judgment=judgment,evidence_source_ids=["feedback"],explanation="User corrected customer context")
    data["assessments"][0]["failure_stage"] = "context_selection"
    with pytest.raises(DecisionReviewError):
        reviewed(data,ReviewInput.model_validate(source))
    data["proposals"][0]["disposition"] = "insufficient_evidence"
    assert reviewed(data,ReviewInput.model_validate(source)).output.assessments[0].user_satisfaction.judgment == judgment


@pytest.mark.parametrize("evidence",[[]])
def test_no_feedback_no_inferred_satisfaction(evidence):
    data = output()
    data["assessments"][0]["user_satisfaction"]["judgment"] = "satisfied"
    data["assessments"][0]["user_satisfaction"]["evidence_source_ids"] = evidence
    with pytest.raises(DecisionReviewError,match="Satisfaction"):
        reviewed(data)


@pytest.mark.parametrize("evidence",[["result"],["invented"]])
def test_satisfaction_citing_non_feedback_is_downgraded_not_inferred(evidence):
    data = output()
    data["assessments"][0]["user_satisfaction"].update(judgment="satisfied",evidence_source_ids=evidence)
    satisfaction = reviewed(data).output.assessments[0].user_satisfaction
    assert (satisfaction.judgment, satisfaction.evidence_source_ids) == ("unknown", ())


def test_context_answer_feedback_are_point_linked_and_unknown_stays_unknown():
    source = snapshot().model_dump(mode="json")
    source["sources"].extend([dict(source_id="memory",kind="memory_context",text="Unrelated customer context"),
        dict(source_id="other_feedback",kind="user_feedback",text="Thanks")])
    source["observations"][0]["context_source_ids"] = ["memory"]
    source["observations"][0]["answer_source_id"] = "answer"
    source = ReviewInput.model_validate(source)
    data = output()
    data["assessments"][0]["context_selection"]["evidence_source_ids"] = ["memory","final"]
    assert reviewed(data,source).output.assessments[0].user_satisfaction.judgment == "unknown"
    # Real session sources linked to a different point never support this point's judgments.
    data["assessments"][0]["user_satisfaction"] = dict(judgment="satisfied",evidence_source_ids=["other_feedback"],explanation="Unlinked thanks")
    assert reviewed(data,source).output.assessments[0].user_satisfaction.judgment == "unknown"
    data = output()
    data["assessments"][0]["context_selection"]["evidence_source_ids"] = ["other_feedback"]
    result = reviewed(data,source).output
    context = result.assessments[0].context_selection
    assert (context.judgment, context.evidence_source_ids) == ("unknown", ())
    assert result.proposals[0].disposition == "insufficient_evidence"  # no longer qualified to teach
    data["assessments"][0]["context_selection"]["evidence_source_ids"] = ["fabricated"]
    assert reviewed(data,source).output.assessments[0].context_selection.judgment == "unknown"
    data["assessments"][0]["context_selection"].update(judgment="correct",evidence_source_ids=[])
    with pytest.raises(DecisionReviewError,match="point-linked"):
        reviewed(data,source)  # A judgment that cites nothing is still rejected.


@pytest.mark.parametrize("change",["missing","duplicate","foreign","contradictory"])
def test_all_points_assessed_and_negative_not_failure_free(change):
    data = output(disposition="no_change")
    if change=="missing":
        data["assessments"] = []
    elif change=="duplicate":
        data["assessments"] *= 2
    elif change=="foreign":
        data["assessments"][0]["point_id"] = "unrelated"
    else:
        data["assessments"][0]["context_selection"]["judgment"] = "incorrect"
    with pytest.raises(DecisionReviewError):
        reviewed(data)


def test_explicit_review_goal_is_in_actual_shared_model_prompt():
    calls = []
    def execute(**kwargs):
        calls.append(kwargs)
        return output()
    DecisionReviewer(model_runner=runner(execute)).review(snapshot())
    assert calls[0]["instructions"] == INSTRUCTIONS
    assert REVIEW_GOAL in INSTRUCTIONS and "GOAL:" in INSTRUCTIONS
    assert all(name in INSTRUCTIONS for name in ("tool_selection","context_selection","result_quality","user_satisfaction"))


def test_satisfied_tool_choice_does_not_mask_dissatisfied_context_or_result():
    source = snapshot().model_dump(mode="json")
    source["sources"].append(dict(source_id="feedback",kind="user_feedback",text="Correct tool, but wrong customer, so the result is wrong"))
    source["observations"][0]["feedback_source_ids"] = ["feedback"]
    data = output(disposition="insufficient_evidence")
    assessed = data["assessments"][0]
    assessed["tool_satisfaction"] = dict(judgment="satisfied",evidence_source_ids=["feedback"],explanation="Explicit correct-tool feedback")
    for dimension in ("context_satisfaction","result_satisfaction"):
        assessed[dimension] = dict(judgment="dissatisfied",evidence_source_ids=["feedback"],explanation="Explicit wrong-customer/result feedback")
    assessed["failure_stage"] = "context_selection"
    result = reviewed(data,ReviewInput.model_validate(source)).output.assessments[0]
    assert result.tool_satisfaction.judgment == "satisfied"
    assert result.context_satisfaction.judgment == result.result_satisfaction.judgment == "dissatisfied"
    data["proposals"][0]["disposition"] = "create"
    with pytest.raises(DecisionReviewError):
        reviewed(data,ReviewInput.model_validate(source))


def test_normalizer_only_removes_misattributed_claims_and_is_idempotent():
    from app.vault_runtime.decision_learning.reviewer import ReviewOutput, normalize_model_output
    source = snapshot().model_dump(mode="json")
    source["sources"].append(dict(source_id="later",kind="user_final",text="A different later request"))
    source = ReviewInput.model_validate(source)
    data = output()
    data["assessments"][0]["tool_selection"]["evidence_source_ids"] = ["final","later"]
    normalized, corrections = normalize_model_output(ReviewOutput.model_validate(data), source)
    tool = normalized.assessments[0].tool_selection
    assert corrections == 1 and tool.evidence_source_ids == ("final",) and tool.judgment == "correct"
    # The point stayed qualified (judgment kept), but a changed point never keeps teaching unverified.
    assert normalized.proposals[0].disposition == "insufficient_evidence"
    assert normalize_model_output(normalized, source) == (normalized, 0)


def test_useful_without_request_and_result_is_downgraded_and_stops_teaching():
    data = output()
    data["assessments"][0]["usefulness"]["evidence_source_ids"] = ["final"]
    result = reviewed(data).output
    assert result.assessments[0].usefulness.judgment == "unknown"
    assert result.proposals[0].disposition == "insufficient_evidence"


def test_claims_on_uncaptured_links_become_unknown_but_recorded_failures_stay_rejected():
    source = snapshot().model_dump(mode="json")
    source["coverage"] = "unknown"  # what Voice capture reports today
    source["observations"][0]["final_source_id"] = None  # request-to-tool link never captured
    data = output(disposition="no_change")
    result = reviewed(data,ReviewInput.model_validate(source)).output
    assert result.assessments[0].usefulness.judgment == "unknown"
    assert result.assessments[0].request_resolution.judgment == "unknown"
    source = snapshot().model_dump(mode="json")
    source["observations"][0]["tool_report"] = "error"  # recorded failure, not missing evidence
    with pytest.raises(DecisionReviewError):
        reviewed(output(disposition="no_change"),ReviewInput.model_validate(source))
