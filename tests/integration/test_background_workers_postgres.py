"""PostgreSQL integration tests for BackgroundCoordinator, private specialist profiles, and BackgroundResults (Task 6)."""
from __future__ import annotations

import asyncio

import psycopg
from psycopg.types.json import Jsonb
import pytest

from app.vault_runtime.background_agent.actions import BackgroundActions
from app.vault_runtime.background_agent.contracts import AutonomyProfile, BackgroundRunRequest, RunLimits
from app.vault_runtime.background_agent.coordination_contracts import (
    ApprovalDecision,
    ExecutionOutcome,
    OwnerScope,
    WorkerSpec,
    WorkRequest,
    WorkState,
)
from app.vault_runtime.background_agent.coordinator import (
    BackgroundCoordinator,
    CoordinatorObservationDecision,
)
from app.vault_runtime.background_agent.output_contract import background_output_schema
from app.vault_runtime.background_agent.errors import BackgroundRunAuthorizationError
from app.vault_runtime.background_agent.results import BackgroundResults
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.memory.repository import MemoryRepository
from app.vault_runtime.notifications.repository import NotificationRepository
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tasks.repository import TaskRepository
from app.vault_runtime.tasks_tools import register_tasks_tools
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult
from app.vault_runtime.voice.events import VoiceProviderEventCapture
from app.vault_runtime.voice.repository import VoiceSessionRepository
from app.vault_runtime.voice.tools import LocalToolAuthority
from tests.support.background_authority import components
from tests.support.background_workers import _RecordingExecutor


def _request(
    run_id: str,
    objective: str = "Compile project status",
    tools: tuple[str, ...] = ("tasks_list",),
) -> BackgroundRunRequest:
    return BackgroundRunRequest(
        run_id=run_id,
        objective=objective,
        instruction_profile="background-default",
        success_criteria=("Status compiled accurately",),
        result_schema=background_output_schema(),
        autonomy=AutonomyProfile.EXPANDED,
        original_request=objective,
        verification_method="Verify status against task list",
        completion_conditions=("Status verified",),
        requested_tool_names=tools,
    )


def _setup_env(context):
    db_url = context[0]
    principal = context[1]
    m, repo, owner, _req, authority, workers = components(context)
    policy = {"tool_names": ["tasks_list"], "resource_policy": {}}
    with psycopg.connect(db_url) as connection:
        connection.execute(
            """INSERT INTO vault_private.vault_background_execution_grants
               (grant_id, user_id, workspace_id, purpose, policy_json)
               VALUES ('grant-t6', %s, %s, 'Read tasks for background coordination', %s)""",
            (owner.user_id, owner.workspace_id, Jsonb(policy)),
        )
    VoiceSessionRepository(database_url=db_url).ensure_schema()
    local = LocalToolAuthority(database_url=db_url, background_authority=authority)
    local.set_grant(
        actor_user_id=owner.user_id,
        workspace_id=owner.workspace_id,
        tool_name="tasks_list",
        effect_class="read",
        voice_enabled=True,
        background_enabled=True,
        user_id=owner.user_id,
    )
    catalog = ToolCatalog(authorizer=local.authorize, background_authorizer=local.authorize_background)
    tasks = TaskRepository(database_url=db_url)
    tasks.ensure_schema()
    register_tasks_tools(catalog=catalog, repository=tasks)
    actions = BackgroundActions(database_url=db_url, domains={})
    results = BackgroundResults(database_url=db_url)
    executor = _RecordingExecutor()
    coordinator = BackgroundCoordinator(
        database_url=db_url,
        executor=executor,
        catalog=catalog,
        results=results,
    )
    return {
        "db_url": db_url,
        "m": m,
        "repo": repo,
        "owner": owner,
        "principal": principal,
        "authority": authority,
        "workers": workers,
        "local": local,
        "catalog": catalog,
        "actions": actions,
        "results": results,
        "executor": executor,
        "coordinator": coordinator,
        "grant_id": "grant-t6",
    }


