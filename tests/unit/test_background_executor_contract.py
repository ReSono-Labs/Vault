"""Unit contract tests for ResumableBackgroundExecutor and checkpoint guards (Task 5)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
import pytest

from app.vault_runtime.background_agent.contracts import AutonomyProfile, BackgroundRunRequest, RunLimits
from app.vault_runtime.background_agent.coordination_contracts import ExecutionOutcome, WorkScope, WorkState
from app.vault_runtime.background_agent.errors import BackgroundRunAuthorizationError
from app.vault_runtime.background_agent.tool_supply import BackgroundToolGrant, BackgroundToolSupply
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationResult


def _scope(*, work_id: str = "work-1", intent_version: int = 1, worker_id: str | None = "worker-1",
           worker_generation: int | None = 1, grant_id: str | None = "grant-1") -> WorkScope:
    return WorkScope(
        user_id="user-1", workspace_id="ws-1", work_id=work_id, intent_version=intent_version,
        worker_id=worker_id, worker_generation=worker_generation, grant_id=grant_id,
    )


def _request(*, max_seconds: int = 120, max_model_turns: int = 8, max_tool_calls: int = 8) -> BackgroundRunRequest:
    return BackgroundRunRequest(
        run_id="run-1",
        objective="Publish brief after approval",
        instruction_profile="background.default.v1",
        original_request="Publish the brief card",
        verification_method="Check brief output",
        result_schema={"type": "object"},
        success_criteria=("Brief published",),
        completion_conditions=("Brief saved once",),
        stop_conditions=("Owner denies",),
        requested_tool_names=("read_notes", "publish_brief"),
        autonomy=AutonomyProfile.EXPANDED,
        limits=RunLimits(
            max_seconds=max_seconds,
            max_model_turns=max_model_turns,
            max_tool_calls=max_tool_calls,
            max_review_rounds=1,
            max_workspace_bytes=65536,
        ),
    )


def _complete_json(summary: str = "Brief published", status: str = "complete") -> str:
    return json.dumps({
        "status": status,
        "summary": summary,
        "artifact_references": [],
        "requirement_outcomes": [{
            "requirement": "Brief published",
            "status": "completed" if status == "complete" else "unresolved",
            "evidence": summary,
        }],
        "unresolved_issues": [] if status == "complete" else [summary],
        "verification_summary": "Verified offline",
        "phase_evidence": [{"phase": "act", "summary": summary}],
    })


class FakeActionStore:
    """In-memory stand-in for BackgroundActions used in unit contract tests."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, object]] = {}
        self._seq = 0
        self.current_time = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self.current_time

    def check(self, scope: WorkScope, kind: str, arguments: dict[str, object]) -> None:
        pass

    def prepare(self, scope: WorkScope, kind: str, arguments: dict[str, object],
                resource_version: str, domain_ref: str):
        from app.vault_runtime.background_agent.coordination_contracts import PreparedAction
        from hashlib import sha256
        self._seq += 1
        action_id = f"act-{self._seq}"
        digest = sha256(json.dumps({
            "kind": kind, "arguments": arguments, "version": resource_version, "ref": domain_ref,
        }, sort_keys=True).encode("utf-8")).hexdigest()
        expires_at = self.current_time + timedelta(minutes=15)
        self.rows[action_id] = {
            "action_id": action_id,
            "action_hash": digest,
            "work_id": scope.work_id,
            "kind": kind,
            "arguments_json": arguments,
            "resource_version": resource_version,
            "domain_ref": domain_ref,
            "state": "pending",
            "expires_at": expires_at,
        }
        return PreparedAction(
            action_id=action_id, action_hash=digest, work_id=scope.work_id,
            kind=kind, title=f"Approve {kind}", detail=str(arguments.get("summary", kind)),
            expires_at=expires_at,
        )

    def get(self, scope: WorkScope, action_id: str) -> dict[str, object]:
        row = self.rows[action_id]
        if row["work_id"] != scope.work_id:
            raise BackgroundRunAuthorizationError("Action does not belong to work scope")
        return dict(row)

    def set_decision(self, action_id: str, state: str) -> None:
        self.rows[action_id]["state"] = state


