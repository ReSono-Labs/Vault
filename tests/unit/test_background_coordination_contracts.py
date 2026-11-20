from dataclasses import FrozenInstanceError
import importlib
import importlib.util

import pytest

from app.vault_runtime.background_agent.contracts import BackgroundRunRequest


def contracts():
    name = "app.vault_runtime.background_agent.coordination_contracts"
    assert importlib.util.find_spec(name) is not None, "Scoped coordination contracts are missing"
    return importlib.import_module(name)


def request(run_id="proof-run"):
    return BackgroundRunRequest(
        run_id=run_id, objective="Prepare a brief", instruction_profile="default",
        success_criteria=("Brief is checked",), result_schema={"type": "object"},
        original_request="Prepare a brief", verification_method="Check evidence",
        completion_conditions=("Brief is checked",),
    )


@pytest.mark.parametrize("session,grant,valid", [(None, None, False), ("session", "grant", False),
                                               ("session", None, True), (None, "grant", True)])
def test_work_request_has_exactly_one_authority_path(session, grant, valid):
    module = contracts()
    if valid:
        value = module.WorkRequest(request(), grant, session, {})
        assert value.payload()["local_session_id"] == session
        assert value.payload()["grant_id"] == grant
    else:
        with pytest.raises(ValueError, match="authority"):
            module.WorkRequest(request(), grant, session, {})


def test_scope_identity_is_immutable_and_not_an_implicit_worker():
    module = contracts()
    owner = module.OwnerScope("user", "workspace")
    with pytest.raises(FrozenInstanceError):
        owner.user_id = "another"
    scope = module.WorkScope("user", "workspace", "work", 1, None, None, None)
    assert scope.worker_id is None
    with pytest.raises(ValueError):
        module.WorkScope("user", "workspace", "work", 1, "worker", None, None)
    with pytest.raises(ValueError):
        module.OwnerScope(" user", "workspace")


def test_worker_scope_does_not_accept_duplicate_tools_or_empty_purpose():
    module = contracts()
    with pytest.raises(ValueError):
        module.WorkerSpec("research", "", "Read approved sources", ("read",), {})
    with pytest.raises(ValueError):
        module.WorkerSpec("research", "Research", "Read approved sources", ("read", "read"), {})


def test_waiting_approval_requires_an_action_and_terminal_work_cannot_resume():
    module = contracts()
    with pytest.raises(ValueError):
        module.ExecutionOutcome(module.WorkState.WAITING_APPROVAL)
    assert module.WorkState.READY not in module.WORK_TRANSITIONS[module.WorkState.COMPLETED]
    assert module.WorkState.READY in module.WORK_TRANSITIONS[module.WorkState.WAITING_APPROVAL]