def test_role_proposal_awaits_user_approval_and_reuses_approved_specialist_without_reprompting(
    context,
) -> None:
    env = _setup_env(context)
    db_url = env["db_url"]
    owner = env["owner"]
    principal = env["principal"]
    coordinator = env["coordinator"]
    executor = env["executor"]
    actions = env["actions"]
    grant_id = env["grant_id"]

    coordinator.set_observation_enabled(owner, True)
    spec = WorkerSpec(
        role_key="status_compiler",
        purpose="Compile weekly status from tasks",
        instructions="Read tasks and summarize progress.",
        tool_names=("tasks_list",),
        resource_policy={},
        limits=RunLimits(),
    )
    work_req_1 = WorkRequest(
        request=_request("run-role-1", "Compile status week 1"),
        grant_id=grant_id,
        local_session_id=None,
        destination={"kind": "activity", "role_key": "status_compiler"},
    )

    work_id_1 = coordinator.observe(
        owner,
        "conversation_turn",
        "conv-1:turn-1",
        {
            "decision": CoordinatorObservationDecision(
                action="propose_worker",
                work_request=work_req_1,
                worker_spec=spec,
                reason="Needs recurring status specialist",
            )
        },
    )
    assert work_id_1

    # Dispatch before approval must wait for approval with zero model calls and zero created workers
    outcome_waiting = coordinator.dispatch_sync(work_id_1)
    assert outcome_waiting.state is WorkState.WAITING_APPROVAL
    assert outcome_waiting.pending_action_id is not None
    assert len(executor.calls) == 0

    with psycopg.connect(db_url) as conn:
        worker_count = conn.execute(
            "SELECT count(*) FROM vault_private.vault_background_workers WHERE user_id=%s AND workspace_id=%s",
            (owner.user_id, owner.workspace_id),
        ).fetchone()[0]
        action_row = conn.execute(
            "SELECT action_id, action_hash FROM vault_private.vault_background_actions WHERE action_id=%s",
            (outcome_waiting.pending_action_id,),
        ).fetchone()
    assert worker_count == 0
    assert action_row is not None

    # Owner approves the role proposal
    actions.decide(
        principal,
        ApprovalDecision(
            action_id=action_row[0],
            action_hash=action_row[1],
            choice="allow_once",
            actor_user_id=owner.user_id,
            workspace_id=owner.workspace_id,
            channel="browser",
            channel_generation=principal.session_id,
            decision_id="dec-role-approve-1",
        ),
    )

    # Now dispatch runs with the approved specialist and returns it to idle with zero further model calls
    assert asyncio.run(coordinator.dispatch(work_id_1)).state is WorkState.QUEUED
    assert executor.calls == []
    outcome_done = coordinator.dispatch_sync(work_id_1)
    assert outcome_done.state is WorkState.COMPLETED
    assert len(executor.calls) == 1

    with psycopg.connect(db_url) as conn:
        worker_row = conn.execute(
            "SELECT worker_id, status FROM vault_private.vault_background_workers WHERE user_id=%s AND workspace_id=%s AND role_key='status_compiler'",
            (owner.user_id, owner.workspace_id),
        ).fetchone()
    assert worker_row is not None
    assert worker_row[1] == "idle"

    # Second work item for the same role_key reuses the approved specialist without proposing another worker_create action
    work_req_2 = WorkRequest(
        request=_request("run-role-2", "Compile status week 2"),
        grant_id=grant_id,
        local_session_id=None,
        destination={"kind": "activity", "role_key": "status_compiler"},
    )
    work_id_2 = coordinator.observe(
        owner,
        "conversation_turn",
        "conv-1:turn-2",
        {
            "decision": CoordinatorObservationDecision(
                action="create_work",
                work_request=work_req_2,
                role_key="status_compiler",
                reason="Reuse approved status_compiler specialist",
            )
        },
    )
    outcome_done_2 = coordinator.dispatch_sync(work_id_2)
    assert outcome_done_2.state is WorkState.COMPLETED
    assert len(executor.calls) == 2
    assert executor.calls[1]["scope"].worker_id == worker_row[0]

    with psycopg.connect(db_url) as conn:
        proposal_count = conn.execute(
            "SELECT count(*) FROM vault_private.vault_background_actions WHERE user_id=%s AND workspace_id=%s AND kind='worker_create'",
            (owner.user_id, owner.workspace_id),
        ).fetchone()[0]
    assert proposal_count == 1