class FakeAuthority:
    def __init__(self, allowed: set[str] | None = None) -> None:
        self.allowed = allowed if allowed is not None else {"read_notes", "publish_brief"}
        self.valid = True

    def validate(self, scope: WorkScope, tool_name: str | None = None, resource: dict | None = None) -> None:
        if not self.valid:
            raise BackgroundRunAuthorizationError("Work scope ownership lost")
        if tool_name is not None and tool_name not in self.allowed:
            raise BackgroundRunAuthorizationError(f"Tool {tool_name} is no longer granted")

    def allowed_tool_names(self, scope: WorkScope) -> frozenset[str]:
        if not self.valid:
            raise BackgroundRunAuthorizationError("Work scope ownership lost")
        return frozenset(self.allowed)


class FakeCredentials:
    def __init__(self, provider_key: str = "openai", model_id: str = "gpt-5.4-mini", secret: str = "sk-secret-must-never-leak") -> None:
        self.provider_key = provider_key
        self.model_id = model_id
        self.secret = secret
        self.requested_providers: list[str] = []

    def selected_provider(self, *, user_id: str, workspace_id: str) -> str:
        return self.provider_key

    def background_access(self, *, user_id: str, workspace_id: str, provider_key: str | None = None):
        chosen = provider_key or self.provider_key
        self.requested_providers.append(chosen)
        return SimpleNamespace(value=self.secret, auth_method="api_key"), self.model_id


class ScriptedSDKModel(Model):
    def __init__(self, steps: list[str] | None = None, *, on_turn=None) -> None:
        self.steps = list(steps or ["write", "complete"])
        self.on_turn = on_turn
        self.seen_inputs: list[object] = []

    async def get_response(self, system_instructions, input, *args, **kwargs):
        self.seen_inputs.append(input)
        if self.on_turn is not None:
            self.on_turn(len(self.seen_inputs), input)
        if isinstance(input, list) and any(
            isinstance(item, dict) and item.get("type") == "function_call_output"
            and "not approved" in str(item.get("output", "")).lower()
            for item in input
        ):
            output = [ResponseOutputMessage(
                id="msg-denied", role="assistant", status="completed", type="message",
                content=[ResponseOutputText(type="output_text", text=_complete_json("Owner denied action", status="blocked"), annotations=[])],
            )]
            return ModelResponse(output=output, usage=Usage(requests=1), response_id="resp-denied")
        step = self.steps.pop(0) if self.steps else "complete"
        if step == "read":
            output = [ResponseFunctionToolCall(
                id="call-read-1", call_id="call-read-1", name="read_notes", type="function_call",
                arguments='{"topic":"q4"}',
            )]
        elif step == "write":
            output = [ResponseFunctionToolCall(
                id="call-write-1", call_id="call-write-1", name="publish_brief", type="function_call",
                arguments='{"card_id":"card-1","text":"hello"}',
            )]
        else:
            output = [ResponseOutputMessage(
                id="msg-done", role="assistant", status="completed", type="message",
                content=[ResponseOutputText(type="output_text", text=_complete_json(), annotations=[])],
            )]
        return ModelResponse(output=output, usage=Usage(requests=1), response_id=f"resp-{len(self.seen_inputs)}")

    async def stream_response(self, *args, **kwargs):
        raise AssertionError("Stream should not be used by offline ScriptedSDKModel")
        yield


