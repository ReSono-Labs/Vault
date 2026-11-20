"""Task 9 PostgreSQL integration tests: Local API /background/* routes for Activity, workers, actions, routines, and preferences."""
from __future__ import annotations

import json
from types import SimpleNamespace as NS

import psycopg
from psycopg.types.json import Jsonb
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.background_agent.action_domains import TaskActionDomain
from app.vault_runtime.background_agent.actions import BackgroundActions
from app.vault_runtime.background_agent.authority import BackgroundAuthority
from app.vault_runtime.background_agent.contracts import BackgroundRunRequest
from app.vault_runtime.background_agent.coordination_contracts import (
    ApprovalDecision,
    ExecutionOutcome,
    OwnerScope,
    WorkRequest,
    WorkState,
)
from app.vault_runtime.background_agent.coordination_repository import CoordinationRepository
from app.vault_runtime.background_agent.repository import BackgroundRunRepository
from app.vault_runtime.local_api.app import VaultLocalApiApp
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService
from app.vault_runtime.tasks.repository import TaskRepository


def _auth_headers(tokens, *, include_csrf: bool = True) -> dict[str, str]:
    headers = {
        "Cookie": f"resono_refresh={tokens.session_token}; resono_csrf={tokens.csrf_token}",
    }
    if include_csrf:
        headers["X-ReSono-CSRF"] = tokens.csrf_token
    return headers


def _setup_api(context):
    url, _owner, _second, runs = context
    identities = LocalIdentityService(
        repository=LocalIdentityRepository(database_url=url),
        setup_credential_hash=hash_token("setup"),
    )
    owner_tokens = identities.login(username="owner", password="owner-password")
    second_tokens = identities.login(username="second", password="second-password")
    coord = CoordinationRepository(database_url=url)
    coord.ensure_schema()
    tasks = TaskRepository(database_url=url)
    tasks.ensure_schema()
    app = VaultLocalApiApp(
        store=NS(health=lambda: {"status": "ok"}),
        token="test-token",
        identity_service=identities,
        background_runs=runs,
        tasks=tasks,
    )
    return NS(
        url=url,
        app=app,
        coord=coord,
        tasks=tasks,
        owner=owner_tokens.principal,
        owner_headers=_auth_headers(owner_tokens),
        owner_no_csrf=_auth_headers(owner_tokens, include_csrf=False),
        second=second_tokens.principal,
        second_headers=_auth_headers(second_tokens),
    )


def test_settings_requests_do_not_run_schema_migrations(context, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    env = _setup_api(context)

    def unexpected_migration(_repository):
        pytest.fail("Settings requests must not migrate the database")

    monkeypatch.setattr(CoordinationRepository, "ensure_schema", unexpected_migration)
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(
            lambda path: env.app.handle(method="GET", target=path, headers=env.owner_headers),
            ("/background/preferences", "/background/workers", "/background/routines"),
        ))
    assert [response.status_code for response in responses] == [200, 200, 200]


def _request_sample(run_id: str = "run-bg-1", objective: str = "Summarize unread mail") -> BackgroundRunRequest:
    return BackgroundRunRequest(
        run_id=run_id,
        objective=objective,
        instruction_profile="background-general",
        success_criteria=("Summary produced",),
        result_schema={"type": "object"},
        original_request=objective,
        verification_method="Check summary fields",
        completion_conditions=("Summary verified",),
    )


def test_background_preferences_default_off_and_csrf_required(context):
    env = _setup_api(context)

    res = env.app.handle(method="GET", target="/background/preferences", headers=env.owner_headers)
    assert res.status_code == 200, res.payload
    assert res.payload["enabled"] is False
    assert res.payload["optIn"] is False
    assert res.payload["quietHours"] == {}
    assert res.payload["approvedGrantIds"] == []
    assert "standingScope" in res.payload

    # Missing CSRF is rejected
    no_csrf = env.app.handle(
        method="POST",
        target="/background/preferences",
        headers=env.owner_no_csrf,
        body=json.dumps({"enabled": True}).encode(),
    )
    assert no_csrf.status_code == 403

    # Update preferences with CSRF
    updated = env.app.handle(
        method="POST",
        target="/background/preferences",
        headers=env.owner_headers,
        body=json.dumps({
            "enabled": True,
            "quietHours": {"start": "22:00", "end": "07:00", "timezone": "America/New_York"},
        }).encode(),
    )
    assert updated.status_code == 200, updated.payload
    assert updated.payload["enabled"] is True
    assert updated.payload["optIn"] is True
    assert updated.payload["quietHours"] == {"start": "22:00", "end": "07:00", "timezone": "America/New_York"}

    # Secondary user still has preferences off by default in their own scope
    second_prefs = env.app.handle(method="GET", target="/background/preferences", headers=env.second_headers)
    assert second_prefs.status_code == 200
    assert second_prefs.payload["enabled"] is False