def test_two_private_specialists_have_isolated_sessions_and_coordinator_sees_only_brief_and_result(
    context,
) -> None:
    env = _setup_env(context)
    owner = env["owner"]
    principal = env["principal"]
    coordinator = env["coordinator"]
    executor = env["executor"]
    actions = env["actions"]
    workers = env["workers"]
    grant_id = env["grant_id"]

    coordinator.set_observation_enabled(owner, True)
    spec_alpha = WorkerSpec("alpha_specialist", "Alpha research", "Alpha instructions.", ("tasks_list",), {})
    spec_beta = WorkerSpec("beta_specialist", "Beta planning", "Beta instructions.", ("tasks_list",), {})

    for idx, spec in enumerate((spec_alpha, spec_beta), start=1):
        prop = workers.propose(owner, spec)
        actions.decide(
            principal,
            ApprovalDecision(
                action_id=prop.action_id,
                action_hash=prop.action_hash,
                choice="allow_once",
                actor_user_id=owner.user_id,
                workspace_id=owner.workspace_id,
                channel="browser",
                channel_generation=principal.session_id,
                decision_id=f"dec-iso-{idx}",
            ),
        )

    # Run Alpha work #1
    w_alpha_1 = coordinator.observe(
        owner,
        "conversation_turn",
        "c-iso:1",
        {
            "decision": CoordinatorObservationDecision(
                action="create_work",
                work_request=WorkRequest(_request("run-alpha-1", "Alpha Secret Brief 1"), grant_id, None, {"role_key": "alpha_specialist"}),
                role_key="alpha_specialist",
                reason="Alpha task 1",
            )
        },
    )
    assert coordinator.dispatch_sync(w_alpha_1).state is WorkState.COMPLETED

    # Run Beta work #1 - must NOT contain Alpha's session history in its instructions/context
    w_beta_1 = coordinator.observe(
        owner,
        "conversation_turn",
        "c-iso:2",
        {
            "decision": CoordinatorObservationDecision(
                action="create_work",
                work_request=WorkRequest(_request("run-beta-1", "Beta Brief 1"), grant_id, None, {"role_key": "beta_specialist"}),
                role_key="beta_specialist",
                reason="Beta task 1",
            )
        },
    )
    assert coordinator.dispatch_sync(w_beta_1).state is WorkState.COMPLETED
    beta_call = executor.calls[-1]
    assert "Alpha Secret Brief 1" not in beta_call["request"].context_summary
    assert "Alpha Secret Brief 1" not in beta_call["request"].instruction_profile

    # Run Alpha work #2 - carries forward Alpha's own bounded session history
    w_alpha_2 = coordinator.observe(
        owner,
        "conversation_turn",
        "c-iso:3",
        {
            "decision": CoordinatorObservationDecision(
                action="create_work",
                work_request=WorkRequest(_request("run-alpha-2", "Alpha Brief 2"), grant_id, None, {"role_key": "alpha_specialist"}),
                role_key="alpha_specialist",
                reason="Alpha task 2",
            )
        },
    )
    assert coordinator.dispatch_sync(w_alpha_2).state is WorkState.COMPLETED
    alpha_call_2 = executor.calls[-1]
    assert "Alpha Secret Brief 1" in alpha_call_2["request"].context_summary
    assert "Beta Brief 1" not in alpha_call_2["request"].context_summary

    # Coordinator view exposes only permitted brief and terminal result, never private session history/checkpoints
    coord_view = coordinator.get_coordinator_view(owner, w_alpha_2)
    assert coord_view["work_id"] == w_alpha_2
    assert coord_view["brief"]["objective"] == "Alpha Brief 2"
    assert coord_view["result"]["summary"] == "Completed Alpha Brief 2"
    assert "history_json" not in coord_view
    assert "checkpoint_json" not in coord_view