def _build_supply(scope: WorkScope, authority: FakeAuthority, effects: list[dict[str, object]],
                  *, on_write=None, on_read=None, calls_used: int = 0, max_calls: int = 8) -> tuple[ToolCatalog, BackgroundToolSupply]:
    catalog = ToolCatalog(
        authorizer=lambda _d, _c: True,
        background_authorizer=lambda d, _c, _a: d.name in authority.allowed,
    )
    catalog.register(ToolDefinition(
        tool_id="test.read_notes.v1", name="read_notes", description="Read notes",
        input_schema={"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"], "additionalProperties": False},
        handler=lambda ctx, args: (on_read(ctx, args) if on_read else ToolInvocationResult('{"notes":"ok"}', {"notes": "ok"})),
        effect_class="read", audiences=frozenset({AgentKind.BACKGROUND}),
    ))

    def write_handler(ctx, args):
        if on_write is not None:
            return on_write(ctx, args)
        effects.append(dict(args))
        return ToolInvocationResult('{"status":"completed"}', {"status": "completed"})

    catalog.register(ToolDefinition(
        tool_id="test.publish_brief.v1", name="publish_brief", description="Publish brief",
        input_schema={"type": "object", "properties": {"card_id": {"type": "string"}, "text": {"type": "string"}},
                      "required": ["card_id", "text"], "additionalProperties": False},
        handler=write_handler, effect_class="write", audiences=frozenset({AgentKind.BACKGROUND}),
    ))
    supply = BackgroundToolSupply(
        catalog=catalog,
        grant=BackgroundToolGrant(
            autonomy=AutonomyProfile.EXPANDED,
            explicit_names=frozenset({"read_notes", "publish_brief"}),
            max_calls=max_calls,
        ),
        calls_used=calls_used,
        background_scope=scope,
        authority=authority,
    )
    return catalog, supply


def test_serialized_fresh_process_resume_executes_approved_action_once_and_excludes_secrets():
    from app.vault_runtime.background_agent.executor import ResumableBackgroundExecutor

    scope = _scope()
    request = _request()
    actions = FakeActionStore()
    authority = FakeAuthority()
    credentials = FakeCredentials(secret="sk-top-secret-sentinel")
    effects: list[dict[str, object]] = []

    _, supply1 = _build_supply(scope, authority, effects)
    executor1 = ResumableBackgroundExecutor(
        credentials=credentials, actions=actions, authority=authority,
        model_factory=lambda *_: ScriptedSDKModel(["write", "complete"]),
    )
    paused = asyncio.run(executor1.execute(scope, request, None, supply1, lambda: False))
    assert paused.state is WorkState.WAITING_APPROVAL
    assert paused.pending_action_id == "act-1"
    assert paused.checkpoint is not None
    assert effects == []

    serialized = json.dumps(paused.checkpoint)
    assert "sk-top-secret-sentinel" not in serialized
    assert "tracing_api_key" not in serialized
    reloaded_checkpoint = json.loads(serialized)

    actions.set_decision("act-1", "approved")
    _, supply2 = _build_supply(scope, authority, effects, calls_used=supply1.calls_used)
    executor2 = ResumableBackgroundExecutor(
        credentials=credentials, actions=actions, authority=authority,
        model_factory=lambda *_: ScriptedSDKModel(["complete"]),
    )
    resumed = asyncio.run(executor2.execute(scope, request, reloaded_checkpoint, supply2, lambda: False))
    assert resumed.state is WorkState.COMPLETED
    assert resumed.output is not None and resumed.output["status"] == "complete"
    assert effects == [{"card_id": "card-1", "text": "hello"}]


def test_checkpoint_cannot_resume_without_an_approval_store():
    from app.vault_runtime.background_agent.executor import ResumableBackgroundExecutor

    scope = _scope()
    request = _request()
    authority = FakeAuthority()
    effects: list[dict[str, object]] = []
    _, supply = _build_supply(scope, authority, effects)
    executor = ResumableBackgroundExecutor(
        credentials=FakeCredentials(), actions=FakeActionStore(), authority=authority,
        model_factory=lambda *_: ScriptedSDKModel(["write", "complete"]),
    )
    paused = asyncio.run(executor.execute(scope, request, None, supply, lambda: False))
    assert paused.state is WorkState.WAITING_APPROVAL

    _, supply = _build_supply(scope, authority, effects)
    executor = ResumableBackgroundExecutor(
        credentials=FakeCredentials(), authority=authority,
        model_factory=lambda *_: ScriptedSDKModel(["complete"]),
    )
    resumed = asyncio.run(executor.execute(scope, request, paused.checkpoint, supply, lambda: False))
    assert resumed.state is WorkState.FAILED
    assert resumed.failure_code == "approval_service_unavailable"
    assert effects == []


