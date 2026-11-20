"""Phase 5 characterization (cleanup Phase 5, C1-C7).

These run on the real production composition before and after the old background engine is
retired; the recorded results must stay the same. Rows covered by existing tests:

- C2 one-time follow-up fires on its tick, C3 daily check-in:
  tests/integration/test_coordinator_wake_postgres.py::test_coordinator_wakes_in_its_chat_and_follows_through
  (plus the tick interval recorded in test_c1_* below).
- C4 stalled reconcile does not reclaim a live run:
  tests/integration/test_background_jobs_postgres.py::test_slow_run_on_this_live_worker_is_not_reclaimed
- C5 A2A unit contract: tests/unit/test_agent2agent_inbound.py (the JSON shapes are recorded here).
- C6 cancel from the Background work page:
  tests/integration/test_background_api_postgres.py::test_settings_stop_aborts_only_selected_run and
  ::test_work_activity_projection_task_link_cancel_and_no_private_leak
"""
from __future__ import annotations

import json
import os
import re
from types import SimpleNamespace as NS

import psycopg
import pytest
from agents import Runner

from app.vault_runtime.background_agent.contracts import (
    AutonomyProfile,
    BackgroundRunRequest,
    ExecutionRecipe,
)
from app.vault_runtime.background_agent.coordination_contracts import OwnerScope, WorkRequest
from app.vault_runtime.background_agent.output_contract import BackgroundAgentOutput, background_output_schema
from app.vault_runtime.composition import build_local_app
from tests.support.background_mounted_runtime import (
    _api, _boot_config, _onboard_owner, _reset_schemas, _wait_until,
)

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _output(objective: str) -> BackgroundAgentOutput:
    if objective.startswith("Needs attention"):
        return BackgroundAgentOutput(status="needs_attention", summary="Could not finish: source missing.",
                                     verification_summary="Checked the source list.",
                                     unresolved_issues=["source missing"])
    return BackgroundAgentOutput(status="complete", summary=f"Done: {objective}",
                                 verification_summary="Checked the answer.")


@pytest.fixture
def booted(tmp_path, monkeypatch):
    url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Exact isolated database required")
    _reset_schemas(url)
    monkeypatch.setattr("app.vault_runtime.memory.service.MemoryService.ensure_vectors", lambda *a, **k: (0, 0))
    monkeypatch.setattr("app.vault_runtime.agent_network.service.A2AService.start", lambda *_: None)
    monkeypatch.setattr("app.vault_runtime.agent_network.inbound.A2AInboundHttpServer.start", lambda *_: None)
    monkeypatch.setattr("app.vault_runtime.extensions.mcp_runtime.McpRuntimeSupervisor.restore_on_boot", lambda *_: None)
    model_calls: list[str] = []

    async def fake_run(agent, *args, **kwargs):
        # One seam for every Background executor: the Agents SDK runner. No provider traffic.
        raw = kwargs.get("input", args[0] if args else None)
        objective = json.loads(raw)["objective"]
        model_calls.append(objective)
        if objective.startswith("Fails"):
            raise RuntimeError("Upstream service refused the request.")
        return NS(final_output=_output(objective), interruptions=[])

    monkeypatch.setattr(Runner, "run", staticmethod(fake_run))
    app = build_local_app(_boot_config(tmp_path, url))
    try:
        principal, headers = _onboard_owner(app)
        app._conversation_runtime.memories._embedder_factory = None
        app._conversation_runtime.title_runner = None
        yield NS(app=app, url=url, principal=principal, headers=headers, model_calls=model_calls)
    finally:
        app.close()
        _reset_schemas(url)


def test_c1_durable_worker_starts_and_stops_with_the_app_and_health_shape(booted):
    from app.vault_runtime.background_agent.jobs import ROUTINE_TICK_SECONDS

    app = booted.app
    jobs = app._conversation_runtime.background_coordinator.jobs
    health = _api(app, "GET", "/background/health", booted.headers)
    assert health.status_code == 200
    assert health.payload == {"durable": {"state": "running"}}
    assert jobs._thread is not None and jobs._thread.is_alive()
    # C2/C3 wiring: routine tick every 15 s, hourly check-ins and wakes run inside this worker.
    assert ROUTINE_TICK_SECONDS == 15.0
    assert jobs._routines is not None and jobs._checkins is not None and jobs._wake_handler is not None
    thread = jobs._thread
    app.close()
    assert not thread.is_alive()
    assert jobs.health() == {"state": "stopped"}


def _rpc(inbound, token, body):
    status, headers, raw = inbound.handle(method="POST", path="/", headers={"Authorization": f"Bearer {token}"},
                                          body=json.dumps(body).encode())
    return status, headers, json.loads(raw)


