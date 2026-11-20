import pytest

from app.vault_runtime.background_agent.contracts import BackgroundRunRequest, RunLimits


def _request(**changes):
    values = {
        "run_id": "run-1", "objective": "Research the scoped question.",
        "instruction_profile": "default", "success_criteria": ("Return evidence.",),
        "result_schema": {"type": "object"}, "original_request": "Research this.",
        "verification_method": "Check cited evidence.",
        "completion_conditions": ("Evidence is returned.",),
    }
    values.update(changes)
    return BackgroundRunRequest(**values)


def test_background_request_is_fixed_bounded_work_not_an_agent_identity() -> None:
    request = _request(requested_tool_names=("memory_lookup",))
    assert request.run_id == "run-1" and request.requested_tool_names == ("memory_lookup",)
    assert "agent_name" not in request.payload() and "agent_kind" not in request.payload()


def test_background_limits_and_required_completion_contract() -> None:
    with pytest.raises(ValueError):
        RunLimits(max_tool_calls=501)
    with pytest.raises(ValueError):
        _request(completion_conditions=())