def test_session_backed_work_passes_the_bound_session_to_tools():
    from app.vault_runtime.background_agent.coordination_contracts import WorkRequest
    from app.vault_runtime.background_agent.executor import ResumableBackgroundExecutor

    scope = _scope(grant_id=None)
    authority = FakeAuthority()
    sessions = []

    def read(context, arguments):
        sessions.append(context.local_session_id)
        return ToolInvocationResult("Read complete")

    _, supply = _build_supply(scope, authority, [], on_read=read)
    executor = ResumableBackgroundExecutor(
        credentials=FakeCredentials(), authority=authority,
        model_factory=lambda *_: ScriptedSDKModel(["read", "complete"]),
    )
    request = WorkRequest(_request(), grant_id=None, local_session_id="owner-session", destination={})
    outcome = asyncio.run(executor.execute(scope, request, None, supply, lambda: False))
    assert outcome.state is WorkState.COMPLETED
    assert sessions == ["owner-session"]


@pytest.mark.parametrize("decision_state,expected_code", [
    ("denied", "approval_denied"),
    ("expired", "approval_expired"),
])
def test_denied_and_expired_actions_never_execute_side_effect_or_report_completed(decision_state, expected_code):
    from app.vault_runtime.background_agent.executor import ResumableBackgroundExecutor

    scope = _scope()
    request = _request()
    actions = FakeActionStore()
    authority = FakeAuthority()
    credentials = FakeCredentials()
    effects: list[dict[str, object]] = []

    _, supply1 = _build_supply(scope, authority, effects)
    executor1 = ResumableBackgroundExecutor(
        credentials=credentials, actions=actions, authority=authority,
        model_factory=lambda *_: ScriptedSDKModel(["write", "complete"]),
    )
    paused = asyncio.run(executor1.execute(scope, request, None, supply1, lambda: False))
    assert paused.state is WorkState.WAITING_APPROVAL
    assert paused.pending_action_id == "act-1"

    actions.set_decision("act-1", decision_state)
    _, supply2 = _build_supply(scope, authority, effects, calls_used=supply1.calls_used)
    # Even if a model tries to output status="complete", a denied/expired approval must fail.
    executor2 = ResumableBackgroundExecutor(
        credentials=credentials, actions=actions, authority=authority,
        model_factory=lambda *_: ScriptedSDKModel(["complete"]),
    )
    resumed = asyncio.run(executor2.execute(scope, request, json.loads(json.dumps(paused.checkpoint)), supply2, lambda: False))
    assert resumed.state is WorkState.FAILED
    assert resumed.failure_code == expected_code
    assert effects == []