def test_worker_proposal_decision_duplicate_and_stale_generation_controls(context):
    env = _setup_api(context)

    # Propose a specialist role -> returns prepared worker_create action, does NOT create worker yet
    prop = env.app.handle(
        method="POST",
        target="/background/workers",
        headers=env.owner_headers,
        body=json.dumps({
            "roleKey": "inbox-triage",
            "purpose": "Triage incoming newsletters and summarize urgent threads",
            "instructions": "Only inspect newsletter headers and summarize.",
            "toolNames": ["email_list", "email_read"],
            "resourcePolicy": {},
        }).encode(),
    )
    assert prop.status_code in (200, 201, 202), prop.payload
    action = prop.payload["action"]
    assert action["kind"] == "worker_create"
    assert len(action["actionHash"]) == 64

    workers_before = env.app.handle(method="GET", target="/background/workers", headers=env.owner_headers)
    assert workers_before.status_code == 200
    assert workers_before.payload["items"] == []

    # Pending action appears in GET /background/actions for owner, never for second user
    owner_actions = env.app.handle(method="GET", target="/background/actions", headers=env.owner_headers)
    assert owner_actions.status_code == 200
    assert any(a["actionId"] == action["actionId"] for a in owner_actions.payload["items"])

    second_actions = env.app.handle(method="GET", target="/background/actions", headers=env.second_headers)
    assert second_actions.status_code == 200
    assert second_actions.payload["items"] == []

    # Foreign user cannot decide owner's action
    foreign_decide = env.app.handle(
        method="POST",
        target=f"/background/actions/{action['actionId']}/decision",
        headers=env.second_headers,
        body=json.dumps({
            "actionHash": action["actionHash"],
            "choice": "allow_once",
            "decisionId": "dec-foreign",
        }).encode(),
    )
    assert foreign_decide.status_code == 403

    # Model-style approve=true or forged actor/channel in body is rejected
    false_model_approve = env.app.handle(
        method="POST",
        target=f"/background/actions/{action['actionId']}/decision",
        headers=env.owner_headers,
        body=json.dumps({
            "actionHash": action["actionHash"],
            "choice": "allow_once",
            "decisionId": "dec-model-flag",
            "approve": True,
        }).encode(),
    )
    assert false_model_approve.status_code == 400

    # Valid owner approval creates the specialist worker once
    decided = env.app.handle(
        method="POST",
        target=f"/background/actions/{action['actionId']}/decision",
        headers=env.owner_headers,
        body=json.dumps({
            "actionHash": action["actionHash"],
            "choice": "allow_once",
            "decisionId": "dec-worker-1",
        }).encode(),
    )
    assert decided.status_code == 200, decided.payload
    assert decided.payload["decisionId"] == "dec-worker-1"
    worker_id = decided.payload["workerId"]
    assert isinstance(worker_id, str) and worker_id

    # Idempotent replay of the exact same decision_id succeeds without creating a second worker
    replay = env.app.handle(
        method="POST",
        target=f"/background/actions/{action['actionId']}/decision",
        headers=env.owner_headers,
        body=json.dumps({
            "actionHash": action["actionHash"],
            "choice": "allow_once",
            "decisionId": "dec-worker-1",
        }).encode(),
    )
    assert replay.status_code == 200
    assert replay.payload["workerId"] == worker_id

    # Conflicting decision_id on already-decided action fails with 409
    dup_conflict = env.app.handle(
        method="POST",
        target=f"/background/actions/{action['actionId']}/decision",
        headers=env.owner_headers,
        body=json.dumps({
            "actionHash": action["actionHash"],
            "choice": "deny",
            "decisionId": "dec-worker-2",
        }).encode(),
    )
    assert dup_conflict.status_code == 409

    # Worker is now listed with generation 1 and status idle
    workers_after = env.app.handle(method="GET", target="/background/workers", headers=env.owner_headers)
    assert workers_after.status_code == 200
    assert len(workers_after.payload["items"]) == 1
    w_item = workers_after.payload["items"][0]
    assert w_item["workerId"] == worker_id
    assert w_item["roleKey"] == "inbox-triage"
    assert w_item["status"] == "idle"
    assert w_item["generation"] == 1
    assert w_item["toolNames"] == ["email_list", "email_read"]

    # Stale generation on pause is rejected with 409
    stale_pause = env.app.handle(
        method="POST",
        target=f"/background/workers/{worker_id}/pause",
        headers=env.owner_headers,
        body=json.dumps({"generation": 99}).encode(),
    )
    assert stale_pause.status_code == 409

    # Valid pause bumps generation to 2
    paused = env.app.handle(
        method="POST",
        target=f"/background/workers/{worker_id}/pause",
        headers=env.owner_headers,
        body=json.dumps({"generation": 1}).encode(),
    )
    assert paused.status_code == 200, paused.payload
    assert paused.payload["generation"] == 2
    assert paused.payload["status"] == "paused"

    # Seed a work + private session row to verify reset purges private session context
    owner_scope = OwnerScope(env.owner.user_id, env.owner.workspace_id)
    work_id = env.coord.create_work(
        owner_scope,
        WorkRequest(
            request=_request_sample("run-reset-1", "Check inbox"),
            grant_id=None,
            local_session_id=env.owner.session_id,
            destination={"kind": "activity"},
        ),
        source_key="test:reset:1",
    )
    with psycopg.connect(env.url) as conn:
        conn.execute(
            """INSERT INTO vault_private.vault_background_sessions
               (session_id, user_id, workspace_id, worker_id, work_id, worker_generation, intent_version,
                history_json, checkpoint_json)
               VALUES ('sess-reset-1', %s, %s, %s, %s, 2, 1, %s, %s)""",
            (
                env.owner.user_id,
                env.owner.workspace_id,
                worker_id,
                work_id,
                Jsonb([{"secret": "PRIVATE_SESSION_HISTORY"}]),
                Jsonb({"state": "PRIVATE_CHECKPOINT"}),
            ),
        )

    # Reset with generation 2 bumps to 3, returns worker to idle, and purges session history/checkpoint
    reset_res = env.app.handle(
        method="POST",
        target=f"/background/workers/{worker_id}/reset",
        headers=env.owner_headers,
        body=json.dumps({"generation": 2}).encode(),
    )
    assert reset_res.status_code == 200, reset_res.payload
    assert reset_res.payload["generation"] == 3
    assert reset_res.payload["status"] == "idle"

    with psycopg.connect(env.url) as conn:
        sess_row = conn.execute(
            "SELECT history_json, checkpoint_json FROM vault_private.vault_background_sessions WHERE session_id='sess-reset-1'"
        ).fetchone()
    assert sess_row == ([], None)

    # Delete with generation 3 bumps to 4 and hides from active list
    del_res = env.app.handle(
        method="POST",
        target=f"/background/workers/{worker_id}/delete",
        headers=env.owner_headers,
        body=json.dumps({"generation": 3}).encode(),
    )
    assert del_res.status_code == 200, del_res.payload
    assert del_res.payload["generation"] == 4
    assert del_res.payload["status"] == "deleted"

    workers_final = env.app.handle(method="GET", target="/background/workers", headers=env.owner_headers)
    assert workers_final.payload["items"] == []