def test_helper_cannot_spawn_helpers_widen_grants_or_speak_as_owner(
    context,
) -> None:
    env = _setup_env(context)
    db_url = env["db_url"]
    owner = env["owner"]
    principal = env["principal"]
    coordinator = env["coordinator"]
    executor = env["executor"]
    actions = env["actions"]
    workers = env["workers"]
    catalog = env["catalog"]

    # Register a forbidden delegation tool in the catalog to prove the helper tool supply strips it
    catalog.register(
        ToolDefinition(
            tool_id="builtin.goal.start.test",
            name="goal_start",
            description="Forbidden recursive goal spawning tool",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=lambda context, args: ToolInvocationResult("spawned", {"spawned": True}),
            effect_class="write",
            audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
        )
    )
    with psycopg.connect(db_url) as conn:
        conn.execute(
            """INSERT INTO vault_private.vault_background_execution_grants
               (grant_id, user_id, workspace_id, purpose, policy_json)
               VALUES ('grant-spawn-test', %s, %s, 'Grant with tasks_list and goal_start', %s)""",
            (owner.user_id, owner.workspace_id, Jsonb({"tool_names": ["tasks_list", "goal_start"], "resource_policy": {}})),
        )
    coordinator.set_observation_enabled(owner, True)
    spec = WorkerSpec(
        role_key="restricted_helper",
        purpose="Read tasks only",
        instructions="Read tasks.",
        tool_names=("tasks_list", "goal_start"),
        resource_policy={},
    )
    prop = workers.propose(owner, spec)
    actions.decide(
        principal,
        ApprovalDecision(
            action_id=prop.action_id,
            action_hash=prop.action_hash,
            choice="allow_once",
            actor_user_id=owner.user_id,
            workspace_id=owner.workspace_id,
            channel="browser",
            channel_generation=principal.session_id,
            decision_id="dec-restricted-1",
        ),
    )

    work_id = coordinator.observe(
        owner,
        "conversation_turn",
        "c-res:1",
        {
            "decision": CoordinatorObservationDecision(
                action="create_work",
                work_request=WorkRequest(
                    _request("run-res-1", "Check tasks without spawning", tools=("tasks_list", "goal_start")),
                    "grant-spawn-test",
                    None,
                    {"role_key": "restricted_helper"},
                ),
                role_key="restricted_helper",
                reason="Test restrictions",
            )
        },
    )
    outcome = coordinator.dispatch_sync(work_id)
    assert outcome.state is WorkState.COMPLETED
    supplied_tools = executor.calls[-1]["tool_names"]
    assert "goal_start" not in supplied_tools
    assert "tasks_list" in supplied_tools

    # Verify invoking an ungranted tool or forbidden tool through the helper's tool supply is denied
    helper_tools = executor.calls[-1]["tools"]
    helper_ctx = ToolInvocationContext(
        agent=AgentKind.BACKGROUND,
        user_id=owner.user_id,
        workspace_id=owner.workspace_id,
        tool_call_id="c-spawn",
        local_session_id=None,
        execution_id="run-res-1",
        background_scope=executor.calls[-1]["scope"],
    )
    denied_spawn = helper_tools.invoke("goal_start", {}, context=helper_ctx)
    assert denied_spawn.is_error is True
    denied_widen = helper_tools.invoke("tasks_add", {"text": "Unauthorized write"}, context=helper_ctx)
    assert denied_widen.is_error is True