def test_checkpoint_rejects_model_provider_sdk_scope_size_and_revoked_tool_mismatch():
    from app.vault_runtime.background_agent.executor import ResumableBackgroundExecutor

    scope = _scope()
    request = _request()
    actions = FakeActionStore()
    authority = FakeAuthority()
    credentials = FakeCredentials()
    effects: list[dict[str, object]] = []

    _, supply1 = _build_supply(scope, authority, effects)
    executor1 = ResumableBackgroundExecutor(
        credentials=credentials, actions=actions, authority=authority,
        model_factory=lambda *_: ScriptedSDKModel(["write", "complete"]),
    )
    paused = asyncio.run(executor1.execute(scope, request, None, supply1, lambda: False))
    actions.set_decision("act-1", "approved")
    base_checkpoint = json.loads(json.dumps(paused.checkpoint))

    # 1. Model pin mismatch
    bad_model_creds = FakeCredentials(model_id="different-model")
    _, supply_m = _build_supply(scope, authority, effects)
    exec_m = ResumableBackgroundExecutor(
        credentials=bad_model_creds, actions=actions, authority=authority,
        model_factory=lambda *_: ScriptedSDKModel(["complete"]),
    )
    out_m = asyncio.run(exec_m.execute(scope, request, base_checkpoint, supply_m, lambda: False))
    assert out_m.state is WorkState.FAILED and out_m.failure_code == "invalid_checkpoint"
    assert effects == []

    # 2. Scope mismatch (different worker_generation)
    wrong_scope = _scope(worker_generation=2)
    _, supply_s = _build_supply(wrong_scope, authority, effects)
    out_s = asyncio.run(executor1.execute(wrong_scope, request, base_checkpoint, supply_s, lambda: False))
    assert out_s.state is WorkState.FAILED and out_s.failure_code == "invalid_checkpoint"
    assert effects == []

    # 3. Oversized checkpoint rejected
    huge_checkpoint = dict(base_checkpoint, padding="x" * 300_000)
    _, supply_h = _build_supply(scope, authority, effects)
    out_h = asyncio.run(executor1.execute(scope, request, huge_checkpoint, supply_h, lambda: False))
    assert out_h.state is WorkState.FAILED and out_h.failure_code == "invalid_checkpoint"
    assert effects == []

    # 4. Stale approved tool removed from current authorized supply before resume
    authority.allowed = {"read_notes"}
    _, supply_revoked = _build_supply(scope, authority, effects)
    out_r = asyncio.run(executor1.execute(scope, request, base_checkpoint, supply_revoked, lambda: False))
    assert out_r.state is WorkState.FAILED and out_r.failure_code in {"tool_not_granted", "not_granted"}
    assert effects == []


def test_cumulative_budgets_persist_across_restarts_and_timeout_stops_before_new_effect():
    from app.vault_runtime.background_agent.executor import ResumableBackgroundExecutor

    now = [100.0]
    scope = _scope()
    request = _request(max_seconds=10, max_model_turns=3, max_tool_calls=2)
    actions = FakeActionStore()
    authority = FakeAuthority()
    credentials = FakeCredentials()
    effects: list[dict[str, object]] = []

    def advance_on_turn(turn_no: int, _input: object) -> None:
        now[0] += 4.0

    _, supply1 = _build_supply(scope, authority, effects, max_calls=2)
    executor1 = ResumableBackgroundExecutor(
        credentials=credentials, actions=actions, authority=authority,
        model_factory=lambda *_: ScriptedSDKModel(["read", "write", "complete"], on_turn=advance_on_turn),
        clock=lambda: now[0],
    )
    paused = asyncio.run(executor1.execute(scope, request, None, supply1, lambda: False))
    assert paused.state is WorkState.WAITING_APPROVAL
    budget = paused.checkpoint["budget"]
    assert budget["model_turns"] == 2
    assert budget["tool_calls"] == 1
    assert budget["active_seconds"] == pytest.approx(8.0)

    # Waiting 500 seconds for the human does not consume active_seconds:
    now[0] += 500.0
    actions.set_decision("act-1", "approved")

    # Resuming when another 4s model turn pushes cumulative active time (8 + 4 = 12s > 10s max_seconds)
    # stops before a new effect can commit:
    _, supply2 = _build_supply(scope, authority, effects, calls_used=supply1.calls_used, max_calls=2)
    executor2 = ResumableBackgroundExecutor(
        credentials=credentials, actions=actions, authority=authority,
        model_factory=lambda *_: ScriptedSDKModel(["complete"], on_turn=advance_on_turn),
        clock=lambda: now[0],
    )
    timed_out = asyncio.run(executor2.execute(scope, request, paused.checkpoint, supply2, lambda: False))
    assert timed_out.state is WorkState.FAILED
    assert timed_out.failure_code == "run_timeout"

    # Also test timeout BEFORE the approved tool effect even starts:
    exhausted_checkpoint = json.loads(json.dumps(paused.checkpoint))
    exhausted_checkpoint["budget"]["active_seconds"] = 10.0
    effects.clear()
    _, supply3 = _build_supply(scope, authority, effects, calls_used=1, max_calls=2)
    before_effect = asyncio.run(executor2.execute(scope, request, exhausted_checkpoint, supply3, lambda: False))
    assert before_effect.state is WorkState.FAILED
    assert before_effect.failure_code == "run_timeout"
    assert effects == []