def test_work_activity_projection_task_link_cancel_and_no_private_leak(context):
    env = _setup_api(context)
    owner_scope = OwnerScope(env.owner.user_id, env.owner.workspace_id)
    second_scope = OwnerScope(env.second.user_id, env.second.workspace_id)

    # Create canonical tasks for owner and second user
    owner_prep = env.tasks.prepare(
        user_id=env.owner.user_id,
        workspace_id=env.owner.workspace_id,
        operation="add",
        task_id=None,
        payload={"text": "Prepare Q4 board deck"},
        voice_session_id="vs-owner",
        tool_call_id="tc-owner-1",
        utterance_id=1,
    )
    owner_claim = env.tasks.claim(
        user_id=env.owner.user_id,
        workspace_id=env.owner.workspace_id,
        action_id=str(owner_prep["actionId"]),
        content_hash=str(owner_prep["contentHash"]),
        voice_session_id="vs-owner",
        approval_utterance_id=2,
    )
    owner_task = env.tasks.execute(
        user_id=env.owner.user_id,
        workspace_id=env.owner.workspace_id,
        claim=owner_claim,
    )
    assert owner_task is not None

    second_prep = env.tasks.prepare(
        user_id=env.second.user_id,
        workspace_id=env.second.workspace_id,
        operation="add",
        task_id=None,
        payload={"text": "Second user private task"},
        voice_session_id="vs-second",
        tool_call_id="tc-second-1",
        utterance_id=1,
    )
    second_claim = env.tasks.claim(
        user_id=env.second.user_id,
        workspace_id=env.second.workspace_id,
        action_id=str(second_prep["actionId"]),
        content_hash=str(second_prep["contentHash"]),
        voice_session_id="vs-second",
        approval_utterance_id=2,
    )
    second_task = env.tasks.execute(
        user_id=env.second.user_id,
        workspace_id=env.second.workspace_id,
        claim=second_claim,
    )
    assert second_task is not None

    # Linking owner's work to second user's task is rejected (403)
    work_id = env.coord.create_work(
        owner_scope,
        WorkRequest(
            request=_request_sample("run-work-1", "Draft Q4 metrics section"),
            grant_id=None,
            local_session_id=env.owner.session_id,
            destination={"kind": "activity", "task_id": owner_task.task_id},
        ),
        source_key="chat:c1:t1",
    )
    foreign_link = env.app.handle(
        method="POST",
        target=f"/background/work/{work_id}/task",
        headers=env.owner_headers,
        body=json.dumps({"taskId": second_task.task_id}).encode(),
    )
    assert foreign_link.status_code == 403

    # Link owner's work to owner's canonical task
    valid_link = env.app.handle(
        method="POST",
        target=f"/background/work/{work_id}/task",
        headers=env.owner_headers,
        body=json.dumps({"taskId": owner_task.task_id}).encode(),
    )
    assert valid_link.status_code == 200, valid_link.payload
    assert valid_link.payload["taskId"] == owner_task.task_id

    # Seed a worker + private session transcript + waiting_approval state
    with psycopg.connect(env.url) as conn:
        conn.execute(
            """INSERT INTO vault_private.vault_background_workers
               (worker_id, user_id, workspace_id, role_key, spec_json, spec_hash, generation, status)
               VALUES ('w-priv-1', %s, %s, 'analyst', %s, %s, 1, 'active')""",
            (
                env.owner.user_id,
                env.owner.workspace_id,
                Jsonb({"role_key": "analyst", "purpose": "Analyze", "instructions": "Private", "tool_names": [], "resource_policy": {}}),
                "a" * 64,
            ),
        )
        conn.execute(
            """UPDATE vault_private.vault_background_work
               SET worker_id='w-priv-1', worker_generation=1, state='waiting_approval',
                   result_json=%s
               WHERE work_id=%s""",
            (
                Jsonb({
                    "status": "completed",
                    "summary": "Public coordinator summary",
                    "artifact_references": ["workspace:q4.md"],
                    "verification_summary": "Checked against numbers",
                    "private_transcript": "NEVER_LEAK_HELPER_TRANSCRIPT",
                    "private_session_history": ["NEVER_LEAK_SESSION_HISTORY"],
                    "checkpoint_json": {"secret": "NEVER_LEAK_CHECKPOINT"},
                }),
                work_id,
            ),
        )
        conn.execute(
            """INSERT INTO vault_private.vault_background_sessions
               (session_id, user_id, workspace_id, worker_id, work_id, worker_generation, intent_version,
                history_json, checkpoint_json)
               VALUES ('sess-priv-1', %s, %s, 'w-priv-1', %s, 1, 1, %s, %s)""",
            (
                env.owner.user_id,
                env.owner.workspace_id,
                work_id,
                Jsonb([{"role": "assistant", "content": "NEVER_LEAK_HELPER_TRANSCRIPT"}]),
                Jsonb({"raw": "NEVER_LEAK_CHECKPOINT"}),
            ),
        )

    # GET /background/work projects canonical statusLabel='needs-you', task link, and strips all private fields
    list_res = env.app.handle(method="GET", target="/background/work", headers=env.owner_headers)
    assert list_res.status_code == 200, list_res.payload
    raw_list_json = json.dumps(list_res.payload)
    assert "NEVER_LEAK_HELPER_TRANSCRIPT" not in raw_list_json
    assert "NEVER_LEAK_SESSION_HISTORY" not in raw_list_json
    assert "NEVER_LEAK_CHECKPOINT" not in raw_list_json

    items = list_res.payload["items"]
    assert len(items) == 1
    assert items[0]["workId"] == work_id
    assert items[0]["state"] == "waiting_approval"
    assert items[0]["statusLabel"] == "needs-you"
    assert items[0]["taskId"] == owner_task.task_id
    assert items[0]["task"]["text"] == "Prepare Q4 board deck"

    # GET /background/work/{id}
    detail_res = env.app.handle(method="GET", target=f"/background/work/{work_id}", headers=env.owner_headers)
    assert detail_res.status_code == 200, detail_res.payload
    raw_detail_json = json.dumps(detail_res.payload)
    assert "NEVER_LEAK_HELPER_TRANSCRIPT" not in raw_detail_json
    assert "NEVER_LEAK_CHECKPOINT" not in raw_detail_json
    assert detail_res.payload["statusLabel"] == "needs-you"
    assert detail_res.payload["result"]["summary"] == "Public coordinator summary"

    # Completing work does not auto-complete the user's canonical task
    with psycopg.connect(env.url) as conn:
        conn.execute("UPDATE vault_private.vault_background_work SET state='completed' WHERE work_id=%s", (work_id,))
    done_detail = env.app.handle(method="GET", target=f"/background/work/{work_id}", headers=env.owner_headers)
    assert done_detail.payload["statusLabel"] == "done"
    canonical_task = env.tasks.get(user_id=env.owner.user_id, workspace_id=env.owner.workspace_id, task_id=owner_task.task_id)
    assert canonical_task is not None and canonical_task.status == "open"

    # Foreign user cannot inspect or cancel owner's work
    assert env.app.handle(method="GET", target=f"/background/work/{work_id}", headers=env.second_headers).status_code == 403
    assert env.app.handle(method="POST", target=f"/background/work/{work_id}/cancel", headers=env.second_headers).status_code == 403

    # Create a second running work item and cancel it via POST /background/work/{id}/cancel
    work_id_2 = env.coord.create_work(
        owner_scope,
        WorkRequest(
            request=_request_sample("run-work-2", "Cancelable background work"),
            grant_id=None,
            local_session_id=env.owner.session_id,
            destination={"kind": "activity"},
        ),
        source_key="chat:c1:t2",
    )
    cancel_res = env.app.handle(
        method="POST",
        target=f"/background/work/{work_id_2}/cancel",
        headers=env.owner_headers,
        body=b"{}",
    )
    assert cancel_res.status_code == 200, cancel_res.payload
    assert cancel_res.payload["state"] == "cancelled"
    assert cancel_res.payload["statusLabel"] == "failed"


