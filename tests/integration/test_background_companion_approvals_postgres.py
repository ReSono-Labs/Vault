"""Task 8 PostgreSQL integration tests: Companion approvals bridged to Link permission mechanism."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import threading
import time
from time import monotonic, sleep
from types import SimpleNamespace as NS

import psycopg
import pytest

from app.vault_runtime.background_agent.action_domains import TaskActionDomain
from app.vault_runtime.background_agent.actions import BackgroundActions
from app.vault_runtime.background_agent.authority import BackgroundAuthority, proposal_hash
from app.vault_runtime.background_agent.contracts import BackgroundRunRequest
from app.vault_runtime.background_agent.coordination_contracts import (
    ApprovalDecision,
    ExecutionOutcome,
    OwnerScope,
    WorkRequest,
    WorkState,
)
from app.vault_runtime.background_agent.coordination_repository import CoordinationRepository
from app.vault_runtime.background_agent.coordinator import BackgroundCoordinator
from app.vault_runtime.background_agent.owner_approvals import OwnerApprovals
from app.vault_runtime.background_agent.routines import BackgroundRoutines
from app.vault_runtime.conversation_tools.approval_gate import ApprovalGate, ApprovalText
from app.vault_runtime.notifications.repository import NotificationRepository
from app.vault_runtime.personal_data import PersonalDataRepository
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tasks.repository import TaskRepository
from app.vault_runtime.tasks_tools import register_tasks_tools
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult
from app.vault_runtime.voice.tools import LocalToolAuthority
from tests.support.genui_conversation import finish, grant
from tests.support.link_companion_chat import _chat, _pair
from tests.support.owner_approvals import _link


def _grant_standing(db_url: str, principal) -> str:
    repo = CoordinationRepository(database_url=db_url)
    repo.ensure_schema()
    auth = BackgroundAuthority(database_url=db_url)
    actions = BackgroundActions(database_url=db_url)
    owner = OwnerScope(principal.user_id, principal.workspace_id)
    proposal = {
        "purpose": "Background companion approval test",
        "tool_names": ["tasks_add", "tasks_confirm_action", "tasks_list"],
        "resource_policy": {},
    }
    prepared = actions.prepare(owner, "execution_grant", proposal, None, None)
    decision = ApprovalDecision(
        action_id=prepared.action_id,
        action_hash=prepared.action_hash,
        choice="allow_once",
        actor_user_id=principal.user_id,
        workspace_id=principal.workspace_id,
        channel="browser",
        channel_generation=principal.session_id,
        decision_id=f"dec-grant-{prepared.action_id}",
    )
    actions.decide(principal, decision)
    return auth.grant(principal, proposal, decision)


def test_companion_run_projects_pending_background_permission_even_after_reply_and_accepts_decision(mounted):
    m = mounted
    m.app._conversation_runtime.memories._embedder_factory = None
    grant(m)
    repo = CoordinationRepository(database_url=m.url)
    repo.ensure_schema()
    tasks_repo = TaskRepository(database_url=m.url)
    tasks_repo.ensure_schema()
    task_domain = TaskActionDomain(repository=tasks_repo)
    actions = BackgroundActions(
        database_url=m.url,
        domains={"tasks": task_domain},
        authorizer=lambda *_: True,
    )
    approvals = OwnerApprovals(database_url=m.url, actions=actions, poll_seconds=0.05)
    m.app._conversation_runtime.approvals = approvals
    m.app._conversation_runtime.background_actions = actions

    async def runner(**kwargs):
        return finish(kwargs, "I prepared the task and sent it for your approval.")

    m.app._conversation_runtime.runner = runner
    token, _pairing = _pair(m)
    session_id = _chat(m, "POST", "sessions", token, {}).payload["id"]
    run_id = _chat(m, "POST", f"sessions/{session_id}/messages", token, {"text": "Add task buy milk"}).payload["run_id"]

    # Wait for the conversational reply to finish in the store
    deadline = monotonic() + 10
    while monotonic() < deadline:
        st = m.app._conversation_runtime.store.status(m.principal, session_id, run_id)
        if st["state"] == "completed":
            break
        sleep(0.05)

    # Create background work linked to this chat turn (chat:{session_id}:{run_id}) in WAITING_APPROVAL
    grant_id = _grant_standing(m.url, m.principal)
    owner = OwnerScope(m.principal.user_id, m.principal.workspace_id)
    work_req = WorkRequest(
        request=BackgroundRunRequest(
            run_id=f"bg-{run_id}",
            objective="Add task buy milk",
            instruction_profile="default",
            result_schema={"type": "object"},
            success_criteria=("Task added",),
            completion_conditions=("Task added",),
            stop_conditions=("Failed",),
            original_request="Add task buy milk",
            verification_method="task_exists",
        ),
        grant_id=grant_id,
        local_session_id=None,
        destination={"kind": "chat", "conversation_id": session_id, "turn_id": run_id},
    )
    work_id = repo.create_work(owner, work_req, source_key=f"chat:{session_id}:{run_id}")
    wscope = repo.resolve_work_scope(work_id)
    domain_ref = task_domain.prepare(wscope, {"operation": "add", "payload": {"text": "Buy organic milk"}})
    version = task_domain.version(wscope, domain_ref)
    prepared = actions.prepare(wscope, "tasks", {"operation": "add", "payload": {"text": "Buy organic milk"}}, version, domain_ref)
    repo.transition(wscope, WorkState.PROPOSED, WorkState.WAITING_APPROVAL, {"pending_action_id": prepared.action_id})

    # Even though conversational turn text completed, GET /link-companion/chat/runs/{run_id} stays "running"
    # and projects permission_request + approval while the pending action is within its bounded window.
    run_status = _chat(m, "GET", f"runs/{run_id}", token)
    assert run_status.status_code == 200
    body = run_status.payload
    assert body["state"] == "running"
    assert "permission_request" in body
    perm = body["permission_request"]
    assert perm["action_id"] == prepared.action_id
    assert perm["action_hash"] == prepared.action_hash
    assert perm["title"] == prepared.title
    assert isinstance(perm["detail"], str) and perm["detail"]
    assert isinstance(perm["expires_at"], int) and perm["expires_at"] > int(time.time())

    # POST /link-companion/chat/runs/{run_id}/permission with exact {action_id, action_hash, choice, decision_id}
    dec_resp = _chat(
        m,
        "POST",
        f"runs/{run_id}/permission",
        token,
        {
            "action_id": prepared.action_id,
            "action_hash": prepared.action_hash,
            "choice": "allow_once",
            "decision_id": f"link-dec-{prepared.action_id}",
        },
    )
    assert dec_resp.status_code == 200
    assert dec_resp.payload["action_id"] == prepared.action_id
    assert dec_resp.payload["result"] == "approved"

    # Duplicate replay with same decision_id is idempotent
    dup_resp = _chat(
        m,
        "POST",
        f"runs/{run_id}/permission",
        token,
        {
            "action_id": prepared.action_id,
            "action_hash": prepared.action_hash,
            "choice": "allow_once",
            "decision_id": f"link-dec-{prepared.action_id}",
        },
    )
    assert dup_resp.status_code == 200
    assert dup_resp.payload["result"] == "approved"

    # Conflicting replay with deny is rejected
    conflict_resp = _chat(
        m,
        "POST",
        f"runs/{run_id}/permission",
        token,
        {
            "action_id": prepared.action_id,
            "action_hash": prepared.action_hash,
            "choice": "deny",
            "decision_id": f"link-dec-other-{prepared.action_id}",
        },
    )
    assert conflict_resp.status_code >= 400

    # Once decided, GET /link-companion/chat/runs/{run_id} finalizes as completed with text
    final_status = _chat(m, "GET", f"runs/{run_id}", token)
    assert final_status.status_code == 200
    assert final_status.payload["state"] == "completed"
    assert "permission_request" not in final_status.payload
    assert final_status.payload["text"] == "I prepared the task and sent it for your approval."


def test_companion_permission_rejects_mismatched_hash_expired_action_and_repaired_session(mounted):
    m = mounted
    m.app._conversation_runtime.memories._embedder_factory = None
    grant(m)
    repo = CoordinationRepository(database_url=m.url)
    repo.ensure_schema()
    tasks_repo = TaskRepository(database_url=m.url)
    tasks_repo.ensure_schema()
    task_domain = TaskActionDomain(repository=tasks_repo)
    actions = BackgroundActions(
        database_url=m.url,
        domains={"tasks": task_domain},
        authorizer=lambda *_: True,
    )
    approvals = OwnerApprovals(database_url=m.url, actions=actions, poll_seconds=0.05)
    m.app._conversation_runtime.approvals = approvals
    m.app._conversation_runtime.background_actions = actions

    async def runner(**kwargs):
        return finish(kwargs, "Waiting.")

    m.app._conversation_runtime.runner = runner
    token, _pairing = _pair(m)
    session_id = _chat(m, "POST", "sessions", token, {}).payload["id"]
    run_id = _chat(m, "POST", f"sessions/{session_id}/messages", token, {"text": "Add task"}).payload["run_id"]

    grant_id = _grant_standing(m.url, m.principal)
    owner = OwnerScope(m.principal.user_id, m.principal.workspace_id)
    work_req = WorkRequest(
        request=BackgroundRunRequest(
            run_id=f"bg-exp-{run_id}",
            objective="Add task",
            instruction_profile="default",
            result_schema={"type": "object"},
            success_criteria=("Task added",),
            completion_conditions=("Task added",),
            stop_conditions=("Failed",),
            original_request="Add task",
            verification_method="task_exists",
        ),
        grant_id=grant_id,
        local_session_id=None,
        destination={"kind": "chat", "conversation_id": session_id, "turn_id": run_id},
    )
    work_id = repo.create_work(owner, work_req, source_key=f"chat:{session_id}:{run_id}")
    wscope = repo.resolve_work_scope(work_id)
    domain_ref = task_domain.prepare(wscope, {"operation": "add", "payload": {"text": "Task 1"}})
    version = task_domain.version(wscope, domain_ref)
    prepared = actions.prepare(wscope, "tasks", {"operation": "add", "payload": {"text": "Task 1"}}, version, domain_ref)
    repo.transition(wscope, WorkState.PROPOSED, WorkState.WAITING_APPROVAL, {"pending_action_id": prepared.action_id})

    # 1. Mismatched action_hash is rejected and leaves action pending
    bad_hash = _chat(
        m,
        "POST",
        f"runs/{run_id}/permission",
        token,
        {
            "action_id": prepared.action_id,
            "action_hash": "0" * 64,
            "choice": "allow_once",
            "decision_id": "dec-bad-hash",
        },
    )
    assert bad_hash.status_code == 400
    with psycopg.connect(m.url) as conn:
        st = conn.execute(
            "SELECT state FROM vault_private.vault_background_actions WHERE action_id=%s",
            (prepared.action_id,),
        ).fetchone()[0]
    assert st == "pending"

    # 2. Expired action is rejected and never counts as allow
    with psycopg.connect(m.url) as conn:
        conn.execute(
            "UPDATE vault_private.vault_background_actions SET expires_at=now()-interval '5 seconds' WHERE action_id=%s",
            (prepared.action_id,),
        )
    expired_resp = _chat(
        m,
        "POST",
        f"runs/{run_id}/permission",
        token,
        {
            "action_id": prepared.action_id,
            "action_hash": prepared.action_hash,
            "choice": "allow_once",
            "decision_id": "dec-expired",
        },
    )
    assert expired_resp.status_code == 400

    # 3. Unpairing revokes the companion token immediately (401 not_paired)
    m.app._link_companion.unpair()
    unpaired_resp = _chat(
        m,
        "POST",
        f"runs/{run_id}/permission",
        token,
        {
            "action_id": prepared.action_id,
            "action_hash": prepared.action_hash,
            "choice": "allow_once",
            "decision_id": "dec-unpaired",
        },
    )
    assert unpaired_resp.status_code == 401


def test_secondary_user_action_never_projects_or_decides_on_owner_companion(mounted):
    m = mounted
    m.app._conversation_runtime.memories._embedder_factory = None
    grant(m)
    repo = CoordinationRepository(database_url=m.url)
    repo.ensure_schema()
    approvals = OwnerApprovals(database_url=m.url, poll_seconds=0.05)
    m.app._conversation_runtime.approvals = approvals

    async def runner(**kwargs):
        return finish(kwargs, "Owner reply.")

    m.app._conversation_runtime.runner = runner
    token, _pairing = _pair(m)
    session_id = _chat(m, "POST", "sessions", token, {}).payload["id"]
    run_id = _chat(m, "POST", f"sessions/{session_id}/messages", token, {"text": "Hello"}).payload["run_id"]

    # Provision a secondary user in the same workspace and create a pending interactive approval for them
    provisioned = m.app._identity_service.provision_user(
        actor=m.principal,
        username="second_user",
        password="SecondUserPass!123",
        password_mode="master_managed",
        age_group="adult",
        display_name="Second User",
        experience_style="balanced",
    )
    m.app._identity_service.add_member(
        principal=m.principal,
        workspace_id=m.principal.workspace_id,
        username="second_user",
    )
    second_tokens = m.app._identity_service.login(username="second_user", password="SecondUserPass!123")
    m.app._identity_service.switch_workspace(
        principal=second_tokens.principal,
        workspace_id=m.principal.workspace_id,
    )
    second_principal = m.app._identity_service.authenticate(session_token=second_tokens.session_token)

    from app.vault_runtime.background_agent.owner_approvals import ApprovalOrigin
    second_action = approvals.ask(
        second_principal,
        origin=ApprovalOrigin(tool_call_id="tc-sec-1", conversation_id="conv-sec-1", turn_id="turn-sec-1"),
        tool_name="email_send_pending",
        tool_arguments={"pendingRequestId": "req-sec-1"},
        title="Send secondary email",
        detail_lines=["To: sec@example.com"],
    )

    # Owner's Companion run never sees secondary user's action
    status = _chat(m, "GET", f"runs/{run_id}", token)
    assert "permission_request" not in status.payload
    assert "approval" not in status.payload

    # Owner's phone cannot decide secondary user's action via /permission or /approval
    forger_perm = _chat(
        m,
        "POST",
        f"runs/{run_id}/permission",
        token,
        {
            "action_id": second_action.action_id,
            "action_hash": second_action.action_hash,
            "choice": "allow_once",
            "decision_id": "forged-dec-1",
        },
    )
    assert forger_perm.status_code >= 400
    forger_app = _chat(
        m,
        "POST",
        f"runs/{run_id}/approval",
        token,
        {"id": second_action.action_id, "choice": "allow_once"},
    )
    assert forger_app.status_code >= 400

    # Secondary user retains browser fallback and decides their own approval in the browser
    second_headers = {
        "Cookie": f"resono_refresh={second_tokens.session_token}; resono_csrf={second_tokens.csrf_token}",
        "X-ReSono-CSRF": second_tokens.csrf_token,
    }
    listed = m.app.handle(method="GET", target="/approvals", headers=second_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.payload["items"]] == [second_action.action_id]
    decided = m.app.handle(
        method="POST",
        target=f"/approvals/{second_action.action_id}/decision",
        headers=second_headers,
        body=json.dumps({"choice": "allow_once"}).encode(),
    )
    assert decided.status_code == 200
    assert decided.payload["result"] == "approved"


def test_routine_out_of_turn_approval_falls_back_to_waiting_input_and_notification(context):
    db_url, principal, _second, *_ = context
    repo = CoordinationRepository(database_url=db_url)
    repo.ensure_schema()
    tasks_repo = TaskRepository(database_url=db_url)
    tasks_repo.ensure_schema()
    notifications = NotificationRepository(database_url=db_url)
    notifications.ensure_schema()

    grant_id = _grant_standing(db_url, principal)
    owner = OwnerScope(principal.user_id, principal.workspace_id)
    task_domain = TaskActionDomain(repository=tasks_repo)
    actions = BackgroundActions(
        database_url=db_url,
        domains={"tasks": task_domain},
        authorizer=lambda *_: True,
    )
    routines = BackgroundRoutines(database_url=db_url)
    now = datetime.now(timezone.utc) + timedelta(hours=2)
    routine_id = routines.create(
        principal,
        rule={"cron": "0 * * * *"},
        timezone="UTC",
        template={
            "objective": "Create daily summary task",
            "success_criteria": ["Task created"],
            "requested_tool_names": ["tasks_add"],
            "effect_bearing": False,
        },
        grant_id=grant_id,
    )
    assert routines.tick(now) == 1
    with psycopg.connect(db_url) as conn:
        work_id = conn.execute(
            "SELECT work_id FROM vault_private.vault_background_work WHERE user_id=%s AND workspace_id=%s AND routine_id=%s",
            (owner.user_id, owner.workspace_id, routine_id),
        ).fetchone()[0]

    class FakeRoutineExecutor:
        def __init__(self):
            self.calls = 0

        async def execute(self, scope, request, checkpoint, tools, cancel_requested):
            self.calls += 1
            if self.calls == 1:
                d_ref = task_domain.prepare(scope, {"operation": "add", "payload": {"text": "Routine task"}})
                ver = task_domain.version(scope, d_ref)
                prep = actions.prepare(scope, "tasks", {"operation": "add", "payload": {"text": "Routine task"}}, ver, d_ref)
                return ExecutionOutcome(
                    state=WorkState.WAITING_APPROVAL,
                    checkpoint={"step": 1},
                    pending_action_id=prep.action_id,
                )
            with psycopg.connect(db_url) as conn:
                act = conn.execute(
                    "SELECT action_id, action_hash FROM vault_private.vault_background_actions WHERE work_id=%s",
                    (scope.work_id,),
                ).fetchone()
            actions.execute(scope, act[0], act[1])
            return ExecutionOutcome(
                state=WorkState.COMPLETED,
                output={"status": "completed", "summary": "Routine task added."},
            )

    catalog = ToolCatalog(authorizer=lambda *_: True)
    coordinator = BackgroundCoordinator(
        database_url=db_url,
        executor=FakeRoutineExecutor(),
        catalog=catalog,
    )
    outcome = coordinator.dispatch_sync(work_id)
    # Out-of-turn routine with no active Companion chat operation reports waiting_input + notification
    assert outcome.state is WorkState.WAITING_INPUT
    assert outcome.pending_action_id is not None
    assert repo.get(owner, work_id)["state"] == WorkState.WAITING_INPUT.value
    active_notes = notifications.list_active(user_id=principal.user_id, workspace_id=principal.workspace_id)
    assert any(work_id in str(n) or outcome.pending_action_id in str(n) for n in active_notes)

    # User opens work in browser and approves the action
    with psycopg.connect(db_url) as conn:
        act_row = conn.execute(
            "SELECT action_id, action_hash FROM vault_private.vault_background_actions WHERE action_id=%s",
            (outcome.pending_action_id,),
        ).fetchone()
    actions.decide(
        principal,
        ApprovalDecision(
            action_id=act_row[0],
            action_hash=act_row[1],
            choice="allow_once",
            actor_user_id=principal.user_id,
            workspace_id=principal.workspace_id,
            channel="browser",
            channel_generation=principal.session_id,
            decision_id=f"browser-{act_row[0]}",
        ),
    )
    resumed = coordinator.dispatch_sync(work_id)
    assert resumed.state is WorkState.COMPLETED
    assert repo.get(owner, work_id)["state"] == WorkState.COMPLETED.value


def test_companion_voice_call_emits_approval_event_and_accepts_owner_decision(mounted):
    from app.vault_runtime.voice.companion import CompanionCall, _call_approval_wait

    m = mounted
    grant(m)
    repo = CoordinationRepository(database_url=m.url)
    repo.ensure_schema()
    approvals = OwnerApprovals(database_url=m.url, poll_seconds=0.05)
    m.app._conversation_runtime.approvals = approvals

    class FakeVoiceText:
        def describe(self, principal, name, arguments):
            return "Send an email", ["To: sam@example.com", "Subject: Call"], arguments.get("pendingRequestId")

    m.app._voice_tools._catalog.set_approval_gate(ApprovalGate(approvals=approvals, text=FakeVoiceText()))
    token, _pairing = _pair(m)
    companion_principal = m.app._link_companion_principal({"Authorization": f"Bearer {token}"})

    # Register an active CompanionCall on the companion voice service
    voice_service = m.app._companion_voice_service()
    call = CompanionCall(
        session_id="voice-call-approval-1",
        principal=companion_principal,
        call_id="realtime-call-1",
        token="fake-token",
        greeting=None,
        max_seconds=300,
        idle_seconds=300,
        protocol="openai-live-client",
    )
    sent_sideband = []

    async def fake_send(event):
        sent_sideband.append(event)

    loop = __import__("asyncio").new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()
    call.loop = loop
    call.sender = fake_send
    with voice_service._lock:
        voice_service._calls[call.session_id] = call

    # Run a gated tool call on a background thread with _call_approval_wait(call, approvals=approvals)
    ctx = ToolInvocationContext(
        agent=AgentKind.VOICE,
        user_id=companion_principal.user_id,
        workspace_id=companion_principal.workspace_id,
        local_session_id=companion_principal.session_id,
        voice_session_id=call.session_id,
        tool_call_id="call-voice-1",
    )
    results = []

    def invoke_tool():
        res = m.app._voice_tools._catalog.invoke(
            "email_send_pending",
            {"pendingRequestId": "req-v1"},
            context=ctx,
            approval_wait=_call_approval_wait(call, approvals=approvals),
        )
        results.append(res)

    worker = threading.Thread(target=invoke_tool)
    worker.start()

    try:
        # Poll call events via /link-companion/voice/sessions/{sid}/events until 'approval' event appears
        approval_event = None
        deadline = monotonic() + 5
        while monotonic() < deadline:
            ev_resp = m.app.handle(
                method="POST",
                target=f"/link-companion/voice/sessions/{call.session_id}/events",
                headers={"Authorization": f"Bearer {token}"},
                body=json.dumps({"after": 0, "wait": 0.1}).encode(),
            )
            assert ev_resp.status_code == 200
            for ev in ev_resp.payload.get("events", []):
                if ev.get("type") == "approval":
                    approval_event = ev
                    break
            if approval_event is not None:
                break
            sleep(0.05)

        assert approval_event is not None
        q = approval_event["approval"]
        assert q["title"] == "Send an email"
        assert q["choices"] == ["allow_once", "deny"]

        # Answer via POST /link-companion/voice/sessions/{sid}/approval
        ans_resp = m.app.handle(
            method="POST",
            target=f"/link-companion/voice/sessions/{call.session_id}/approval",
            headers={"Authorization": f"Bearer {token}"},
            body=json.dumps({"id": q["id"], "choice": "allow_once"}).encode(),
        )
        assert ans_resp.status_code == 200
        assert ans_resp.payload["result"] == "approved"
        worker.join(timeout=5)
        assert len(results) == 1
    finally:
        call.closing = "ended"
        with call.condition:
            call.closed = True
        voice_service._calls.pop(call.session_id, None)
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=2)
        loop.close()


def test_tasks_memory_commands_and_ask_mode_in_approval_gate(context):
    db_url, owner, _second, *_ = context
    repo = CoordinationRepository(database_url=db_url)
    repo.ensure_schema()
    tasks_repo = TaskRepository(database_url=db_url)
    tasks_repo.ensure_schema()
    records = PersonalDataRepository(database_url=db_url)
    records.ensure_schema()

    from app.vault_runtime.voice.schema import ensure_voice_schema
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        ensure_voice_schema(cur)

    tool_auth = LocalToolAuthority(database_url=db_url)
    catalog = ToolCatalog(authorizer=tool_auth.authorize)
    register_tasks_tools(catalog=catalog, repository=tasks_repo)

    # Register a custom tool that will be configured with approval_mode='ask'
    custom_calls = []
    catalog.register(
        ToolDefinition(
            tool_id="builtin.custom-delete.v1",
            name="custom_delete",
            description="Delete an item",
            input_schema={
                "type": "object",
                "properties": {"itemId": {"type": "string"}},
                "required": ["itemId"],
                "additionalProperties": False,
            },
            handler=lambda _ctx, args: (custom_calls.append(dict(args)) or ToolInvocationResult("deleted")),
            effect_class="delete",
            audiences=frozenset({AgentKind.VOICE}),
        )
    )
    tool_auth.ensure_builtin_grants(
        user_id=owner.user_id,
        workspace_id=owner.workspace_id,
        definitions=catalog.definitions_for(AgentKind.VOICE, user_id=owner.user_id, workspace_id=owner.workspace_id),
    )
    tool_auth.set_grant(
        actor_user_id=owner.user_id,
        workspace_id=owner.workspace_id,
        tool_name="custom_delete",
        effect_class="delete",
        voice_enabled=True,
        background_enabled=False,
        approval_mode="ask",
    )

    approvals = OwnerApprovals(database_url=db_url, poll_seconds=0.05)
    text = ApprovalText(database_url=db_url, records=records)
    gate = ApprovalGate(approvals=approvals, text=text, tool_authority=tool_auth)
    catalog.set_approval_gate(gate)

    # 1. Prepare a task in Chat (where utterance_id is 0) and confirm it through ApprovalGate
    chat_ctx = ToolInvocationContext(
        agent=AgentKind.VOICE,
        user_id=owner.user_id,
        workspace_id=owner.workspace_id,
        local_session_id=owner.session_id,
        conversation_id="conv-task-1",
        turn_id="turn-task-1",
        tool_call_id="call-task-prep",
    )
    prep_res = catalog.invoke("tasks_add", {"text": "Call the dentist"}, context=chat_ctx)
    assert not prep_res.is_error
    prep_payload = json.loads(prep_res.text)

    def approve_turn(turn_id: str):
        for _ in range(100):
            shown = approvals.pending(owner, turn_id=turn_id)
            if shown:
                approvals.answer(owner, shown["id"], "allow_once", channel="browser")
                return
            time.sleep(0.02)

    t1 = threading.Thread(target=approve_turn, args=("turn-task-1",))
    t1.start()
    confirm_ctx = ToolInvocationContext(
        agent=AgentKind.VOICE,
        user_id=owner.user_id,
        workspace_id=owner.workspace_id,
        local_session_id=owner.session_id,
        conversation_id="conv-task-1",
        turn_id="turn-task-1",
        tool_call_id="call-task-confirm",
    )
    confirm_res = catalog.invoke(
        "tasks_confirm_action",
        {"actionId": prep_payload["actionId"], "contentHash": prep_payload["contentHash"]},
        context=confirm_ctx,
    )
    t1.join(timeout=5)
    assert not confirm_res.is_error, confirm_res.text
    assert json.loads(confirm_res.text)["state"] == "completed"

    # 2. Invoke custom_delete configured with approval_mode='ask'
    t2 = threading.Thread(target=approve_turn, args=("turn-ask-1",))
    t2.start()
    ask_ctx = ToolInvocationContext(
        agent=AgentKind.VOICE,
        user_id=owner.user_id,
        workspace_id=owner.workspace_id,
        local_session_id=owner.session_id,
        conversation_id="conv-task-1",
        turn_id="turn-ask-1",
        tool_call_id="call-ask-1",
    )
    ask_res = catalog.invoke("custom_delete", {"itemId": "item-42"}, context=ask_ctx)
    t2.join(timeout=5)
    assert not ask_res.is_error, ask_res.text
    assert ask_res.text == "deleted"
    assert custom_calls == [{"itemId": "item-42"}]


@pytest.mark.flags_off(reason="installs its own coordinator stack with a recording executor")
def test_coordinator_first_routine_uses_one_link_permission_for_grant_and_schedule(mounted):
    from app.vault_runtime.background_agent.coordinator_tools import register_background_conversation_tools
    from app.vault_runtime.background_agent.results import BackgroundResults
    from app.vault_runtime.local_identity.repository import LocalIdentityRepository
    from tests.support.background_workers import _RecordingExecutor
    from tests.support.genui_conversation import call
    from tests.support.link_companion_chat import _run

    m = mounted
    runtime = m.app._conversation_runtime
    runtime.memories._embedder_factory = None
    CoordinationRepository(database_url=m.url).ensure_schema()
    executor = _RecordingExecutor()
    coordinator = BackgroundCoordinator(
        database_url=m.url, catalog=runtime.catalog, executor=executor,
        results=BackgroundResults(database_url=m.url),
    )
    coordinator.jobs.ensure_schema()
    runtime.background_coordinator = coordinator
    runtime.background_actions = BackgroundActions(database_url=m.url)
    register_background_conversation_tools(
        catalog=runtime.catalog, database_url=m.url, coordinator=runtime.background_coordinator,
        resolve_principal=LocalIdentityRepository(database_url=m.url).resolve_review_principal,
    )
    issued = []

    async def runner(**kwargs):
        assert kwargs["instructions"].startswith("You are the Vault coordinator")
        # The owner's own schedules, and a specialist routine the owner asks for, are saved at once.
        specialist, raw_specialist = call(kwargs, "specialist-proposal", "specialist-call", "background_propose_specialist", {
            "role_key": "weekday-briefer", "purpose": "Prepare weekday briefs",
            "instructions": "Summarize the day", "tool_names": [],
        })
        issued.append(json.loads(await specialist.on_invoke_tool(NS(tool_call_id="specialist-call"), raw_specialist)))
        tool, raw = call(kwargs, "routine-proposal", "routine-call", "background_propose_routine", {
            "objective": "Prepare a weekday brief", "cron": "0 8 * * 1-5", "role_key": "weekday-briefer",
            "timezone": "America/New_York", "tool_names": [],
        })
        issued.append(json.loads(await tool.on_invoke_tool(NS(tool_call_id="routine-call"), raw)))
        return finish(kwargs, "Please review the approval card.")

    runtime.runner = runner
    token, _ = _pair(m)
    conversation = _chat(m, "POST", "sessions", token, {}).payload["id"]
    # Vault (2026-11-19): a specialist routine the owner asks for is saved at once, with no approval.
    sent = _chat(m, "POST", f"sessions/{conversation}/messages", token, {"text": "Set up the weekday routine"})
    assert sent.status_code == 202, sent.payload
    final = _run(m, token, sent.payload["run_id"])
    assert final["state"] == "completed" and not final.get("permission_request"), final
    assert issued[1]["structuredContent"]["status"] == "scheduled", issued
    with psycopg.connect(m.url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM vault_private.vault_background_actions WHERE kind='routine_create'").fetchone() == (0,)

    assert all(not result["isError"] for result in issued)
    with psycopg.connect(m.url) as connection:
        assert connection.execute(
            """SELECT status, timezone, template_json->'destination'->>'conversation_id'
               FROM vault_private.vault_background_routines""",
        ).fetchall() == [("active", "America/New_York", conversation)]

    routines = BackgroundRoutines(database_url=m.url, jobs=coordinator.jobs)
    with psycopg.connect(m.url) as connection:
        due, = connection.execute("SELECT next_due_at FROM vault_private.vault_background_routines").fetchone()
    assert routines.tick(due) == 1
    assert routines.tick(due) == 0
    with psycopg.connect(m.url) as connection:
        work_id, = connection.execute(
            "SELECT work_id FROM vault_private.vault_background_work WHERE routine_id IS NOT NULL",
        ).fetchone()
    assert coordinator.dispatch_sync(work_id).state is WorkState.COMPLETED
    assert len(executor.calls) == 1
    history = _chat(m, "GET", f"sessions/{conversation}/messages", token)
    assert history.status_code == 200, history.payload
    result = history.payload["messages"][-1]
    assert result["role"] == "assistant"
    assert result["text"] == "Completed Prepare a weekday brief"

    from app.vault_runtime.background_agent.coordination_contracts import WorkerSpec
    from app.vault_runtime.background_agent.worker_repository import WorkerRepository

    scope = OwnerScope(m.principal.user_id, m.principal.workspace_id)
    workers = WorkerRepository(database_url=m.url)
    proposed = workers.propose(scope, WorkerSpec("briefing", "Prepare briefs", "Summarize facts", (), {}))
    decision = ApprovalDecision(
        proposed.action_id, proposed.action_hash, "allow_once", scope.user_id, scope.workspace_id,
        "browser", m.principal.session_id, "create-briefing-for-memory-test",
    )
    runtime.background_actions.decide(m.principal, decision)
    worker_id = workers.create_from_approval(decision)

    pending = workers.propose_memory_lookup(scope, "briefing", conversation_id="web-chat", turn_id="web-turn")
    assert pending is not None

    second_proposal = workers.propose(
        scope, WorkerSpec("another", "Track another project", "Summarize progress", (), {}),
        origin_conversation_id="web-chat", origin_turn_id="web-second",
    )

    async def memory_runner(**kwargs):
        inspect, args = call(kwargs, "pending-review", "pending-list", "background_inspect", {})
        listing = json.loads(await inspect.on_invoke_tool(NS(tool_call_id="pending-list"), args))
        assert {item["action_id"] for item in listing["structuredContent"]["pendingApprovals"]} == {
            pending.action_id, second_proposal.action_id,
        }
        tool, raw = call(kwargs, "memory-review", "memory-call", "background_review_approval", {})
        response = json.loads(await tool.on_invoke_tool(NS(tool_call_id="memory-call"), raw))
        assert not response["isError"], response
        return finish(kwargs, "Please review memory access.")

    runtime.runner = memory_runner
    queued = _chat(m, "POST", f"sessions/{conversation}/messages", token, {
        "text": "Review pending approvals.",
    })
    assert queued.status_code == 202, queued.payload
    turn = queued.payload["run_id"]
    deadline = monotonic() + 12
    permission = None
    while monotonic() < deadline:
        status = _chat(m, "GET", f"runs/{turn}", token).payload
        permission = status.get("permission_request")
        if permission or status["state"] == "failed":
            break
        sleep(.05)
    assert permission and permission["action_id"] == pending.action_id, status
    assert workers.get(scope, worker_id).tool_names == ()
    approved = _chat(m, "POST", f"runs/{turn}/permission", token, {
        "action_id": permission["action_id"], "action_hash": permission["action_hash"],
        "choice": "allow_once", "decision_id": "link-specialist-memory",
    })
    assert approved.status_code == 200, approved.payload
    assert workers.get(scope, worker_id).tool_names == ("memory_lookup",)

    next_status = _chat(m, "GET", f"runs/{turn}", token).payload
    assert next_status["state"] == "running"
    second = next_status["permission_request"]
    assert second["action_id"] == second_proposal.action_id
    denied = _chat(m, "POST", f"runs/{turn}/permission", token, {
        "action_id": second["action_id"], "action_hash": second["action_hash"],
        "choice": "deny", "decision_id": "link-deny-second-proposal",
    })
    assert denied.status_code == 200, denied.payload
    assert _run(m, token, turn)["state"] == "completed"

    expired = routines.propose(
        m.principal, rule={"kind": "cron", "cron": "30 9 * * 1-5"},
        timezone="America/New_York", template={"request": {"objective": "Morning review"}},
        grant_id=None, origin_conversation_id=conversation, origin_turn_id="expired-schedule-turn",
    )
    with psycopg.connect(m.url) as connection:
        connection.execute(
            "UPDATE vault_private.vault_background_actions SET expires_at=now()-interval '1 second' WHERE action_id=%s",
            (expired.action_id,),
        )
    reopen = runtime.catalog.definition("background_reopen_routines")
    context = ToolInvocationContext(
        agent=AgentKind.VOICE, user_id=scope.user_id, workspace_id=scope.workspace_id,
        tool_call_id="reopen-test", local_session_id=m.principal.session_id,
        conversation_id=conversation, turn_id="reopen-turn",
    )
    result = reopen.handler(context, {})
    assert not result.is_error
    fresh_id = result.structured_content["items"][0]["actionId"]
    assert fresh_id != expired.action_id
    with psycopg.connect(m.url) as connection:
        assert connection.execute(
            """SELECT state,action_hash,origin_json->>'conversation_id'
               FROM vault_private.vault_background_actions WHERE action_id=%s""",
            (fresh_id,),
        ).fetchone() == ("pending", expired.action_hash, conversation)

    schedule = runtime.catalog.definition("background_propose_routine")
    reminder = schedule.handler(context, {
        "objective": "Call Dana", "delay_minutes": 10, "reminder": True,
        "timezone": "America/New_York", "tool_names": [],
    })
    assert not reminder.is_error, reminder.text
    # A tool-free reminder is saved immediately (2026-11-18): it only posts its own text here.
    assert reminder.structured_content["status"] == "scheduled"
    reminder_id = reminder.structured_content["routineId"]
    with psycopg.connect(m.url) as connection:
        due, = connection.execute(
            "SELECT next_due_at FROM vault_private.vault_background_routines WHERE routine_id=%s", (reminder_id,),
        ).fetchone()
    routines.tick(due)
    assert routines.tick(due) == 0
    with psycopg.connect(m.url) as connection:
        reminder_work, = connection.execute(
            "SELECT work_id FROM vault_private.vault_background_work WHERE routine_id=%s", (reminder_id,),
        ).fetchone()
    assert coordinator.dispatch_sync(reminder_work).state is WorkState.COMPLETED
    assert len(executor.calls) == 1
    history = _chat(m, "GET", f"sessions/{conversation}/messages", token).payload
    assert [entry["text"] for entry in history["messages"]].count("Call Dana") == 1

    manage = runtime.catalog.definition("background_manage_routine")
    with psycopg.connect(m.url) as connection:
        recurring_id, = connection.execute(
            "SELECT routine_id FROM vault_private.vault_background_routines WHERE status='active'"
        ).fetchone()
    with psycopg.connect(m.url) as connection:
        original_due, = connection.execute(
            "SELECT next_due_at FROM vault_private.vault_background_routines WHERE routine_id=%s", (recurring_id,),
        ).fetchone()
    with pytest.raises(RuntimeError, match="queue unavailable"):
        def fail_enqueue(connection, work_id):
            raise RuntimeError("queue unavailable")

        routines.run_now(m.principal, recurring_id, call_key="failed-dispatch", jobs=NS(enqueue=fail_enqueue))
    with psycopg.connect(m.url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM vault_private.vault_background_work WHERE source_key=%s",
            (f"routine-manual:{recurring_id}:failed-dispatch",),
        ).fetchone() == (0,)
    manual = manage.handler(context, {"routine_id": recurring_id, "operation": "run_now"})
    assert not manual.is_error, manual.text
    manual_id = manual.structured_content["workId"]
    assert manage.handler(context, {"routine_id": recurring_id, "operation": "run_now"}).structured_content["workId"] == manual_id
    assert coordinator.dispatch_sync(manual_id).state is WorkState.COMPLETED
    history = _chat(m, "GET", f"sessions/{conversation}/messages", token).payload
    assert history["messages"][-1]["text"] == "Completed Prepare a weekday brief"
    with psycopg.connect(m.url) as connection:
        assert connection.execute(
            "SELECT next_due_at FROM vault_private.vault_background_routines WHERE routine_id=%s", (recurring_id,),
        ).fetchone() == (original_due,)
    for operation, expected in (("pause", "paused"), ("reschedule", "paused"),
                                ("resume", "active"), ("cancel", "deleted")):
        arguments = {"routine_id": recurring_id, "operation": operation}
        if operation == "reschedule":
            arguments.update(cron="0 10 * * 1-5", timezone="America/New_York")
        updated = manage.handler(context, arguments)
        assert not updated.is_error, updated.text
        with psycopg.connect(m.url) as connection:
            status, cron = connection.execute(
                "SELECT status,rule_json->>'cron' FROM vault_private.vault_background_routines WHERE routine_id=%s",
                (recurring_id,),
            ).fetchone()
        assert status == expected
        if operation != "pause":
            assert cron == "0 10 * * 1-5"
