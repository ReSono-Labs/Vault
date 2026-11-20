"""PostgreSQL integration tests for resumable background execution through approval waits (Task 5)."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import json
from time import monotonic, sleep
from types import SimpleNamespace

import psycopg
import pytest

from app.vault_runtime.background_agent.action_bridge import BackgroundActionBridge, current_tool_authorizer
from app.vault_runtime.background_agent.action_domains import TaskActionDomain
from app.vault_runtime.background_agent.actions import BackgroundActions
from dataclasses import replace
from psycopg.types.json import Jsonb
from app.vault_runtime.background_agent.coordination_contracts import ApprovalDecision, WorkerSpec, WorkScope, WorkState
from app.vault_runtime.background_agent.contracts import AutonomyProfile
from tests.support.background_authority import approve_fixture, components


from app.vault_runtime.background_agent.jobs import BackgroundJobs
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tasks.repository import TaskRepository
from app.vault_runtime.tasks_tools import register_tasks_tools
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.voice.repository import VoiceSessionRepository
from app.vault_runtime.voice.tools import LocalToolAuthority
from tests.support.background_resume import TASK_TOOLS, OfflineTaskModel


class FakeCredentials:
    def __init__(self, provider_key: str = "openai", model_id: str = "gpt-5.4-mini") -> None:
        self.provider_key = provider_key
        self.model_id = model_id

    def selected_provider(self, *, user_id: str, workspace_id: str) -> str:
        return self.provider_key

    def background_access(self, *, user_id: str, workspace_id: str, provider_key: str | None = None):
        return SimpleNamespace(value="sk-offline-test-secret", auth_method="api_key"), self.model_id


def _build_env(context, *, task_text: str = "Ship Phase B", force_complete_on_deny: bool = False):
    from app.vault_runtime.background_agent.executor import ResumableBackgroundExecutor

    m, repo, owner, request, authority, workers = components(context)
    policy = {"tool_names": TASK_TOOLS, "resource_policy": {}}
    with psycopg.connect(context[0]) as connection:
        connection.execute(
            """INSERT INTO vault_private.vault_background_execution_grants
               (grant_id,user_id,workspace_id,purpose,policy_json)
               VALUES ('grant',%s,%s,'Manage approved tasks',%s)""",
            (owner.user_id, owner.workspace_id, Jsonb(policy)),
        )
    proposal = workers.propose(owner, WorkerSpec("tasks-helper", "Manage tasks", "Update tasks carefully", tuple(TASK_TOOLS), {}))
    worker_id = workers.create_from_approval(approve_fixture(context, proposal))
    run_req = replace(request.request, autonomy=AutonomyProfile.EXPANDED, requested_tool_names=tuple(TASK_TOOLS))
    work_req = replace(request, request=run_req, grant_id="grant", local_session_id=None)
    work_id = repo.create_work(owner, work_req, "resume:work")
    unassigned = WorkScope(owner.user_id, owner.workspace_id, work_id, 1, None, None, "grant")
    repo.assign(unassigned, worker_id)
    scope = WorkScope(owner.user_id, owner.workspace_id, work_id, 1, worker_id, 1, "grant")
    repo.transition(scope, WorkState.PROPOSED, WorkState.READY, {})
    VoiceSessionRepository(database_url=context[0]).ensure_schema()
    local = LocalToolAuthority(database_url=context[0], background_authority=authority)
    for name in TASK_TOOLS:
        local.set_grant(
            actor_user_id=owner.user_id, workspace_id=owner.workspace_id, tool_name=name,
            effect_class="read" if name in {"tasks_list", "tasks_read"} else "write",
            voice_enabled=False, background_enabled=True, user_id=owner.user_id,
        )
    catalog = ToolCatalog(authorizer=local.authorize, background_authorizer=local.authorize_background)
    tasks = TaskRepository(database_url=context[0])
    tasks.ensure_schema()
    actions = BackgroundActions(
        database_url=context[0],
        domains={"tasks": TaskActionDomain(repository=tasks)},
        authorizer=current_tool_authorizer(catalog=catalog, tool_authority=local, work_session=lambda _s: None),
    )
    bridge = BackgroundActionBridge(actions=actions, domains=actions._domains)
    register_tasks_tools(catalog=catalog, repository=tasks, background_actions=bridge)

    credentials = FakeCredentials()
    def make_executor(model_id: str = "gpt-5.4-mini"):
        return ResumableBackgroundExecutor(
            credentials=FakeCredentials(model_id=model_id),
            actions=actions,
            authority=authority,
            catalog=catalog,
            database_url=context[0],
            model_factory=lambda *_: OfflineTaskModel(task_text, force_complete_on_deny=force_complete_on_deny),
        )

    executor = make_executor()
    jobs = BackgroundJobs(database_url=context[0], executor=executor)
    executor.attach_jobs(jobs)
    jobs.ensure_schema()
    return {
        "repo": repo, "owner": owner, "scope": scope, "authority": authority, "workers": workers,
        "catalog": catalog, "tasks": tasks, "actions": actions, "jobs": jobs,
        "executor": executor, "make_executor": make_executor, "credentials": credentials,
    }


def _cleanup_queue(database_url: str) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_background_queue CASCADE")


def test_durable_job_pauses_for_domain_approval_releases_slot_and_resumes_once_in_fresh_executor(context):
    env = _build_env(context)
    try:
        scope = env["scope"]
        with psycopg.connect(context[0]) as connection:
            env["jobs"].enqueue(connection, scope.work_id)
        asyncio.run(env["jobs"].run_pending())

        with psycopg.connect(context[0]) as connection:
            work_state = connection.execute(
                "SELECT state FROM vault_private.vault_background_work WHERE work_id=%s", (scope.work_id,),
            ).fetchone()[0]
            active_slots = connection.execute(
                "SELECT count(*) FROM vault_private.vault_background_runs WHERE state IN ('running','reviewing','repairing')",
            ).fetchone()[0]
            run_row = connection.execute(
                "SELECT checkpoint_json, tool_calls, model_turns FROM vault_private.vault_background_runs WHERE work_id=%s",
                (scope.work_id,),
            ).fetchone()
            action_row = connection.execute(
                "SELECT action_id, action_hash, state FROM vault_private.vault_background_actions WHERE work_id=%s",
                (scope.work_id,),
            ).fetchone()

        assert work_state == "waiting_approval"
        assert active_slots == 0
        assert run_row[0] is not None and run_row[0]["pending_action_id"] == action_row[0]
        assert "sk-offline-test-secret" not in json.dumps(run_row[0])
        assert run_row[1] == 1 and run_row[2] == 1
        assert action_row[2] == "pending"
        assert [t.task_text for t in env["tasks"].list(user_id=scope.user_id, workspace_id=scope.workspace_id)] == []
        assert env["jobs"].resume_decided() == 0

        # The persisted decision is the only change made by the decision writer.
        principal = context[1]
        env["actions"].decide(
            principal,
            ApprovalDecision(
                action_row[0], action_row[1], "allow_once",
                principal.user_id, principal.workspace_id, "browser", principal.session_id, "dec-allow-1",
            ),
        )
        # Fresh executor instance resumes the saved checkpoint from PostgreSQL:
        fresh_executor = env["make_executor"]()
        fresh_jobs = BackgroundJobs(database_url=context[0], executor=fresh_executor)
        fresh_executor.attach_jobs(fresh_jobs)
        try:
            fresh_jobs.start()
            deadline = monotonic() + 10
            while monotonic() < deadline:
                state = env["repo"].get(env["owner"], scope.work_id)["state"]
                if state in ("completed", "failed", "unknown"):
                    break
                sleep(0.05)
        finally:
            fresh_jobs.stop()
        assert fresh_jobs.resume_decided() == 0

        with psycopg.connect(context[0]) as connection:
            work_state, result_json = connection.execute(
                "SELECT state, result_json FROM vault_private.vault_background_work WHERE work_id=%s",
                (scope.work_id,),
            ).fetchone()
            worker_status = connection.execute(
                "SELECT status FROM vault_private.vault_background_workers WHERE worker_id=%s",
                (scope.worker_id,),
            ).fetchone()[0]
            action_state = connection.execute(
                "SELECT state FROM vault_private.vault_background_actions WHERE action_id=%s",
                (action_row[0],),
            ).fetchone()[0]
            tool_calls, model_turns = connection.execute(
                "SELECT tool_calls, model_turns FROM vault_private.vault_background_runs WHERE work_id=%s",
                (scope.work_id,),
            ).fetchone()
            result_events = connection.execute(
                """SELECT count(*) FROM vault_private.vault_background_events
                   WHERE user_id=%s AND workspace_id=%s
                     AND source_kind='result' AND payload_json->>'work_id'=%s""",
                (scope.user_id, scope.workspace_id, scope.work_id),
            ).fetchone()[0]

        assert work_state == "completed"
        assert result_json["status"] == "complete"
        assert worker_status == "idle"
        assert action_state == "completed"
        assert result_events == 1
        assert tool_calls == 1 and model_turns == 2
        assert [t.task_text for t in env["tasks"].list(user_id=scope.user_id, workspace_id=scope.workspace_id)] == ["Ship Phase B"]
    finally:
        env["jobs"].stop()
        _cleanup_queue(context[0])


@pytest.mark.parametrize("mode,expected_code", [
    ("deny", "approval_denied"),
    ("expire", "approval_expired"),
])
def test_denied_or_expired_domain_action_resumes_without_effect_and_cannot_retry(context, mode, expected_code):
    env = _build_env(context, task_text="Never created", force_complete_on_deny=True)
    try:
        scope = env["scope"]
        with psycopg.connect(context[0]) as connection:
            env["jobs"].enqueue(connection, scope.work_id)
        asyncio.run(env["jobs"].run_pending())

        with psycopg.connect(context[0]) as connection:
            action_id, action_hash = connection.execute(
                "SELECT action_id, action_hash FROM vault_private.vault_background_actions WHERE work_id=%s",
                (scope.work_id,),
            ).fetchone()

        principal = context[1]
        if mode == "deny":
            env["actions"].decide(
                principal,
                ApprovalDecision(
                    action_id, action_hash, "deny",
                    principal.user_id, principal.workspace_id, "browser", principal.session_id, "dec-deny-1",
                ),
            )
        else:
            with psycopg.connect(context[0]) as connection:
                connection.execute(
                    "UPDATE vault_private.vault_background_actions SET expires_at=now()-interval '1 minute' WHERE action_id=%s",
                    (action_id,),
                )

        asyncio.run(env["jobs"].run_pending())

        with psycopg.connect(context[0]) as connection:
            work_state = connection.execute(
                "SELECT state FROM vault_private.vault_background_work WHERE work_id=%s", (scope.work_id,),
            ).fetchone()[0]
            failure_code = connection.execute(
                "SELECT failure_code FROM vault_private.vault_background_runs WHERE work_id=%s", (scope.work_id,),
            ).fetchone()[0]
            worker_status = connection.execute(
                "SELECT status FROM vault_private.vault_background_workers WHERE worker_id=%s", (scope.worker_id,),
            ).fetchone()[0]

        assert work_state == "failed"
        assert failure_code == expected_code
        assert worker_status == "idle"
        assert [t.task_text for t in env["tasks"].list(user_id=scope.user_id, workspace_id=scope.workspace_id)] == []
    finally:
        env["jobs"].stop()
        _cleanup_queue(context[0])


def test_revoked_grant_during_approval_wait_prevents_resumed_effect(context):
    env = _build_env(context, task_text="Revoked before resume")
    try:
        scope = env["scope"]
        with psycopg.connect(context[0]) as connection:
            env["jobs"].enqueue(connection, scope.work_id)
        asyncio.run(env["jobs"].run_pending())

        with psycopg.connect(context[0]) as connection:
            action_id, action_hash = connection.execute(
                "SELECT action_id, action_hash FROM vault_private.vault_background_actions WHERE work_id=%s",
                (scope.work_id,),
            ).fetchone()

        principal = context[1]
        env["actions"].decide(
            principal,
            ApprovalDecision(
                action_id, action_hash, "allow_once",
                principal.user_id, principal.workspace_id, "browser", principal.session_id, "dec-revoke-1",
            ),
        )
        env["repo"].transition(scope, WorkState.WAITING_APPROVAL, WorkState.READY, {})
        with psycopg.connect(context[0]) as connection:
            env["jobs"].enqueue(connection, scope.work_id)
        attempt = env["jobs"].claim(scope.work_id)
        assert attempt is not None

        # Revoke the standing execution grant after claim but before the resumed tool executes:
        env["authority"].revoke(principal, scope.grant_id)
        outcome = asyncio.run(env["executor"](attempt))
        assert outcome.state is WorkState.FAILED
        assert [t.task_text for t in env["tasks"].list(user_id=scope.user_id, workspace_id=scope.workspace_id)] == []
    finally:
        env["jobs"].stop()
        _cleanup_queue(context[0])


def test_worker_reset_during_approval_wait_clears_session_checkpoint_and_blocks_resume(context):
    env = _build_env(context, task_text="Reset before resume")
    try:
        scope = env["scope"]
        with psycopg.connect(context[0]) as connection:
            env["jobs"].enqueue(connection, scope.work_id)
        asyncio.run(env["jobs"].run_pending())

        with psycopg.connect(context[0]) as connection:
            saved_session_cp = connection.execute(
                "SELECT checkpoint_json FROM vault_private.vault_background_sessions WHERE work_id=%s",
                (scope.work_id,),
            ).fetchone()[0]
        assert saved_session_cp and saved_session_cp.get("pending_action_id")

        # Owner resets the specialist worker while the work is waiting for approval:
        new_gen = env["workers"].set_state(env["owner"], scope.worker_id, scope.worker_generation, "reset")
        assert new_gen == scope.worker_generation + 1

        with psycopg.connect(context[0]) as connection:
            cleared_session_cp = connection.execute(
                "SELECT checkpoint_json FROM vault_private.vault_background_sessions WHERE work_id=%s",
                (scope.work_id,),
            ).fetchone()[0]
            cleared_run_cp = connection.execute(
                "SELECT checkpoint_json FROM vault_private.vault_background_runs WHERE work_id=%s",
                (scope.work_id,),
            ).fetchone()[0]
            action_state = connection.execute(
                "SELECT state FROM vault_private.vault_background_actions WHERE work_id=%s",
                (scope.work_id,),
            ).fetchone()[0]
        assert cleared_session_cp is None
        assert cleared_run_cp is None
        assert action_state == "expired"
        assert [t.task_text for t in env["tasks"].list(user_id=scope.user_id, workspace_id=scope.workspace_id)] == []
    finally:
        env["jobs"].stop()
        _cleanup_queue(context[0])

