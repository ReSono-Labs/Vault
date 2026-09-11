from __future__ import annotations

import os
from threading import Barrier
from time import monotonic, sleep

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.background_agent.contracts import BackgroundRunRequest, BackgroundRunState
from app.vault_runtime.background_agent.repository import (
    BackgroundRunAuthorizationError,
    BackgroundRunConflictError,
    BackgroundRunRepository,
)
from app.vault_runtime.background_agent.service import BackgroundAgentService
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService
from app.vault_runtime.tools.catalog import ToolCatalog


@pytest.fixture()
def background_context():
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    identities = LocalIdentityRepository(database_url=database_url)
    identity = LocalIdentityService(
        repository=identities, setup_credential_hash=hash_token("setup")
    )
    identity.ensure_schema()
    owner = identity.bootstrap_owner(
        setup_credential="setup", username="owner", password="owner-password",
        display_name="Owner", experience_style="strict",
    )
    identity.create_user(
        actor=owner.principal, username="second", password="second-password",
        display_name="Second", experience_style="funny",
    )
    second = identity.login(username="second", password="second-password")
    runs = BackgroundRunRepository(database_url=database_url)
    runs.ensure_schema()
    yield database_url, identity, owner, second, runs
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")


def _request(run_id="run-1"):
    return BackgroundRunRequest(
        run_id=run_id, objective="Research the scoped question.", instruction_profile="default",
        success_criteria=("Return evidence.",), result_schema={"type": "object"},
        original_request="Research this.", verification_method="Check cited evidence.",
        completion_conditions=("Evidence is returned.",), requested_tool_names=("memory_lookup",),
    )


def _complete_output():
    return {
        "status": "complete", "summary": "done", "artifact_references": [],
        "requirement_outcomes": [{
            "requirement": "Return evidence.", "status": "completed",
            "evidence": "Evidence checked.",
        }],
        "unresolved_issues": [], "verification_summary": "verified",
        "phase_evidence": [{"phase": "execution", "summary": "Evidence returned."}],
    }


def test_background_run_legal_lifecycle_and_events(background_context) -> None:
    url, _identity, owner, _second, runs = background_context
    kwargs = {
        "user_id": owner.principal.user_id, "workspace_id": owner.principal.workspace_id,
        "local_session_id": owner.principal.session_id, "run_id": "run-1",
    }
    accepted = runs.create(
        user_id=kwargs["user_id"], workspace_id=kwargs["workspace_id"],
        local_session_id=kwargs["local_session_id"], request=_request(),
    )
    assert accepted.state is BackgroundRunState.ACCEPTED
    runs.transition(**kwargs, target=BackgroundRunState.QUEUED, event_type="queued")
    runs.transition(**kwargs, target=BackgroundRunState.RUNNING, event_type="started")
    runs.record_activity(**kwargs, event_type="model_turns", detail={"count": 2})
    runs.record_activity(**kwargs, event_type="tool_completed", detail={"call": 1, "name": "memory_lookup"})
    completed = runs.transition(
        **kwargs, target=BackgroundRunState.COMPLETED, event_type="completed",
        output={"summary": "done"},
    )
    assert completed.state is BackgroundRunState.COMPLETED
    assert completed.output == {"summary": "done"}
    assert (completed.model_turns, completed.tool_calls) == (2, 1)
    with psycopg.connect(url) as connection:
        events = connection.execute(
            "SELECT event_index,event_type FROM vault_private.vault_background_run_events ORDER BY event_index"
        ).fetchall()
    assert [row[0] for row in events] == list(range(len(events)))


