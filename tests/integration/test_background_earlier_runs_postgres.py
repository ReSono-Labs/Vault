"""Old-engine rows stay readable read-only; one cancel path (owner decision 5-C, BG-ROUTES)."""
from __future__ import annotations

from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from app.vault_runtime.background_agent.contracts import AutonomyProfile, BackgroundRunRequest, ExecutionRecipe
from app.vault_runtime.background_agent.output_contract import background_output_schema
from tests.integration.test_background_characterization_postgres import booted  # noqa: F401
from tests.support.background_mounted_runtime import _api, _wait_until


def _old_row(url, principal, *, state, objective, profile="inbound-a2a"):
    run_id = str(uuid4())
    request = BackgroundRunRequest(
        run_id=run_id, objective=objective, instruction_profile=profile, success_criteria=("Reply.",),
        result_schema=background_output_schema(), recipe=ExecutionRecipe.DIRECT, autonomy=AutonomyProfile.LIMITED,
        original_request=objective, verification_method="Read it.", completion_conditions=("Reply.",),
    )
    terminal = state in {"completed", "failed", "cancelled"}
    with psycopg.connect(url) as connection:
        connection.execute(
            """INSERT INTO vault_private.vault_background_runs
               (run_id,user_id,workspace_id,local_session_id,request_json,state,output_json,model_turns,completed_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,2,CASE WHEN %s THEN now() END)""",
            (run_id, principal.user_id, principal.workspace_id, principal.session_id, Jsonb(request.payload()),
             state, Jsonb({"summary": "Earlier answer"}) if state == "completed" else None, terminal))
        connection.execute(
            """INSERT INTO vault_private.vault_background_run_events
               (run_id,event_index,user_id,workspace_id,event_type,state,detail_json)
               VALUES (%s,0,%s,%s,'reasoning_summary',%s,%s)""",
            (run_id, principal.user_id, principal.workspace_id, state, Jsonb({"summary": "Old reasoning."})))
    return run_id


def test_earlier_runs_list_only_old_rows_read_only_and_one_cancel_path(booted):  # noqa: F811
    app, principal, headers = booted.app, booted.principal, booted.headers
    done = _old_row(booted.url, principal, state="completed", objective="Old peer request")
    stuck = _old_row(booted.url, principal, state="queued", objective="Old queued request", profile="voice-goal")
    created = _api(app, "POST", "/background/runs", headers, {
        "objective": "New compat run", "instructionProfile": "strict", "successCriteria": ["Done."],
        "resultSchema": {"type": "object"}, "originalRequest": "New compat run",
        "verificationMethod": "Read it.", "completionConditions": ["Done."]})
    new_run = created.payload["runId"]
    _wait_until(lambda: _api(app, "GET", f"/background/runs/{new_run}", headers).payload["state"] == "completed",
                timeout=30)

    listed = _api(app, "GET", "/background/runs", headers)
    assert listed.status_code == 200
    assert sorted(item["runId"] for item in listed.payload["items"]) == sorted([done, stuck])
    old = next(item for item in listed.payload["items"] if item["runId"] == done)
    assert (old["state"], old["output"], old["invocationType"], old["modelTurns"]) == (
        "completed", {"summary": "Earlier answer"}, "inbound-a2a", 2)
    assert [entry["detail"] for entry in old["reasoningEntries"]] == [{"summary": "Old reasoning."}]
    assert next(item for item in listed.payload["items"] if item["runId"] == stuck)["invocationType"] == "voice_goal"
    one = _api(app, "GET", f"/background/runs/{done}", headers)
    assert one.status_code == 200 and one.payload["runId"] == done and one.payload["objective"] == "Old peer request"

    # The old cancel route is gone; nothing changes on the row.
    assert _api(app, "POST", f"/background/runs/{stuck}/cancel", headers, {}).status_code == 404
    with psycopg.connect(booted.url) as connection:
        assert connection.execute("SELECT state,cancellation_requested FROM vault_private.vault_background_runs WHERE run_id=%s",
                                  (stuck,)).fetchone() == ("queued", False)
    # Delete stays for a finished earlier run only; work items keep their runs.
    assert _api(app, "DELETE", f"/background/runs/{stuck}", headers).status_code == 409
    assert _api(app, "DELETE", f"/background/runs/{new_run}", headers).status_code == 403
    deleted = _api(app, "DELETE", f"/background/runs/{done}", headers)
    assert deleted.status_code == 200 and deleted.payload == {"runId": done, "deleted": True}
    assert [item["runId"] for item in _api(app, "GET", "/background/runs", headers).payload["items"]] == [stuck]
    assert _api(app, "GET", f"/background/runs/{new_run}", headers).payload["state"] == "completed"