def test_cancellation_during_generation_or_read_is_cancelled_but_in_flight_write_records_unknown():
    from app.vault_runtime.background_agent.executor import ResumableBackgroundExecutor

    scope = _scope()
    request = _request()
    actions = FakeActionStore()
    authority = FakeAuthority()
    credentials = FakeCredentials()
    effects: list[dict[str, object]] = []
    cancel_flag = [False]

    # 1. Cancel during read tool I/O -> WorkState.CANCELLED (no external write effect in flight)
    def cancel_on_read(_ctx, _args):
        cancel_flag[0] = True
        return ToolInvocationResult('{"notes":"ok"}', {"notes": "ok"})

    _, supply_read = _build_supply(scope, authority, effects, on_read=cancel_on_read)
    exec_read = ResumableBackgroundExecutor(
        credentials=credentials, actions=actions, authority=authority,
        model_factory=lambda *_: ScriptedSDKModel(["read", "complete"]),
    )
    out_read = asyncio.run(exec_read.execute(scope, request, None, supply_read, lambda: cancel_flag[0]))
    assert out_read.state is WorkState.CANCELLED
    assert effects == []

    # 2. Cancel during an in-flight approved write effect that cannot be undone -> WorkState.UNKNOWN
    cancel_flag[0] = False
    _, supply_prep = _build_supply(scope, authority, effects)
    exec_prep = ResumableBackgroundExecutor(
        credentials=credentials, actions=actions, authority=authority,
        model_factory=lambda *_: ScriptedSDKModel(["write", "complete"]),
    )
    paused = asyncio.run(exec_prep.execute(scope, request, None, supply_prep, lambda: False))
    actions.set_decision("act-1", "approved")

    def write_cancels_mid_flight(_ctx, args):
        effects.append(dict(args))
        cancel_flag[0] = True
        raise RuntimeError("remote_connection_reset_after_send")

    _, supply_write = _build_supply(scope, authority, effects, on_write=write_cancels_mid_flight)
    exec_write = ResumableBackgroundExecutor(
        credentials=credentials, actions=actions, authority=authority,
        model_factory=lambda *_: ScriptedSDKModel(["complete"]),
    )
    out_write = asyncio.run(exec_write.execute(scope, request, paused.checkpoint, supply_write, lambda: cancel_flag[0]))
    assert out_write.state is WorkState.UNKNOWN
    assert len(effects) == 1


def test_lost_ownership_before_result_commit_refuses_to_finalize():
    from app.vault_runtime.background_agent.executor import ResumableBackgroundExecutor

    scope = _scope()
    request = _request()
    actions = FakeActionStore()
    authority = FakeAuthority()
    credentials = FakeCredentials()
    effects: list[dict[str, object]] = []

    def lose_ownership_on_final_turn(_turn_no: int, _input: object) -> None:
        authority.valid = False

    _, supply = _build_supply(scope, authority, effects)
    executor = ResumableBackgroundExecutor(
        credentials=credentials, actions=actions, authority=authority,
        model_factory=lambda *_: ScriptedSDKModel(["complete"], on_turn=lose_ownership_on_final_turn),
    )
    with pytest.raises(BackgroundRunAuthorizationError):
        asyncio.run(executor.execute(scope, request, None, supply, lambda: False))