def test_c5_a2a_send_message_and_get_task_json_shapes(booted):
    app = booted.app
    enabled = _api(app, "POST", "/builtin-plugins/agent2agent", booted.headers, {"enabled": True})
    assert enabled.status_code == 200, enabled.payload
    inbound = app._a2a_service._inbound
    token = inbound.listen_info(user_id=booted.principal.user_id, workspace_id=booted.principal.workspace_id)["token"]

    def send(text, request_id):
        return _rpc(inbound, token, {"jsonrpc": "2.0", "id": request_id, "method": "SendMessage", "params": {
            "message": {"messageId": "m-" + request_id, "role": "ROLE_USER", "contextId": "ctx-characterization",
                        "parts": [{"text": text, "mediaType": "text/plain"}]}}})

    def get(task_id, request_id):
        return _rpc(inbound, token, {"jsonrpc": "2.0", "id": request_id, "method": "GetTask", "params": {"id": task_id}})

    def text_task(task_id, state, text):
        return {"id": task_id, "contextId": "ctx-characterization",
                "status": {"state": state, "message": {"parts": [{"text": text, "mediaType": "text/plain"}]}},
                "artifacts": [{"parts": [{"text": text, "mediaType": "text/plain"}]}]}

    for text, request_id, final_state, summary in (
        ("Summarize the release notes", "1", "TASK_STATE_COMPLETED", "Done: Summarize the release notes"),
        ("Needs attention: check the source", "3", "TASK_STATE_FAILED", "Could not finish: source missing."),
        # A failed run reports its failure message, as the old engine did (A2A-TEXT; B4 had "failed").
        ("Fails: fetch the quarterly figures", "4", "TASK_STATE_FAILED", "Upstream service refused the request."),
    ):
        status, headers, sent = send(text, request_id)
        assert status == 200 and headers == {"Content-Type": "application/json"}
        task_id = sent["result"]["task"]["id"]
        assert UUID.match(task_id)
        assert sent == {"jsonrpc": "2.0", "id": request_id,
                        "result": {"task": text_task(task_id, "TASK_STATE_SUBMITTED", text)}}
        polled = _wait_until(lambda: (lambda value: value if value[2]["result"]["status"]["state"] not in {
            "TASK_STATE_SUBMITTED", "TASK_STATE_WORKING"} else None)(get(task_id, request_id + "g")), timeout=30)
        assert polled[0] == 200
        assert polled[2] == {"jsonrpc": "2.0", "id": request_id + "g", "result": text_task(task_id, final_state, summary)}

    # Malformed requests and a bad token keep their exact error bodies.
    assert send("", "5")[2] == {"jsonrpc": "2.0", "id": "5",
                                "error": {"code": -32602, "message": "The inbound A2A message is invalid."}}
    assert get("missing", "6")[2] == {"jsonrpc": "2.0", "id": "6",
                                      "error": {"code": -32602, "message": "A2A task is unavailable."}}
    status, headers, body = _rpc(inbound, "wrong-token", {"jsonrpc": "2.0", "id": "7", "method": "GetTask", "params": {}})
    assert (status, headers, body) == (401, {"Content-Type": "application/json", "WWW-Authenticate": "Bearer"},
                                       {"error": "unauthorized", "message": "A2A bearer token is invalid."})
    assert sorted(booted.model_calls) == ["Fails: fetch the quarterly figures", "Needs attention: check the source",
                                          "Summarize the release notes"]


def _normalize(value, ids):
    if isinstance(value, dict):
        return {key: _normalize(item, ids) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item, ids) for item in value]
    if isinstance(value, str):
        if UUID.match(value):
            return ids.setdefault(value, f"<id{len(ids)}>")
        if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", value):
            return "<time>"
    if isinstance(value, float):
        return "<seconds>"
    return value


def test_c7_background_work_list_and_detail_json_for_a_fixture_account(booted):
    app, principal = booted.app, booted.principal
    coordinator = app._conversation_runtime.background_coordinator
    scope = OwnerScope(principal.user_id, principal.workspace_id)
    request = BackgroundRunRequest(
        run_id="11111111-2222-4333-8444-555555555555", objective="Collect the fixture summary",
        instruction_profile="characterization", success_criteria=("A summary exists.",),
        result_schema=background_output_schema(), recipe=ExecutionRecipe.DIRECT, autonomy=AutonomyProfile.LIMITED,
        original_request="Collect the fixture summary", verification_method="Read the result.",
        completion_conditions=("A summary exists.",), context_summary="Fixture context.",
    )
    work_id = coordinator.observe(scope, "explicit_goal", "characterization-c7", {
        "explicit": True, "work_request": WorkRequest(request=request, grant_id=None,
                                                          local_session_id=principal.session_id, destination={})})
    _wait_until(lambda: _api(app, "GET", f"/background/work/{work_id}", booted.headers).payload["state"] == "completed",
                timeout=30)
    ids: dict[str, str] = {}
    listed = _api(app, "GET", "/background/work", booted.headers)
    detail = _api(app, "GET", f"/background/work/{work_id}", booted.headers)
    assert listed.status_code == 200 and detail.status_code == 200
    expected_item = {
        "workId": "<id0>", "state": "completed", "statusLabel": "done", "intentVersion": 1,
        "objective": "Collect the fixture summary", "workerId": None, "workerGeneration": None, "roleKey": None,
        "taskId": None, "task": None, "routineId": None, "parentWorkId": None, "pendingActionId": None,
        "result": {"status": "complete", "summary": "Done: Collect the fixture summary", "artifact_references": [],
                   "verification_summary": "Checked the answer.", "cards": []},
        "createdAt": "<time>", "updatedAt": "<time>", "startedAt": "<time>", "activeSeconds": "<seconds>",
        "runId": "<id1>", "failureCode": None, "completedAt": "<time>", "modelTurns": 0, "toolCalls": 0,
    }
    assert _normalize(listed.payload, ids) == {"items": [expected_item]}
    assert ids == {work_id: "<id0>", request.run_id: "<id1>"}
    assert _normalize(detail.payload, ids) == {
        **expected_item,
        "brief": {"objective": "Collect the fixture summary", "successCriteria": ["A summary exists."],
                  "expectedResult": "", "contextSummary": "Fixture context."},
        "deliveries": [], "reasoningEntries": [],
    }
