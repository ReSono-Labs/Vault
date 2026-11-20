"""Mounted Vault runtime integration tests for Background Assistant (Steps 1 & 2)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from types import SimpleNamespace

import psycopg
import pytest

from app.vault_runtime.background_agent.actions import BackgroundActions
from app.vault_runtime.background_agent.contracts import (
    AutonomyProfile,
    BackgroundRunRequest,
    ExecutionRecipe,
)
from app.vault_runtime.background_agent.coordination_contracts import (
    OwnerScope,
    WorkerSpec,
    WorkRequest,
    WorkState,
)
from app.vault_runtime.background_agent.coordinator import CoordinatorObservationDecision
from app.vault_runtime.background_agent.output_contract import background_output_schema
from app.vault_runtime.background_agent.routines import BackgroundRoutines
from app.vault_runtime.composition import build_local_app
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.definitions import ToolInvocationContext
from tests.support.background_resume import OfflineTaskModel, TASK_TOOLS
from tests.support.conversation_identity import require_test_database
from tests.support.genui_conversation import finish
from tests.support.link_companion_chat import _chat, _pair
from tests.support.background_mounted_runtime import (
    _reset_schemas, _api, _boot_config, _onboard_owner, _wait_until,
)


def _grant_background_tools(app, principal) -> None:
    app._builtin_plugins.update(
        account_id=principal.user_id,
        workspace_id=principal.workspace_id,
        plugin_key="tasks",
        enabled=True,
    )
    authority = app._voice_tools._authority
    for name in TASK_TOOLS:
        authority.set_grant(
            actor_user_id=principal.user_id,
            workspace_id=principal.workspace_id,
            tool_name=name,
            effect_class="read" if name in {"tasks_list", "tasks_read"} else "write",
            voice_enabled=True,
            background_enabled=True,
            user_id=principal.user_id,
        )
    for name, effect in (("goal_start", "write"), ("goal_status", "read"), ("goal_cancel", "write")):
        authority.set_grant(
            actor_user_id=principal.user_id,
            workspace_id=principal.workspace_id,
            tool_name=name,
            effect_class=effect,
            voice_enabled=True,
            background_enabled=False,
            user_id=principal.user_id,
        )


def test_mounted_app_specialist_proposal_link_approval_and_restart_resume_once(tmp_path, monkeypatch):
    url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Exact isolated database required")
    _reset_schemas(url)

    monkeypatch.setattr("app.vault_runtime.memory.service.MemoryService.ensure_vectors", lambda *a, **k: (0, 0))
    monkeypatch.setattr("app.vault_runtime.agent_network.service.A2AService.start", lambda *_: None)
    monkeypatch.setattr("app.vault_runtime.agent_network.inbound.A2AInboundHttpServer.start", lambda *_: None)
    monkeypatch.setattr("app.vault_runtime.extensions.mcp_runtime.McpRuntimeSupervisor.restore_on_boot", lambda *_: None)
    async def _noop_aclose():
        return None

    monkeypatch.setattr(
        "app.vault_runtime.background_agent.executor.build_openai_sdk_provider",
        lambda **_: (None, SimpleNamespace(get_model=lambda *_: OfflineTaskModel("Ship Mounted Vault"), aclose=_noop_aclose)),
    )

    config = _boot_config(tmp_path, url)
    app1 = build_local_app(config)
    app2 = None
    try:
        health = _api(app1, "GET", "/background/health", {"Authorization": "Bearer local-test"})
        # Authenticate owner so we can inspect /background/health with session cookie too
        principal, headers = _onboard_owner(app1)
        health = _api(app1, "GET", "/background/health", headers)
        assert health.status_code == 200
        assert health.payload["durable"]["state"] == "running"

        app1._conversation_runtime.memories._embedder_factory = None
        app1._conversation_runtime.title_runner = None
        _grant_background_tools(app1, principal)

        async def chat_runner(**kwargs):
            return finish(kwargs, "Working on that in the background.")

        app1._conversation_runtime.runner = chat_runner

        # Pair Link Companion on mounted app1
        holder = SimpleNamespace(
            app=app1,
            headers=headers,
            principal=principal,
            url=url,
            post=lambda path, payload, hdrs: _api(app1, "POST", path, hdrs, payload),
        )
        link_token, _pairing = _pair(holder)

        # Enable background coordination observation for owner
        pref_res = _api(app1, "POST", "/background/preferences", headers, {"enabled": True})
        assert pref_res.status_code == 200 and pref_res.payload["enabled"] is True

        # Propose standing execution grant and approve it through Link Companion!
        owner_scope = OwnerScope(principal.user_id, principal.workspace_id)
        actions: BackgroundActions = app1._conversation_runtime.background_actions
        grant_proposal = {
            "purpose": "Mounted background task helper",
            "tool_names": list(TASK_TOOLS),
            "resource_policy": {},
        }
        prepared_grant = actions.prepare(owner_scope, "execution_grant", grant_proposal, None, None)

        session_id = _chat(holder, "POST", "sessions", link_token, {}).payload["id"]
        grant_turn_id = _chat(
            holder, "POST", f"sessions/{session_id}/messages", link_token, {"text": "Review standing grant"}
        ).payload["run_id"]
        _wait_until(
            lambda: app1._conversation_runtime.store.status(principal, session_id, grant_turn_id)["state"] == "completed"
        )
        poll_grant = _chat(holder, "GET", f"runs/{grant_turn_id}", link_token)
        assert poll_grant.status_code == 200
        assert poll_grant.payload["state"] == "running"
        assert poll_grant.payload["permission_request"]["action_id"] == prepared_grant.action_id

        dec_grant = _chat(
            holder,
            "POST",
            f"runs/{grant_turn_id}/permission",
            link_token,
            {
                "action_id": prepared_grant.action_id,
                "action_hash": prepared_grant.action_hash,
                "choice": "allow_once",
                "decision_id": f"dec-grant-{prepared_grant.action_id}",
            },
        )
        assert dec_grant.status_code == 200 and dec_grant.payload["result"] == "approved"

        with psycopg.connect(url) as conn:
            grant_id = conn.execute(
                "SELECT grant_id FROM vault_private.vault_background_execution_grants WHERE user_id=%s AND workspace_id=%s",
                (principal.user_id, principal.workspace_id),
            ).fetchone()[0]

        # Wire coordinator triage so the next Chat turn proposes a specialist ("tasks_specialist") + work item
        specialist_spec = WorkerSpec(
            role_key="tasks_specialist",
            purpose="Prepare and confirm owner tasks",
            instructions="Prepare the requested task and confirm after owner approval.",
            tool_names=tuple(TASK_TOOLS),
            resource_policy={},
        )

        def triage(_scope, source_kind, _source_id, event_payload, _scratchpad):
            if source_kind != "conversation_turn" or "Ship Mounted Vault" not in str(event_payload.get("input_text", "")):
                return None
            t_id = str(event_payload["turn_id"])
            c_id = str(event_payload["conversation_id"])
            req = BackgroundRunRequest(
                run_id=f"bg-run-{t_id}",
                objective="Add task Ship Mounted Vault",
                instruction_profile="default",
                success_criteria=("Task Ship Mounted Vault added",),
                result_schema=background_output_schema(),
                recipe=ExecutionRecipe.SELF_REVIEW,
                autonomy=AutonomyProfile.EXPANDED,
                original_request="Add task Ship Mounted Vault",
                verification_method="Check Tasks repository",
                completion_conditions=("Task added",),
                requested_tool_names=tuple(TASK_TOOLS),
            )
            return CoordinatorObservationDecision(
                action="propose_worker",
                reason="Needs tasks_specialist role",
                work_request=WorkRequest(
                    request=req,
                    grant_id=grant_id,
                    local_session_id=None,
                    destination={"kind": "chat", "conversation_id": c_id, "turn_id": t_id, "role_key": "tasks_specialist"},
                ),
                worker_spec=specialist_spec,
                role_key="tasks_specialist",
            )

        app1._conversation_runtime.background_coordinator._triage_evaluator = triage

        work_turn_id = _chat(
            holder,
            "POST",
            f"sessions/{session_id}/messages",
            link_token,
            {"text": "Please Ship Mounted Vault in the background"},
        ).payload["run_id"]

        # 1) Turn finishes text, Link run projects specialist worker_create permission_request!
        worker_perm = _wait_until(
            lambda: (_chat(holder, "GET", f"runs/{work_turn_id}", link_token).payload or {}).get("permission_request")
        )
        assert "tasks_specialist" in worker_perm["title"]

        # Approve specialist creation in Link -> materializes worker AND auto-dispatches waiting work!
        dec_worker = _chat(
            holder,
            "POST",
            f"runs/{work_turn_id}/permission",
            link_token,
            {
                "action_id": worker_perm["action_id"],
                "action_hash": worker_perm["action_hash"],
                "choice": "allow_once",
                "decision_id": f"dec-worker-{worker_perm['action_id']}",
            },
        )
        assert dec_worker.status_code == 200 and dec_worker.payload["result"] == "approved"

        # 2) Specialist runs, calls tasks_add("Ship Mounted Vault"), and parks at checkpoint (waiting_approval),
        #    surfacing the tasks prepared action on the SAME Link Companion run!
        def _task_perm():
            p = (_chat(holder, "GET", f"runs/{work_turn_id}", link_token).payload or {}).get("permission_request")
            return p if p and p["action_id"] != worker_perm["action_id"] else None

        task_perm = _wait_until(_task_perm, timeout=15.0)
        assert "Ship Mounted Vault" in task_perm["detail"]

        # Verify zero tasks exist before approval + restart
        assert list(app1._tasks.list(user_id=principal.user_id, workspace_id=principal.workspace_id)) == []

        # Stop durable worker on app1 BEFORE recording the Link decision so decision is recorded while worker is down,
        # then close app1 completely and restart a brand-new app2 to prove durable restart recovery!
        app1._conversation_runtime.background_coordinator.jobs.stop()
        dec_task = _chat(
            holder,
            "POST",
            f"runs/{work_turn_id}/permission",
            link_token,
            {
                "action_id": task_perm["action_id"],
                "action_hash": task_perm["action_hash"],
                "choice": "allow_once",
                "decision_id": f"dec-task-{task_perm['action_id']}",
            },
        )
        assert dec_task.status_code == 200 and dec_task.payload["result"] == "approved"
        app1.close()

        # Boot brand-new mounted app2: startup resume_decided() wakes the parked checkpoint automatically!
        app2 = build_local_app(config)
        app2._conversation_runtime.memories._embedder_factory = None
        app2._conversation_runtime.title_runner = None

        created_tasks = _wait_until(
            lambda: app2._tasks.list(user_id=principal.user_id, workspace_id=principal.workspace_id),
            timeout=15.0,
        )
        assert [t.task_text for t in created_tasks] == ["Ship Mounted Vault"]

        # Verify work item completed with ONE result and ONE delivery
        work_resp = _api(app2, "GET", "/background/work", headers)
        assert work_resp.status_code == 200
        assert len(work_resp.payload["items"]) == 1
        item = work_resp.payload["items"][0]
        _wait_until(
            lambda: _api(app2, "GET", f"/background/work/{item['workId']}", headers).payload.get("state") == "completed",
            timeout=10.0,
        )
        # The result is delivered right after the work completes (deliver_outcome runs after commit).
        detail = _wait_until(
            lambda: (lambda d: d if d.get("deliveries") else None)(
                _api(app2, "GET", f"/background/work/{item['workId']}", headers).payload),
            timeout=10.0,
        )
        assert detail["statusLabel"] == "done"
        assert detail["roleKey"] == "tasks_specialist"
        assert len(detail["deliveries"]) == 1
    finally:
        try:
            app1.close()
        except Exception:
            pass
        if app2 is not None:
            app2.close()


def test_mounted_goal_tools_sync_intakes_out_of_turn_parking_and_secondary_user_isolation(tmp_path, monkeypatch):
    url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Exact isolated database required")
    _reset_schemas(url)

    monkeypatch.setattr("app.vault_runtime.memory.service.MemoryService.ensure_vectors", lambda *a, **k: (0, 0))
    monkeypatch.setattr("app.vault_runtime.agent_network.service.A2AService.start", lambda *_: None)
    monkeypatch.setattr("app.vault_runtime.agent_network.inbound.A2AInboundHttpServer.start", lambda *_: None)
    monkeypatch.setattr("app.vault_runtime.extensions.mcp_runtime.McpRuntimeSupervisor.restore_on_boot", lambda *_: None)
    async def _noop_aclose():
        return None

    monkeypatch.setattr(
        "app.vault_runtime.background_agent.executor.build_openai_sdk_provider",
        lambda **_: (None, SimpleNamespace(get_model=lambda *_: OfflineTaskModel("Routine Task"), aclose=_noop_aclose)),
    )

    config = _boot_config(tmp_path, url)
    app = build_local_app(config)
    try:
        owner, headers = _onboard_owner(app)
        app._conversation_runtime.memories._embedder_factory = None
        app._conversation_runtime.title_runner = None
        _grant_background_tools(app, owner)

        async def chat_runner(**kwargs):
            return finish(kwargs, "Done.")

        app._conversation_runtime.runner = chat_runner
        holder = SimpleNamespace(
            app=app,
            headers=headers,
            principal=owner,
            url=url,
            post=lambda path, payload, hdrs: _api(app, "POST", path, hdrs, payload),
        )
        link_token, _pairing = _pair(holder)

        # 1. Voice no longer starts Background Agent goals (2026-11-18): it hands requests to the chat
        #    coordinator (tests/integration/test_coordinator_wake_postgres.py covers the hand-off).
        app._conversation_runtime.background_coordinator.jobs.stop()
        assert app._voice_tools._catalog.definition("coordinator_hand_off") is not None
        assert app._voice_tools._catalog.definition("goal_start") is None

        # 2. Verify mail_sync and calendar_sync event sinks deduplicate identical payloads and observe changes once
        _api(app, "POST", "/background/preferences", headers, {"enabled": True})
        observed_sources: list[tuple[str, str]] = []

        def spy_triage(_scope, source_kind, source_id, _payload, _scratchpad):
            observed_sources.append((source_kind, source_id))
            return None

        app._conversation_runtime.background_coordinator._triage_evaluator = spy_triage
        mail_sink = app._email_runtime._background_event_sink
        cal_sink = app._calendar_runtime._background_event_sink
        assert mail_sink is not None and cal_sink is not None

        mail_sink(owner.user_id, owner.workspace_id, "mbx-1", {"messages": ["m1"]})
        mail_sink(owner.user_id, owner.workspace_id, "mbx-1", {"messages": ["m1"]})  # identical -> ignored
        mail_sink(owner.user_id, owner.workspace_id, "mbx-1", {"messages": ["m1", "m2"]})  # changed -> observed
        cal_sink(owner.user_id, owner.workspace_id, "cal-1", {"events": ["e1"]})
        cal_sink(owner.user_id, owner.workspace_id, "cal-1", {"events": ["e1"]})  # identical -> ignored
        assert [k for k, _ in observed_sources] == ["mail_sync", "mail_sync", "calendar_sync"]

        # 3. Verify routine role_key CANNOT bypass WorkerRepository approval, and out-of-turn routine write parks
        #    in waiting_input + notification without projecting onto an unrelated owner Chat turn!
        owner_scope = OwnerScope(owner.user_id, owner.workspace_id)
        actions: BackgroundActions = app._conversation_runtime.background_actions
        prepared_grant = actions.prepare(
            owner_scope,
            "execution_grant",
            {"purpose": "Routine grant", "tool_names": list(TASK_TOOLS), "resource_policy": {}},
            None,
            None,
        )
        session_id = _chat(holder, "POST", "sessions", link_token, {}).payload["id"]
        t1 = _chat(holder, "POST", f"sessions/{session_id}/messages", link_token, {"text": "Approve grant"}).payload["run_id"]
        _wait_until(lambda: app._conversation_runtime.store.status(owner, session_id, t1)["state"] == "completed")
        _chat(
            holder,
            "POST",
            f"runs/{t1}/permission",
            link_token,
            {
                "action_id": prepared_grant.action_id,
                "action_hash": prepared_grant.action_hash,
                "choice": "allow_once",
                "decision_id": f"dec-rg-{prepared_grant.action_id}",
            },
        )
        with psycopg.connect(url) as conn:
            grant_id = conn.execute(
                "SELECT grant_id FROM vault_private.vault_background_execution_grants WHERE user_id=%s",
                (owner.user_id,),
            ).fetchone()[0]

        routines = BackgroundRoutines(database_url=url, jobs=app._conversation_runtime.background_coordinator.jobs)
        now = datetime.now(timezone.utc)
        unapproved_routine_id = routines.create(
            owner,
            rule={"kind": "once", "run_at": (now - timedelta(seconds=5)).isoformat(), "anchor_utc": (now - timedelta(seconds=10)).isoformat()},
            timezone="UTC",
            template={
                "request": {
                    "objective": "Try unapproved specialist",
                    "requested_tool_names": list(TASK_TOOLS),
                },
                "destination": {"kind": "activity", "role_key": "never_approved_role"},
            },
            grant_id=grant_id,
        )
        routines.tick(now)
        with psycopg.connect(url) as conn:
            unapproved_state = conn.execute(
                "SELECT state, worker_id FROM vault_private.vault_background_work WHERE routine_id=%s",
                (unapproved_routine_id,),
            ).fetchone()
        assert unapproved_state == ("waiting_input", None)

        # Out-of-turn direct routine calling tasks_add parks in waiting_input + emits notification
        app._conversation_runtime.background_coordinator.jobs.start()
        direct_routine_id = routines.create(
            owner,
            rule={"kind": "once", "run_at": (now - timedelta(seconds=2)).isoformat(), "anchor_utc": (now - timedelta(seconds=10)).isoformat()},
            timezone="UTC",
            template={
                "request": {
                    "objective": "Add Routine Task",
                    "autonomy": "expanded",
                    "requested_tool_names": list(TASK_TOOLS),
                },
                "destination": {"kind": "notification"},
            },
            grant_id=grant_id,
        )
        routines.tick(now)

        def _routine_parked():
            with psycopg.connect(url) as conn:
                r = conn.execute(
                    "SELECT state FROM vault_private.vault_background_work WHERE routine_id=%s",
                    (direct_routine_id,),
                ).fetchone()
                return r[0] == "waiting_input" if r else False

        _wait_until(_routine_parked, timeout=12.0)

        # Unrelated owner Chat turn does NOT receive the out-of-turn routine's pending action!
        t2 = _chat(holder, "POST", f"sessions/{session_id}/messages", link_token, {"text": "Hello"}).payload["run_id"]
        _wait_until(lambda: app._conversation_runtime.store.status(owner, session_id, t2)["state"] == "completed")
        unrelated_poll = _chat(holder, "GET", f"runs/{t2}", link_token).payload
        assert unrelated_poll["state"] == "completed"
        assert "permission_request" not in unrelated_poll

        notifs = app._notifications.list_active(user_id=owner.user_id, workspace_id=owner.workspace_id)
        assert any(n["kind"] == "background_approval" for n in notifs)

        # 4. Secondary user's specialist proposal NEVER projects or answers on owner's Link Companion!
        app._identity_service.create_user(
            actor=owner,
            username="second",
            password="second-password",
            display_name="Secondary User",
            experience_style="strict",
        )
        sec_tokens = app._identity_service.login(username="second", password="second-password")
        sec_headers = {
            "Cookie": f"resono_refresh={sec_tokens.session_token}; resono_csrf={sec_tokens.csrf_token}",
            "X-ReSono-CSRF": sec_tokens.csrf_token,
        }

        sec_prop = _api(
            app,
            "POST",
            "/background/workers",
            sec_headers,
            {"roleKey": "sec_helper", "purpose": "Secondary helper", "toolNames": ["tasks_list"]},
        )
        assert sec_prop.status_code == 202
        sec_action = sec_prop.payload["action"]

        t3 = _chat(holder, "POST", f"sessions/{session_id}/messages", link_token, {"text": "Check status"}).payload["run_id"]
        _wait_until(lambda: app._conversation_runtime.store.status(owner, session_id, t3)["state"] == "completed")
        owner_poll = _chat(holder, "GET", f"runs/{t3}", link_token).payload
        assert "permission_request" not in owner_poll

        hijack_attempt = _chat(
            holder,
            "POST",
            f"runs/{t3}/permission",
            link_token,
            {
                "action_id": sec_action["actionId"],
                "action_hash": sec_action["actionHash"],
                "choice": "allow_once",
                "decision_id": "hijack-sec",
            },
        )
        assert hijack_attempt.status_code >= 400
    finally:
        app.close()


def test_lifecycle_memory_forget_grant_revocation_and_backup_restore_reconciliation(tmp_path, monkeypatch):
    from psycopg.types.json import Jsonb
    from app.vault_runtime.background_agent.authority import BackgroundAuthority
    from app.vault_runtime.background_agent.coordination_contracts import ApprovalDecision
    from app.vault_runtime.memory.contracts import MemoryCandidate
    from app.vault_runtime.package_runtime import reconcile_restore

    url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Exact isolated database required")
    _reset_schemas(url)

    monkeypatch.setattr("app.vault_runtime.memory.service.MemoryService.ensure_vectors", lambda *a, **k: (0, 0))
    monkeypatch.setattr("app.vault_runtime.agent_network.service.A2AService.start", lambda *_: None)
    monkeypatch.setattr("app.vault_runtime.agent_network.inbound.A2AInboundHttpServer.start", lambda *_: None)
    monkeypatch.setattr("app.vault_runtime.extensions.mcp_runtime.McpRuntimeSupervisor.restore_on_boot", lambda *_: None)

    config = _boot_config(tmp_path, url)
    app = build_local_app(config)
    try:
        owner, headers = _onboard_owner(app)
        app._conversation_runtime.memories._embedder_factory = None
        app._conversation_runtime.title_runner = None
        app._conversation_runtime.background_coordinator.jobs.stop()

        owner_scope = OwnerScope(owner.user_id, owner.workspace_id)
        actions: BackgroundActions = app._conversation_runtime.background_actions

        # 1. Create a memory, reference it in a background session & scratchpad item, then delete_memory -> purged!
        voice_session = app._voice_sessions.create_session(
            user_id=owner.user_id,
            workspace_id=owner.workspace_id,
            local_session_id=owner.session_id,
            provider_key="openai",
            model_key="gpt-realtime",
            connection_mode="webrtc",
        )
        candidate = MemoryCandidate(
            subject_id=owner.user_id,
            domain="personal",
            memory_type="preference",
            memory_key="coffee_order",
            content_text="Prefers oat cortado",
            source_authority="user_asserted",
            confidence="high",
            sensitivity="normal",
            intent="create",
            visibility="private",
        ).validated()
        mem_repo = app._conversation_runtime.memories._repository
        rec = mem_repo.reconcile_memory(
            user_id=owner.user_id,
            workspace_id=owner.workspace_id,
            voice_session_id=voice_session.voice_session_id,
            candidate=candidate,
            evidence=((None, "explicit_memory_intent", "user_asserted", "Remember oat cortado"),),
        )
        mem_ref = f"memory:{rec.memory_id}"

        coord = app._conversation_runtime.background_coordinator
        req = BackgroundRunRequest(
            run_id="run-mem-inv-1",
            objective="Draft coffee order",
            instruction_profile="default",
            success_criteria=("Drafted",),
            result_schema=background_output_schema(),
            original_request="Draft coffee order",
            verification_method="Check",
            completion_conditions=("Drafted",),
        )
        w_mem = coord._repo.create_work(
            owner_scope,
            WorkRequest(request=req, grant_id=None, local_session_id=owner.session_id, destination={"kind": "activity"}),
            source_key="chat:mem:1",
        )
        prop_w = coord._workers.propose(
            owner_scope,
            WorkerSpec("mem_helper", "Memory helper", "Help", ("tasks_list",), {}),
        )
        dec_w = ApprovalDecision(
            action_id=prop_w.action_id,
            action_hash=prop_w.action_hash,
            choice="allow_once",
            actor_user_id=owner.user_id,
            workspace_id=owner.workspace_id,
            channel="browser",
            channel_generation=owner.session_id,
            decision_id="dec-mem-w-1",
        )
        actions.decide(owner, dec_w)
        worker_mem_id = coord._workers.create_from_approval(dec_w)
        coord._repo.assign(coord.resolve_work_scope(w_mem), worker_mem_id)
        with psycopg.connect(url) as conn:
            conn.execute(
                """UPDATE vault_private.vault_background_sessions
                   SET history_json=%s, checkpoint_json=%s, source_refs_json=%s
                   WHERE work_id=%s""",
                (
                    Jsonb(["oat cortado history"]),
                    Jsonb({"state": "saved"}),
                    Jsonb([mem_ref]),
                    w_mem,
                ),
            )
            conn.execute(
                """INSERT INTO vault_private.vault_background_events
                   (event_id, user_id, workspace_id, source_kind, source_id, payload_json, state)
                   VALUES ('scratch-mem-1', %s, %s, 'scratchpad_item', 'sp-1', %s, 'processed')""",
                (owner.user_id, owner.workspace_id, Jsonb({"source_refs": [mem_ref], "summary": "oat cortado"})),
            )

        assert mem_repo.delete_memory(user_id=owner.user_id, workspace_id=owner.workspace_id, memory_id=rec.memory_id)
        with psycopg.connect(url) as conn:
            sess_after = conn.execute(
                "SELECT history_json, checkpoint_json, source_refs_json FROM vault_private.vault_background_sessions WHERE work_id=%s",
                (w_mem,),
            ).fetchone()
            scratch_count = conn.execute(
                "SELECT count(*) FROM vault_private.vault_background_events WHERE event_id='scratch-mem-1'"
            ).fetchone()[0]
        assert sess_after == ([], None, [])
        assert scratch_count == 0

        # 2. Grant revocation pauses active routines and cancels queued work under that grant
        grant_prop = {"purpose": "Revocable grant", "tool_names": ["tasks_list"], "resource_policy": {}}
        prep_g = actions.prepare(owner_scope, "execution_grant", grant_prop, None, None)
        dec_g = ApprovalDecision(
            action_id=prep_g.action_id,
            action_hash=prep_g.action_hash,
            choice="allow_once",
            actor_user_id=owner.user_id,
            workspace_id=owner.workspace_id,
            channel="browser",
            channel_generation=owner.session_id,
            decision_id="dec-rev-g-1",
        )
        actions.decide(owner, dec_g)
        auth = BackgroundAuthority(database_url=url)
        grant_id = auth.grant(owner, grant_prop, dec_g)

        routines = BackgroundRoutines(database_url=url)
        rt_id = routines.create(
            owner,
            rule={"kind": "cron", "cron": "0 9 * * *"},
            timezone="UTC",
            template={"request": {"objective": "Revocable routine"}},
            grant_id=grant_id,
        )
        w_grant = coord._repo.create_work(
            owner_scope,
            WorkRequest(
                request=BackgroundRunRequest(
                    run_id="run-grant-rev-1",
                    objective="Granted work",
                    instruction_profile="default",
                    success_criteria=("Done",),
                    result_schema=background_output_schema(),
                    original_request="Granted work",
                    verification_method="Check",
                    completion_conditions=("Done",),
                ),
                grant_id=grant_id,
                local_session_id=None,
                destination={"kind": "activity"},
            ),
            source_key="chat:grant:1",
        )
        auth.revoke(owner, grant_id)
        with psycopg.connect(url) as conn:
            rt_status = conn.execute(
                "SELECT status FROM vault_private.vault_background_routines WHERE routine_id=%s", (rt_id,)
            ).fetchone()[0]
            wg_state = conn.execute(
                "SELECT state FROM vault_private.vault_background_work WHERE work_id=%s", (w_grant,)
            ).fetchone()[0]
        assert rt_status == "paused"
        assert wg_state == "cancelled"

        # 3. Backup restore reconciliation pauses routines, expires pending actions, and marks running work unknown
        prep_g2 = actions.prepare(owner_scope, "execution_grant", {"purpose": "Restore grant", "tool_names": ["tasks_list"], "resource_policy": {}}, None, None)
        dec_g2 = ApprovalDecision(
            action_id=prep_g2.action_id,
            action_hash=prep_g2.action_hash,
            choice="allow_once",
            actor_user_id=owner.user_id,
            workspace_id=owner.workspace_id,
            channel="browser",
            channel_generation=owner.session_id,
            decision_id="dec-rest-g-2",
        )
        actions.decide(owner, dec_g2)
        grant_id_2 = auth.grant(owner, {"purpose": "Restore grant", "tool_names": ["tasks_list"], "resource_policy": {}}, dec_g2)
        rt_restore = routines.create(
            owner,
            rule={"kind": "cron", "cron": "0 10 * * *"},
            timezone="UTC",
            template={"request": {"objective": "Routine before backup"}},
            grant_id=grant_id_2,
        )
        pending_act = actions.prepare(
            owner_scope,
            "execution_grant",
            {"purpose": "Unfinished pending action", "tool_names": ["tasks_list"], "resource_policy": {}},
            None,
            None,
        )
        w_running = coord._repo.create_work(
            owner_scope,
            WorkRequest(
                request=BackgroundRunRequest(
                    run_id="run-inflight-restore",
                    objective="In-flight during backup",
                    instruction_profile="default",
                    success_criteria=("Done",),
                    result_schema=background_output_schema(),
                    original_request="In-flight during backup",
                    verification_method="Check",
                    completion_conditions=("Done",),
                ),
                grant_id=grant_id_2,
                local_session_id=None,
                destination={"kind": "activity"},
            ),
            source_key="chat:restore:1",
        )
        with psycopg.connect(url) as conn:
            conn.execute("UPDATE vault_private.vault_background_work SET state='running' WHERE work_id=%s", (w_running,))

        summary = reconcile_restore(database_url=url)
        assert summary["pausedRoutines"] >= 1
        assert summary["expiredActions"] >= 1
        assert summary["reconciledWork"] >= 1

        with psycopg.connect(url) as conn:
            restored_rt = conn.execute(
                "SELECT status FROM vault_private.vault_background_routines WHERE routine_id=%s", (rt_restore,)
            ).fetchone()[0]
            restored_act = conn.execute(
                "SELECT state FROM vault_private.vault_background_actions WHERE action_id=%s", (pending_act.action_id,)
            ).fetchone()[0]
            restored_work = conn.execute(
                "SELECT state FROM vault_private.vault_background_work WHERE work_id=%s", (w_running,)
            ).fetchone()[0]
        assert restored_rt == "paused"
        assert restored_act == "expired"
        assert restored_work == "unknown"
    finally:
        app.close()