def test_routines_create_list_pause_and_cancel_and_secondary_user_isolation(context):
    env = _setup_api(context)
    owner_scope = OwnerScope(env.owner.user_id, env.owner.workspace_id)

    # Prepare and approve an execution grant for routines
    auth = BackgroundAuthority(database_url=env.url)
    actions = BackgroundActions(database_url=env.url)
    proposal = {
        "purpose": "Morning digest routine",
        "tool_names": ["email_list"],
        "resource_policy": {},
    }
    prepared_grant = actions.prepare(owner_scope, "execution_grant", proposal, None, None)
    grant_decision = env.app.handle(
        method="POST",
        target=f"/background/actions/{prepared_grant.action_id}/decision",
        headers=env.owner_headers,
        body=json.dumps({
            "actionHash": prepared_grant.action_hash,
            "choice": "allow_once",
            "decisionId": "dec-grant-routine-1",
        }).encode(),
    )
    assert grant_decision.status_code == 200, grant_decision.payload
    grant_id = grant_decision.payload["grantId"]
    assert isinstance(grant_id, str) and grant_id

    # Create routine via POST /background/routines
    created = env.app.handle(
        method="POST",
        target="/background/routines",
        headers=env.owner_headers,
        body=json.dumps({
            "rule": {"kind": "cron", "cron": "0 8 * * *"},
            "timezone": "America/New_York",
            "template": {"request": {"objective": "Prepare morning digest"}},
            "grantId": grant_id,
        }).encode(),
    )
    assert created.status_code in (200, 201), created.payload
    routine_id = created.payload["routineId"]

    # List routines for owner vs secondary user
    owner_routines = env.app.handle(method="GET", target="/background/routines", headers=env.owner_headers)
    assert owner_routines.status_code == 200
    assert [r["routineId"] for r in owner_routines.payload["items"]] == [routine_id]
    assert owner_routines.payload["items"][0]["status"] == "active"

    second_routines = env.app.handle(method="GET", target="/background/routines", headers=env.second_headers)
    assert second_routines.status_code == 200
    assert second_routines.payload["items"] == []

    # Secondary user cannot pause owner's routine
    assert env.app.handle(
        method="POST",
        target=f"/background/routines/{routine_id}/pause",
        headers=env.second_headers,
        body=b"{}",
    ).status_code == 403

    # Owner pauses routine
    paused = env.app.handle(
        method="POST",
        target=f"/background/routines/{routine_id}/pause",
        headers=env.owner_headers,
        body=b"{}",
    )
    assert paused.status_code == 200
    assert paused.payload["status"] == "paused"

    # Owner cancels routine
    cancelled = env.app.handle(
        method="POST",
        target=f"/background/routines/{routine_id}/cancel",
        headers=env.owner_headers,
        body=b"{}",
    )
    assert cancelled.status_code == 200
    assert cancelled.payload["status"] == "deleted"

    # Secondary user creates their own worker proposal and sees only browser channel
    sec_prop = env.app.handle(
        method="POST",
        target="/background/workers",
        headers=env.second_headers,
        body=json.dumps({
            "roleKey": "notes-helper",
            "purpose": "Organize notes",
            "instructions": "Keep notes tidy.",
            "toolNames": ["tasks_list"],
            "resourcePolicy": {},
        }).encode(),
    )
    assert sec_prop.status_code in (200, 201, 202), sec_prop.payload
    sec_actions = env.app.handle(method="GET", target="/background/actions", headers=env.second_headers)
    assert sec_actions.status_code == 200
    assert len(sec_actions.payload["items"]) == 1
    assert sec_actions.payload["items"][0]["channels"] == ["browser"]