def test_illegal_transition_cross_user_probe_and_revocation_denied(background_context) -> None:
    _url, identity, owner, second, runs = background_context
    run = runs.create(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        local_session_id=owner.principal.session_id, request=_request(),
    )
    with pytest.raises(BackgroundRunConflictError):
        runs.transition(
            user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
            local_session_id=owner.principal.session_id, run_id=run.request.run_id,
            target=BackgroundRunState.COMPLETED, event_type="completed", output={"x": 1},
        )
    with pytest.raises(BackgroundRunAuthorizationError):
        runs.get(
            user_id=second.principal.user_id, workspace_id=second.principal.workspace_id,
            local_session_id=second.principal.session_id, run_id=run.request.run_id,
        )
    identity.add_member(
        principal=owner.principal, workspace_id=owner.principal.workspace_id, username="second"
    )
    identity.switch_workspace(principal=second.principal, workspace_id=owner.principal.workspace_id)
    second_shared = identity.authenticate(session_token=second.session_token)
    shared_run = runs.create(
        user_id=second_shared.user_id, workspace_id=second_shared.workspace_id,
        local_session_id=second_shared.session_id, request=_request("run-second"),
    )
    identity.revoke_member(
        principal=owner.principal, workspace_id=owner.principal.workspace_id, username="second"
    )
    with pytest.raises(Exception):
        runs.get(
            user_id=second_shared.user_id, workspace_id=second_shared.workspace_id,
            local_session_id=second_shared.session_id, run_id=shared_run.request.run_id,
        )


def test_cancellation_request_is_durable_and_terminal_run_is_stable(background_context) -> None:
    _url, _identity, owner, _second, runs = background_context
    kwargs = {
        "user_id": owner.principal.user_id, "workspace_id": owner.principal.workspace_id,
        "local_session_id": owner.principal.session_id, "run_id": "run-1",
    }
    runs.create(
        user_id=kwargs["user_id"], workspace_id=kwargs["workspace_id"],
        local_session_id=kwargs["local_session_id"], request=_request(),
    )
    requested = runs.request_cancellation(**kwargs)
    assert requested.cancellation_requested
    cancelled = runs.transition(
        **kwargs, target=BackgroundRunState.CANCELLED, event_type="cancelled"
    )
    assert cancelled.completed_at is not None
    assert runs.request_cancellation(**kwargs).state is BackgroundRunState.CANCELLED


class _Executor:
    def __init__(self, output=None, error=None):
        self.output = output if output is not None else _complete_output()
        self.error = error

    def execute(self, request, *, tools, context, progress):
        assert context.execution_id == request.run_id
        assert tools.calls_used == 0
        progress.model_turn()
        if self.error:
            raise self.error
        return self.output


def test_fixed_background_service_executes_queued_run(background_context) -> None:
    url, _identity, owner, _second, runs = background_context
    request = BackgroundRunRequest(
        run_id="service-run", objective="Research the scoped question.",
        instruction_profile="default", success_criteria=("Return evidence.",),
        result_schema={
            "type": "object", "properties": {"summary": {"type": "string"}},
            "required": ["summary"], "additionalProperties": False,
        }, original_request="Research this.", verification_method="Check evidence.",
        completion_conditions=("Evidence is returned.",),
    )
    service = BackgroundAgentService(
        repository=runs, catalog=ToolCatalog(authorizer=lambda _definition, _context: True),
        executor=_Executor(),
    )
    queued = service.submit(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        local_session_id=owner.principal.session_id, request=request,
    )
    assert queued.state is BackgroundRunState.QUEUED
    completed = service.execute_queued(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        local_session_id=owner.principal.session_id, run_id=request.run_id,
    )
    assert completed.state is BackgroundRunState.COMPLETED
    assert completed.output["status"] == "complete" and completed.model_turns == 1
    with psycopg.connect(url) as connection:
        evidence = connection.execute(
            "SELECT detail_json FROM vault_private.vault_background_run_events "
            "WHERE run_id=%s AND event_type='agent_evidence'", (request.run_id,),
        ).fetchone()
    assert evidence and evidence[0] == {
        "phase": "execution", "summary": "Evidence returned.",
    }