def test_one_result_returns_once_cancelled_or_invalidated_work_cannot_publish_late_and_artifacts_stay_references(
    context,
) -> None:
    env = _setup_env(context)
    db_url = env["db_url"]
    owner = env["owner"]
    repo = env["repo"]
    grant_id = env["grant_id"]
    executor = env["executor"]
    catalog = env["catalog"]

    memories = MemoryRepository(database_url=db_url)
    memories.ensure_schema()
    notifications = NotificationRepository(database_url=db_url)
    notifications.ensure_schema()

    results = BackgroundResults(database_url=db_url, notifications=notifications)
    coordinator = BackgroundCoordinator(
        database_url=db_url,
        executor=executor,
        catalog=catalog,
        results=results,
    )
    coordinator.set_observation_enabled(owner, True)

    work_id = coordinator.observe(
        owner,
        "conversation_turn",
        "c-dedup:1",
        {
            "decision": CoordinatorObservationDecision(
                action="create_work",
                work_request=WorkRequest(
                    _request("run-dedup-1", "Generate artifact reference"),
                    grant_id,
                    None,
                    {"kind": "notification"},
                ),
                reason="Test one-result dedup",
            )
        },
    )
    outcome = coordinator.dispatch_sync(work_id)
    assert outcome.state is WorkState.COMPLETED

    scope = coordinator.resolve_work_scope(work_id)
    # Replaying the same completed result or delivery has no effect.
    assert not repo.accept_result(scope, "run-dedup-1", outcome)
    delivery_1 = results.deliver(scope, {"kind": "notification"}, "run-dedup-1:1")
    delivery_2 = results.deliver(scope, {"kind": "notification"}, "run-dedup-1:1")
    assert delivery_1 == delivery_2

    with psycopg.connect(db_url) as conn:
        result_events = conn.execute(
            "SELECT count(*) FROM vault_private.vault_background_events WHERE user_id=%s AND workspace_id=%s AND source_kind='result' AND source_id='run-dedup-1:1'",
            (owner.user_id, owner.workspace_id),
        ).fetchone()[0]
        mem_count = conn.execute(
            "SELECT count(*) FROM vault_private.vault_memory_records WHERE user_id=%s AND workspace_id=%s",
            (owner.user_id, owner.workspace_id),
        ).fetchone()[0]
    assert result_events == 1
    # Helper results and shared artifacts must NEVER be written into permanent memory automatically
    assert mem_count == 0

    # Source invalidation prevents any further delivery of results depending on that source_ref
    results.invalidate(scope, f"artifact://{work_id}")
    with pytest.raises(BackgroundRunAuthorizationError):
        results.deliver(scope, {"kind": "notification"}, "run-dedup-1:1")

    # Cancelled work cannot publish late
    work_id_cancel = coordinator.observe(
        owner,
        "conversation_turn",
        "c-dedup:2",
        {
            "decision": CoordinatorObservationDecision(
                action="create_work",
                work_request=WorkRequest(
                    _request("run-cancel-late", "Work to cancel"),
                    grant_id,
                    None,
                    {"kind": "notification"},
                ),
                reason="Test cancelled late publish",
            )
        },
    )
    cancel_scope = coordinator.resolve_work_scope(work_id_cancel)
    repo.transition(cancel_scope, WorkState.PROPOSED, WorkState.CANCELLED, {"reason": "user_cancelled"})
    assert not repo.accept_result(cancel_scope, "run-cancel-late", outcome)
    row_after = repo.get(owner, work_id_cancel)
    assert row_after["state"] == "cancelled"
    assert row_after["result_json"] is None
    with pytest.raises(BackgroundRunAuthorizationError):
        results.deliver(cancel_scope, {"kind": "notification"}, "run-cancel-late:1")


