"""New-engine work shows reasoning in the Background work detail (owner decision 5-D, BG-05).

The resumable executor writes reasoning_summary and agent_evidence events in the shape the old
engine wrote them, and the detail reads them by run id."""
from __future__ import annotations

import json
from types import SimpleNamespace as NS

import psycopg
from agents import Runner

from app.vault_runtime.background_agent.contracts import AutonomyProfile, BackgroundRunRequest, ExecutionRecipe
from app.vault_runtime.background_agent.coordination_contracts import OwnerScope, WorkRequest
from app.vault_runtime.background_agent.output_contract import BackgroundAgentOutput, background_output_schema
from tests.integration.test_background_characterization_postgres import booted  # noqa: F401
from tests.support.background_mounted_runtime import _api, _wait_until


def test_new_engine_work_detail_shows_reasoning_and_evidence(booted, monkeypatch):  # noqa: F811
    app, principal = booted.app, booted.principal

    async def run_with_reasoning(agent, *args, **kwargs):
        hooks = kwargs["hooks"]
        await hooks.on_llm_start(None, agent, None, None)
        await hooks.on_llm_end(None, agent, NS(output=[
            NS(type="reasoning", summary=[NS(text="Read the release notes first."), NS(text="  ")]),
            NS(type="message", summary=[NS(text="not reasoning")]),
        ]))
        objective = json.loads(args[0])["objective"]
        return NS(interruptions=[], final_output=BackgroundAgentOutput(
            status="complete", summary=f"Done: {objective}", verification_summary="Checked.",
            phase_evidence=[{"phase": "verify", "summary": "Compared against the changelog."}]))

    monkeypatch.setattr(Runner, "run", staticmethod(run_with_reasoning))
    request = BackgroundRunRequest(
        run_id="21111111-2222-4333-8444-555555555555", objective="Summarize the release",
        instruction_profile="characterization", success_criteria=("A summary exists.",),
        result_schema=background_output_schema(), recipe=ExecutionRecipe.DIRECT, autonomy=AutonomyProfile.LIMITED,
        original_request="Summarize the release", verification_method="Read it.",
        completion_conditions=("A summary exists.",),
    )
    work_id = app._conversation_runtime.background_coordinator.observe(
        OwnerScope(principal.user_id, principal.workspace_id), "explicit_goal", "reasoning-5d", {
            "explicit": True, "work_request": WorkRequest(request=request, grant_id=None,
                                                          local_session_id=principal.session_id, destination={})})
    detail = _wait_until(lambda: (lambda value: value if value.payload["state"] == "completed" else None)(
        _api(app, "GET", f"/background/work/{work_id}", booted.headers)), timeout=30).payload
    assert [(entry["type"], entry["detail"]) for entry in detail["reasoningEntries"]] == [
        ("reasoning_summary", {"summary": "Read the release notes first."}),
        ("agent_evidence", {"phase": "verify", "summary": "Compared against the changelog."}),
    ]
    assert all(entry["createdAt"] for entry in detail["reasoningEntries"])
    assert detail["modelTurns"] == 1
    with psycopg.connect(booted.url) as connection:
        rows = connection.execute(
            """SELECT event_index, event_type, state, user_id FROM vault_private.vault_background_run_events
               WHERE run_id=%s ORDER BY event_index""", (request.run_id,)).fetchall()
    assert rows == [(0, "reasoning_summary", "running", principal.user_id),
                    (1, "agent_evidence", "running", principal.user_id)]