def test_gemini_provider_saves_and_resumes_wait_state_without_silent_provider_switch():
    from app.vault_runtime.background_agent.executor import ResumableBackgroundExecutor

    scope = _scope()
    request = _request()
    actions = FakeActionStore()
    authority = FakeAuthority()
    credentials = FakeCredentials(provider_key="gemini", model_id="gemini-2.5-pro", secret="gemini-secret-key")
    effects: list[dict[str, object]] = []
    gemini_calls: list[dict[str, object]] = []

    def fake_gemini_transport(url: str, headers: dict[str, str], body: dict[str, object]) -> dict[str, object]:
        gemini_calls.append({"url": url, "headers": headers, "body": body})
        contents = body["contents"]
        last = contents[-1]
        parts = last.get("parts", [])
        if any(isinstance(p, dict) and "functionResponse" in p for p in parts):
            resp = parts[0]["functionResponse"]["response"]
            if resp.get("isError"):
                text = _complete_json("Denied on Gemini", status="blocked")
            else:
                text = _complete_json("Completed on Gemini", status="complete")
            return {"candidates": [{"content": {"parts": [{"text": text}]}}]}
        return {"candidates": [{"content": {"parts": [{"functionCall": {"name": "publish_brief", "args": {"card_id": "g-1", "text": "gemini"}}}]}}]}

    _, supply1 = _build_supply(scope, authority, effects)
    executor = ResumableBackgroundExecutor(
        credentials=credentials, actions=actions, authority=authority,
        gemini_transport=fake_gemini_transport,
    )
    paused = asyncio.run(executor.execute(scope, request, None, supply1, lambda: False))
    assert paused.state is WorkState.WAITING_APPROVAL
    assert paused.checkpoint["provider_key"] == "gemini"
    assert paused.checkpoint["model_id"] == "gemini-2.5-pro"
    assert "gemini-secret-key" not in json.dumps(paused.checkpoint)
    assert credentials.requested_providers == ["gemini"]
    assert effects == []

    # Cannot resume a Gemini checkpoint on OpenAI (no cross-provider loading):
    openai_executor = ResumableBackgroundExecutor(
        credentials=FakeCredentials(provider_key="openai", model_id="gpt-5.4-mini"),
        actions=actions, authority=authority,
    )
    cross = asyncio.run(openai_executor.execute(scope, request, paused.checkpoint, supply1, lambda: False))
    assert cross.state is WorkState.FAILED and cross.failure_code == "invalid_checkpoint"

    # Resume on Gemini after approval:
    actions.set_decision(paused.pending_action_id, "approved")
    _, supply2 = _build_supply(scope, authority, effects, calls_used=supply1.calls_used)
    resumed = asyncio.run(executor.execute(scope, request, json.loads(json.dumps(paused.checkpoint)), supply2, lambda: False))
    assert resumed.state is WorkState.COMPLETED
    assert effects == [{"card_id": "g-1", "text": "gemini"}]


def test_chatgpt_oauth_background_run_uses_sdk_stream():
    from openai.types.responses import Response, ResponseCompletedEvent

    from app.vault_runtime.background_agent.coordination_contracts import WorkRequest
    from app.vault_runtime.background_agent.executor import ResumableBackgroundExecutor

    class OAuthCredentials(FakeCredentials):
        def background_access(self, **kwargs):
            credential, model_id = super().background_access(**kwargs)
            credential.auth_method = "chatgpt_oauth"
            return credential, model_id

    class StreamOnlyModel(ScriptedSDKModel):
        async def get_response(self, *args, **kwargs):
            raise AssertionError("The OAuth endpoint requires streaming")

        async def stream_response(self, instructions, input, *args, **kwargs):
            result = await super().get_response(instructions, input, *args, **kwargs)
            yield ResponseCompletedEvent(
                type="response.completed", sequence_number=1,
                response=Response.model_construct(id=result.response_id, output=result.output, usage=None),
            )

    scope = _scope(grant_id=None)
    authority = FakeAuthority()
    _, supply = _build_supply(scope, authority, [])
    model = StreamOnlyModel(["complete"])
    executor = ResumableBackgroundExecutor(
        credentials=OAuthCredentials(), authority=authority, model_factory=lambda *_: model,
    )
    request = WorkRequest(_request(), grant_id=None, local_session_id="owner-session", destination={})
    outcome = asyncio.run(executor.execute(scope, request, None, supply, lambda: False))
    assert outcome.state is WorkState.COMPLETED, outcome
    assert len(model.seen_inputs) == 1