def test_opt_in_controls_unsolicited_voice_and_chat_observation_while_explicit_goal_start_always_works(
    context,
) -> None:
    env = _setup_env(context)
    db_url = env["db_url"]
    owner = env["owner"]
    principal = env["principal"]
    executor = env["executor"]
    catalog = env["catalog"]
    results = env["results"]
    triage_calls: list[tuple[str, str]] = []

    def _triage(scope: OwnerScope, source_kind: str, source_id: str, payload: dict, scratchpad: dict):
        triage_calls.append((source_kind, source_id))
        return CoordinatorObservationDecision(
            action="create_work",
            work_request=WorkRequest(
                _request(f"run-{source_id.replace(':', '-')}", f"Observed {source_id}"),
                None,
                principal.session_id,
                {"kind": "activity"},
            ),
            reason="Structured triage created work",
        )

    coordinator = BackgroundCoordinator(
        database_url=db_url,
        executor=executor,
        catalog=catalog,
        results=results,
        triage_evaluator=_triage,
    )

    # Default opt-in is False: unsolicited observation returns "" and does not call triage or create work
    assert coordinator.is_observation_enabled(owner) is False
    unsolicited = coordinator.observe(
        owner,
        "conversation_turn",
        "conv-opt:turn-1",
        {"input_text": "Can we prepare next week's agenda?"},
    )
    assert unsolicited == ""
    assert len(triage_calls) == 0

    # Voice transcript capture hook with opt-in False also does not create unsolicited work
    memories = MemoryRepository(database_url=db_url)
    memories.ensure_schema()
    voice_sessions = VoiceSessionRepository(database_url=db_url)
    voice_sessions.ensure_schema()
    voice_session = voice_sessions.create_session(
        user_id=owner.user_id,
        workspace_id=owner.workspace_id,
        local_session_id=principal.session_id,
        provider_key="openai",
        model_key="gpt-realtime",
        connection_mode="webrtc",
    )
    capture = VoiceProviderEventCapture(
        sessions=voice_sessions,
        memories=memories,
        background_coordinator=coordinator,
    )
    capture.capture(
        user_id=owner.user_id,
        workspace_id=owner.workspace_id,
        local_session_id=principal.session_id,
        voice_session_id=voice_session.voice_session_id,
        provider_event_id="ev-1",
        event_type="conversation.item.input_audio_transcription.completed",
        event_role="user",
        payload={"text": "Remind me to check the budget"},
        transcript_text="Remind me to check the budget",
        transcript_entry_index=0,
    )
    assert len(triage_calls) == 0

    # Now enable opt-in: committed Voice transcript capture observes once per source key
    coordinator.set_observation_enabled(owner, True)
    capture.capture(
        user_id=owner.user_id,
        workspace_id=owner.workspace_id,
        local_session_id=principal.session_id,
        voice_session_id=voice_session.voice_session_id,
        provider_event_id="ev-2",
        event_type="conversation.item.input_audio_transcription.completed",
        event_role="user",
        payload={"text": "Prepare the project checklist"},
        transcript_text="Prepare the project checklist",
        transcript_entry_index=1,
    )
    assert len(triage_calls) == 1
    assert triage_calls[0] == ("voice_transcript", f"{voice_session.voice_session_id}:1")

    # Replaying the exact same source key does not duplicate work or re-run triage
    duplicate_work_id = coordinator.observe(
        owner,
        "voice_transcript",
        f"{voice_session.voice_session_id}:1",
        {
            "voice_session_id": voice_session.voice_session_id,
            "local_session_id": principal.session_id,
            "provider_event_id": "ev-2",
            "entry_index": 1,
            "role": "user",
            "text": "Prepare the project checklist",
        },
    )
    assert duplicate_work_id
    assert len(triage_calls) == 1


@pytest.mark.parametrize(("tool_names", "fails", "specialist"), [
    ([], False, False), (["tasks_list"], False, False), ([], True, False),
    (["tasks_list"], False, True),
])
def test_chat_background_start_queues_once_and_returns_to_original_conversation(context, tool_names, fails, specialist):
    from app.vault_runtime.background_agent.coordinator_tools import register_background_conversation_tools
    from app.vault_runtime.conversation.runtime_store import ConversationRuntimeStore

    env = _setup_env(context)
    principal = env["principal"]
    coordinator = env["coordinator"]
    catalog = env["catalog"]
    if fails:
        async def fail(*_):
            env["executor"].calls.append({"tool_names": ()})
            return ExecutionOutcome(WorkState.FAILED, failure_code="provider_unavailable")

        coordinator._executor.execute = fail
    store = ConversationRuntimeStore(database_url=env["db_url"])
    store.ensure_schema()
    conversation = store.create(principal, "queue-test")
    turn = store.submit_text(principal, conversation.conversation_id, "link:queue-test",
                             "Prepare a brief", conversation.history_version)
    register_background_conversation_tools(
        catalog=catalog, database_url=env["db_url"], resolve_principal=None, coordinator=coordinator,
    )
    assert "background_start" not in {definition.name for definition in catalog.definitions_for(AgentKind.VOICE)}
    tool = catalog.definition("background_start")
    invocation = ToolInvocationContext(
        agent=AgentKind.VOICE, user_id=principal.user_id, workspace_id=principal.workspace_id,
        tool_call_id="queue-test-call", local_session_id=principal.session_id,
        conversation_id=conversation.conversation_id, turn_id=turn.turn_id,
    )
    arguments = {
        "objective": "Prepare a brief", "tool_names": tool_names,
        "context_summary": "Use the agreed reporting period from the chat.",
    }
    if specialist:
        from tests.support.background_authority import approve_fixture

        prepared = env["workers"].propose(env["owner"], WorkerSpec(
            "briefing", "Prepare task briefs", "Summarize tasks", ("tasks_list",), {},
        ))
        worker_id = env["workers"].create_from_approval(approve_fixture(context, prepared))
        arguments["role_key"] = "briefing"
    accepted = tool.handler(invocation, arguments)
    assert not accepted.is_error
    work_id = accepted.structured_content["workId"]
    assert tool.handler(invocation, arguments).structured_content["workId"] == work_id
    expected_state = WorkState.FAILED if fails else WorkState.COMPLETED
    assert coordinator.dispatch_sync(work_id).state is expected_state
    assert len(env["executor"].calls) == 1
    assert env["executor"].calls[0]["tool_names"] == tuple(tool_names)
    if specialist:
        assert env["executor"].calls[0]["scope"].worker_id == worker_id
        assert arguments["context_summary"] in env["executor"].calls[0]["request"].context_summary
    page = store.display_history(principal, conversation.conversation_id, include_background=True)
    assert [entry["input"] for entry in page["turns"]] == ["Prepare a brief", None]
    expected_answer = "Background run failed: Prepare a brief" if fails else "Completed Prepare a brief"
    assert page["turns"][-1]["answer"] == expected_answer


