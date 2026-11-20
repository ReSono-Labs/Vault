"""POST /background/runs stays for one release (owner decision 5-A, BG-03): accepted, runs on the
durable engine, keeps its response shape and logs a deprecation warning without content."""
from __future__ import annotations

import logging

from tests.integration.test_background_characterization_postgres import booted  # noqa: F401
from tests.support.background_mounted_runtime import _api, _wait_until

RUN_KEYS = {
    "runId", "agentKind", "invocationType", "originId", "objective", "recipe", "state",
    "cancellationRequested", "output", "failure", "failureCode", "failureMessage", "failureExplanation",
    "modelTurns", "toolCalls", "createdAt", "updatedAt", "completedAt", "reasoningEntries", "progress",
}
PROGRESS_KEYS = {"label", "fraction", "active", "tone", "activity", "modelTurns", "toolCalls", "timeline"}


def test_deprecated_post_background_runs_runs_on_the_durable_engine(booted, caplog):  # noqa: F811
    app, principal = booted.app, booted.principal
    caplog.set_level(logging.WARNING, logger="app.vault_runtime.local_api.app")
    created = _api(app, "POST", "/background/runs", booted.headers, {
        "objective": "Return local status PRIVATE-OBJECTIVE", "instructionProfile": "strict",
        "successCriteria": ["Status exists."],
        "resultSchema": {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]},
        "originalRequest": "Return local status.", "verificationMethod": "Validate schema.",
        "completionConditions": ["Status exists."], "requestedToolNames": [],
    })
    assert created.status_code == 202, created.payload
    assert set(created.payload) == RUN_KEYS and set(created.payload["progress"]) == PROGRESS_KEYS
    assert created.payload["agentKind"] == "background" and created.payload["invocationType"] == "strict"
    assert created.payload["originId"] == principal.session_id
    assert created.payload["state"] in {"queued", "running", "completed"}
    warnings = [record for record in caplog.records if record.name == "app.vault_runtime.local_api.app"]
    assert [record.getMessage() for record in warnings] == ["background_runs_post_deprecated"]
    assert "PRIVATE" not in caplog.text

    run_id = created.payload["runId"]
    done = _wait_until(lambda: (lambda value: value if value.payload["state"] == "completed" else None)(
        _api(app, "GET", f"/background/runs/{run_id}", booted.headers)), timeout=30)
    assert set(done.payload) == RUN_KEYS
    assert done.payload["output"]["summary"] == "Done: Return local status PRIVATE-OBJECTIVE"
    work = _api(app, "GET", "/background/work", booted.headers).payload["items"]
    assert [(item["runId"], item["state"], item["roleKey"]) for item in work] == [(run_id, "completed", None)]
    assert booted.model_calls == ["Return local status PRIVATE-OBJECTIVE"]