def test_invalid_background_output_fails_and_prestart_cancel_is_honoured(background_context) -> None:
    _url, _identity, owner, _second, runs = background_context
    request = BackgroundRunRequest(
        run_id="invalid-output", objective="Research.", instruction_profile="default",
        success_criteria=("Return summary.",),
        result_schema={
            "type": "object", "properties": {"summary": {"type": "string"}},
            "required": ["summary"], "additionalProperties": False,
        }, original_request="Research.", verification_method="Check schema.",
        completion_conditions=("Summary exists.",),
    )
    service = BackgroundAgentService(
        repository=runs, catalog=ToolCatalog(authorizer=lambda _definition, _context: True),
        executor=_Executor(output={"wrong": True}),
    )
    service.submit(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        local_session_id=owner.principal.session_id, request=request,
    )
    failed = service.execute_queued(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        local_session_id=owner.principal.session_id, run_id=request.run_id,
    )
    assert failed.state is BackgroundRunState.FAILED

    cancel_request = _request("cancel-before-start")
    service.submit(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        local_session_id=owner.principal.session_id, request=cancel_request,
    )
    runs.request_cancellation(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        local_session_id=owner.principal.session_id, run_id=cancel_request.run_id,
    )
    cancelled = service.execute_queued(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        local_session_id=owner.principal.session_id, run_id=cancel_request.run_id,
    )
    assert cancelled.state is BackgroundRunState.CANCELLED


def test_background_worker_consumes_queued_run(background_context) -> None:
    _url, _identity, owner, _second, runs = background_context
    request = BackgroundRunRequest(
        run_id="worker-run", objective="Run in background.", instruction_profile="default",
        success_criteria=("Return summary.",),
        result_schema={
            "type": "object", "properties": {"summary": {"type": "string"}},
            "required": ["summary"], "additionalProperties": False,
        }, original_request="Run in background.", verification_method="Check schema.",
        completion_conditions=("Summary exists.",),
    )
    service = BackgroundAgentService(
        repository=runs, catalog=ToolCatalog(authorizer=lambda _definition, _context: True),
        executor=_Executor(),
    )
    service.start()
    try:
        service.submit(
            user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
            local_session_id=owner.principal.session_id, request=request,
        )
        deadline = monotonic() + 5
        while monotonic() < deadline:
            current = runs.get(
                user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
                local_session_id=owner.principal.session_id, run_id=request.run_id,
            )
            if current.state in {BackgroundRunState.COMPLETED, BackgroundRunState.FAILED}:
                break
            sleep(0.02)
        assert current.state is BackgroundRunState.COMPLETED
    finally:
        service.stop()


def test_four_users_run_concurrently_and_one_failure_is_contained(background_context) -> None:
    _url, identity, owner, second, runs = background_context
    principals = [owner.principal, second.principal]
    for number in (3, 4):
        identity.create_user(
            actor=owner.principal, username=f"user{number}", password=f"password-{number:02d}",
            display_name=f"User {number}", experience_style="strict",
        )
        principals.append(identity.login(
            username=f"user{number}", password=f"password-{number:02d}",
        ).principal)

    barrier = Barrier(4, timeout=5)

    class ConcurrentExecutor:
        def execute(self, request, *, tools, context, progress):
            barrier.wait()
            progress.model_turn()
            if request.run_id == "run-2":
                raise RuntimeError("contained_failure")
            return _complete_output()

    service = BackgroundAgentService(
        repository=runs, catalog=ToolCatalog(authorizer=lambda _definition, _context: True),
        executor=ConcurrentExecutor(), worker_count=4,
    )
    service.start()
    try:
        for number, principal in enumerate(principals, start=1):
            service.submit(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                local_session_id=principal.session_id, request=_request(f"run-{number}"),
            )
        deadline = monotonic() + 8
        states = {}
        while monotonic() < deadline:
            states = {
                number: runs.get(
                    user_id=principal.user_id, workspace_id=principal.workspace_id,
                    local_session_id=principal.session_id, run_id=f"run-{number}",
                ).state
                for number, principal in enumerate(principals, start=1)
            }
            if all(state in {BackgroundRunState.COMPLETED, BackgroundRunState.FAILED} for state in states.values()):
                break
            sleep(0.02)
        assert states == {
            1: BackgroundRunState.COMPLETED, 2: BackgroundRunState.FAILED,
            3: BackgroundRunState.COMPLETED, 4: BackgroundRunState.COMPLETED,
        }
        assert identity.authenticate(session_token=owner.session_token).user_id == owner.principal.user_id
        assert identity.authenticate(session_token=second.session_token).user_id == second.principal.user_id
        assert identity.login(username="user3", password="password-03").principal.user_id == principals[2].user_id
        assert identity.login(username="user4", password="password-04").principal.user_id == principals[3].user_id
    finally:
        service.stop()