def test_existing_specialist_adds_memory_search_only_after_approval(context):
    from tests.support.background_authority import approve_fixture

    env = _setup_env(context)
    workers = env["workers"]
    owner = env["owner"]
    new_worker = workers.propose(owner, WorkerSpec(
        "briefing", "Prepare briefs", "Summarize tasks", ("tasks_list",), {},
    ))
    worker_id = workers.create_from_approval(approve_fixture(context, new_worker))
    prepared = workers.propose_memory_lookup(owner, "briefing", conversation_id="chat", turn_id="turn")
    assert prepared is not None
    assert workers.get(owner, worker_id).tool_names == ("tasks_list",)
    principal = env["principal"]
    decision = ApprovalDecision(
        prepared.action_id, prepared.action_hash, "allow_once", principal.user_id,
        principal.workspace_id, "browser", principal.session_id, "enable-memory-lookup",
    )
    env["actions"].decide(principal, decision)
    assert workers.create_from_approval(decision) == worker_id
    assert workers.create_from_approval(decision) == worker_id
    assert workers.get(owner, worker_id).tool_names == ("tasks_list", "memory_lookup")

    from app.vault_runtime.memory.service import MemoryService
    from app.vault_runtime.memory.tools import register_memory_tools
    from tests.support.indexed_memory import _memory

    memories = MemoryRepository(database_url=env["db_url"])
    memories.ensure_schema()
    expected = _memory(memories, principal, "reporting-period", vector=None)
    _memory(memories, context[2], "reporting-period", vector=None)
    env["local"].set_grant(
        actor_user_id=owner.user_id, workspace_id=owner.workspace_id, user_id=owner.user_id,
        tool_name="memory_lookup", effect_class="read", voice_enabled=True, background_enabled=True,
    )
    register_memory_tools(catalog=env["catalog"], repository=memories, service=MemoryService(repository=memories))
    seen = []

    async def search(scope, request, _checkpoint, tools, _cancelled):
        context = ToolInvocationContext(
            agent=AgentKind.BACKGROUND, user_id=owner.user_id, workspace_id=owner.workspace_id,
            tool_call_id="specialist-memory-search", local_session_id=principal.session_id,
            execution_id=request.run_id, background_scope=scope,
        )
        result = tools.invoke("memory_lookup", {"query": "reporting-period"}, context=context)
        assert not result.is_error, result.text
        seen.extend(item["memoryId"] for item in result.structured_content["items"])
        return ExecutionOutcome(WorkState.COMPLETED, output={"summary": "Found the reporting period"})

    env["executor"].execute = search
    coordinator = env["coordinator"]
    work = coordinator.observe(owner, "explicit_goal", "specialist-memory-test", {
        "work_request": WorkRequest(
            _request("specialist-memory-test", tools=("memory_lookup",)),
            None, principal.session_id, {"role_key": "briefing"},
        ),
    })
    assert coordinator.dispatch_sync(work).state is WorkState.COMPLETED
    assert seen == [expected.memory_id]