def test_settings_stop_aborts_only_selected_run(context):
    from app.vault_runtime.background_agent.jobs import BackgroundJobs
    from app.vault_runtime.background_agent.errors import BackgroundRunAuthorizationError
    from tests.support.background_jobs import enqueue, ready

    env = _setup_api(context)

    async def execute(_attempt):
        raise AssertionError("This test claims jobs directly")

    jobs = BackgroundJobs(database_url=env.url, executor=execute)
    jobs.ensure_schema()
    env.app._conversation_runtime = NS(background_coordinator=NS(jobs=jobs))
    target = ready(context, "stop-target", principal=env.owner)
    other = ready(context, "stop-other", principal=env.owner)
    job_id = enqueue(context, jobs, target)
    enqueue(context, jobs, other)
    attempt = jobs.claim(target)
    assert attempt is not None
    listed = env.app.handle(method="GET", target="/background/work", headers=env.owner_headers)
    assert listed.status_code == 200, listed.payload
    active = next(item for item in listed.payload["items"] if item["workId"] == target)
    assert active["state"] == "running"
    assert active["startedAt"] and active["activeSeconds"] >= 0
    stopped = env.app.handle(method="POST", target=f"/background/work/{target}/cancel",
                             headers=env.owner_headers, body=b"{}")
    assert stopped.status_code == 200, stopped.payload
    assert stopped.payload["state"] == "cancelled"
    with pytest.raises(BackgroundRunAuthorizationError):
        jobs.validate_attempt(attempt)
    with psycopg.connect(env.url) as connection:
        assert connection.execute("SELECT status FROM vault_background_queue.procrastinate_jobs WHERE id=%s",
                                  (job_id,)).fetchone() == ("cancelled",)
        assert connection.execute("SELECT state FROM vault_private.vault_background_work WHERE work_id=%s",
                                  (other,)).fetchone() == ("queued",)
    # The Background work page reads each run's outcome from the list and detail endpoints.
    after = env.app.handle(method="GET", target="/background/work", headers=env.owner_headers)
    stopped_item = next(item for item in after.payload["items"] if item["workId"] == target)
    assert stopped_item["runId"] and {"failureCode", "completedAt", "modelTurns", "toolCalls"} <= set(stopped_item)
    detail = env.app.handle(method="GET", target=f"/background/work/{target}", headers=env.owner_headers)
    assert detail.status_code == 200, detail.payload
    assert detail.payload["runId"] == stopped_item["runId"]
    assert detail.payload["startedAt"] and detail.payload["reasoningEntries"] == []
