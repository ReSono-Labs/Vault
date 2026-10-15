import json

import pytest

from app.vault_runtime.decision_learning.prompt_examples import (
    FORMAT_EXAMPLES, PROPOSAL_EXAMPLES, REVIEW_EXAMPLE,
)
from app.vault_runtime.decision_learning.reviewer import (
    INSTRUCTIONS, ReviewInput, ReviewOutput, _validate_output,
)
from app.vault_runtime.decision_learning.reconciliation import PROMPT, ReconciliationOutput
from tests.unit.test_decision_learning_reviewer import snapshot


@pytest.mark.parametrize("kind", PROPOSAL_EXAMPLES)
def test_prompt_record_examples_match_schema_and_reference_validation(kind):
    data = snapshot().model_dump(mode="json")
    data["sources"] = [
        dict(source_id="demo-request",kind="user_final",text="Find the contact matching the supplied query"),
        dict(source_id="demo-result",kind="tool_result",text="One matching authorized contact found"),
        dict(source_id="demo-answer",kind="assistant_final",text="Here is the matching contact"),
    ]
    data["observations"][0].update(point_id="demo-point",final_source_id="demo-request",
        result_source_id="demo-result",answer_source_id="demo-answer",capability_id="demo.contacts.read")
    data["capabilities"]=[dict(capability_id="demo.contacts.read",description="Contact lookup",effect="read")]
    data["existing_decisions"]=[dict(definition_id="demo-existing-rule",version=1,description="Contact lookup")]
    result=ReviewOutput.model_validate({**REVIEW_EXAMPLE,"proposals":[PROPOSAL_EXAMPLES[kind]]})
    _validate_output(result,ReviewInput.model_validate(data))
    ReconciliationOutput.model_validate({**result.model_dump(),"rationale":"Synthetic formatting explanation"})


def test_both_real_model_prompts_include_same_examples_and_non_evidence_warning():
    assert FORMAT_EXAMPLES in INSTRUCTIONS and FORMAT_EXAMPLES in PROMPT
    assert json.dumps(REVIEW_EXAMPLE,ensure_ascii=False) in INSTRUCTIONS
    assert "NEVER session evidence" in FORMAT_EXAMPLES
    assert "Preserve the ACTUAL analysis" in FORMAT_EXAMPLES
    assert '"target_definition_id": null' in FORMAT_EXAMPLES