def test_chat_assignment_resumes_after_specialist_approval_without_another_message(context):
    from app.vault_runtime.background_agent.coordinator_tools import register_background_conversation_tools
    from app.vault_runtime.conversation.runtime_store import ConversationRuntimeStore

    env = _setup_env(context)
    principal = env["principal"]
    coordinator = env["coordinator"]
    catalog = env["catalog"]
    store = ConversationRuntimeStore(database_url=env["db_url"])
    store.ensure_schema()
    conversation = store.create(principal, "specialist-assignment-test")
    # A turn Vault started (not the owner) keeps Rakazo's outside-run gating: approval first.
    turn = store.submit_text(principal, conversation.conversation_id, "vault-wake:assignment-test:0",
                             "Create a specialist and prepare the brief", conversation.history_version)
    register_background_conversation_tools(
        catalog=catalog, database_url=env["db_url"], resolve_principal=None, coordinator=coordinator,
    )
    call = ToolInvocationContext(
        agent=AgentKind.VOICE, user_id=principal.user_id, workspace_id=principal.workspace_id,
        tool_call_id="assignment", local_session_id=principal.session_id,
        conversation_id=conversation.conversation_id, turn_id=turn.turn_id,
    )
    result = catalog.definition("background_start").handler(call, {
        "objective": "Prepare the brief", "tool_names": [],
        "new_specialist": {"role_key": "briefing", "purpose": "Prepare briefs",
                           "instructions": "Summarize the assignment", "tool_names": []},
    })
    assert not result.is_error, result.text
    assert result.structured_content["status"] == "waiting_approval"
    action_id = result.structured_content["actionId"]
    work_id = result.structured_content["workId"]
    assert coordinator.jobs.resume_decided() == 0
    with psycopg.connect(env["db_url"]) as connection:
        action_hash, = connection.execute(
            "SELECT action_hash FROM vault_private.vault_background_actions WHERE action_id=%s", (action_id,),
        ).fetchone()
    decision = ApprovalDecision(
        action_id, action_hash, "allow_once", principal.user_id, principal.workspace_id,
        "browser", principal.session_id, "approve-briefing",
    )
    env["actions"].decide(principal, decision)
    worker_id = env["workers"].create_from_approval(decision)
    # Simulate an approval handler that exits after committing the receipt, before dispatch.
    coordinator.jobs.ensure_schema()
    assert coordinator.jobs.resume_decided() == 1
    assert coordinator.jobs.resume_decided() == 0
    assert coordinator.dispatch_sync(work_id).state is WorkState.COMPLETED
    assert len(env["executor"].calls) == 1
    assert env["executor"].calls[0]["scope"].worker_id == worker_id
    assert store.display_history(principal, conversation.conversation_id, include_background=True)["turns"][-1]["answer"] == "Completed Prepare the brief"

    # The owner asking in their own turn creates the specialist at once (Rakazo spawn_bot) and starts the work.
    owner_turn = store.submit_text(principal, conversation.conversation_id, "link:owner-assignment",
                                   "Create a writer and draft the note", conversation.history_version + 1)
    owner_call = ToolInvocationContext(
        agent=AgentKind.VOICE, user_id=principal.user_id, workspace_id=principal.workspace_id,
        tool_call_id="owner-assignment", local_session_id=principal.session_id,
        conversation_id=conversation.conversation_id, turn_id=owner_turn.turn_id,
    )
    direct = catalog.definition("background_start").handler(owner_call, {
        "objective": "Draft the note", "tool_names": [],
        "new_specialist": {"role_key": "writer", "purpose": "Write notes",
                           "instructions": "Draft clearly", "tool_names": []},
    })
    assert not direct.is_error, direct.text
    assert "actionId" not in direct.structured_content
    assert coordinator.dispatch_sync(direct.structured_content["workId"]).state is WorkState.COMPLETED
