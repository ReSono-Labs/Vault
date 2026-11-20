"""A2A inbound runs as a direct one-shot on the durable engine (owner decision 5-B, BG-02).

The JSON shapes are recorded in test_background_characterization_postgres.py (C5)."""
from __future__ import annotations

import json
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from app.vault_runtime.background_agent.contracts import (
    AutonomyProfile, BackgroundRunRequest, ExecutionRecipe,
)
from app.vault_runtime.background_agent.output_contract import background_output_schema
from tests.integration.test_background_characterization_postgres import _rpc, booted  # noqa: F401
from tests.support.background_mounted_runtime import _api, _wait_until


def test_a2a_message_is_one_direct_work_item_and_earlier_tasks_still_read(booted):  # noqa: F811
    app, principal = booted.app, booted.principal
    assert _api(app, "POST", "/builtin-plugins/agent2agent", booted.headers, {"enabled": True}).status_code == 200
    inbound = app._a2a_service._inbound
    token = inbound.listen_info(user_id=principal.user_id, workspace_id=principal.workspace_id)["token"]
    _, _, sent = _rpc(inbound, token, {"jsonrpc": "2.0", "id": "1", "method": "SendMessage", "params": {
        "message": {"parts": [{"text": "Answer the peer", "mediaType": "text/plain"}]}}})
    task_id = sent["result"]["task"]["id"]
    done = _wait_until(lambda: (lambda body: body if body["result"]["status"]["state"] == "TASK_STATE_COMPLETED" else None)(
        _rpc(inbound, token, {"jsonrpc": "2.0", "id": "2", "method": "GetTask", "params": {"id": task_id}})[2]), timeout=30)
    assert done["result"]["status"]["message"]["parts"][0]["text"] == "Done: Answer the peer"
    session_id, run_id = inbound.repository.inbound_task(task_id=task_id)[2:4]
    with psycopg.connect(booted.url) as connection:
        work = connection.execute(
            """SELECT w.source_key, w.worker_id, w.request_json->'destination', w.local_session_id, w.state,
                      r.state, r.work_id IS NOT NULL
               FROM vault_private.vault_background_runs r
               JOIN vault_private.vault_background_work w USING (work_id)
               WHERE r.run_id=%s""", (run_id,)).fetchone()
        assert work == (f"direct_run:{run_id}", None, {}, session_id, "completed", "completed", True)
        # Nothing is delivered to a chat and no specialist is proposed for a peer's request.
        assert connection.execute("SELECT count(*) FROM vault_private.vault_background_workers").fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM vault_private.vault_background_events WHERE source_kind='result_delivery'"
        ).fetchone() == (0,)
    assert booted.model_calls == ["Answer the peer"]

    # A task the old engine ran before the upgrade (work_id IS NULL) still answers GetTask.
    earlier_run = str(uuid4())
    request = BackgroundRunRequest(
        run_id=earlier_run, objective="Earlier peer request", instruction_profile="inbound-a2a",
        success_criteria=("Reply.",), result_schema=background_output_schema(), recipe=ExecutionRecipe.DIRECT,
        autonomy=AutonomyProfile.LIMITED, original_request="Earlier peer request",
        verification_method="Read it.", completion_conditions=("Reply.",),
    )
    with psycopg.connect(booted.url) as connection:
        connection.execute(
            """INSERT INTO vault_private.vault_background_runs
               (run_id,user_id,workspace_id,local_session_id,request_json,state,output_json,completed_at)
               VALUES (%s,%s,%s,%s,%s,'completed',%s,now())""",
            (earlier_run, principal.user_id, principal.workspace_id, session_id, Jsonb(request.payload()),
             Jsonb({"summary": "Earlier answer"})))
    inbound.repository.save_inbound_task(task_id="earlier-task", user_id=principal.user_id,
                                         workspace_id=principal.workspace_id, local_session_id=session_id,
                                         run_id=earlier_run, context_id="ctx-earlier")
    _, _, earlier = _rpc(inbound, token, {"jsonrpc": "2.0", "id": "3", "method": "GetTask", "params": {"id": "earlier-task"}})
    assert earlier == {"jsonrpc": "2.0", "id": "3", "result": {
        "id": "earlier-task", "contextId": "ctx-earlier",
        "status": {"state": "TASK_STATE_COMPLETED", "message": {"parts": [{"text": "Earlier answer", "mediaType": "text/plain"}]}},
        "artifacts": [{"parts": [{"text": "Earlier answer", "mediaType": "text/plain"}]}]}}
    assert json.dumps(earlier).count("Earlier answer") == 2
