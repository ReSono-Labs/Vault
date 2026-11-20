"""Shared test helpers moved out of test modules (TST-01)."""

from types import SimpleNamespace

from app.vault_runtime.decision_learning.reviewer import ReviewInput
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
