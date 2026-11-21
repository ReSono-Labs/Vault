"""Resumable Background Agent executor across approval waits and process restarts (Task 5)."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
from hashlib import sha256
import json
from time import monotonic
from types import SimpleNamespace
from typing import Any

from agents import (
    Agent, AgentOutputSchema, FunctionTool, ModelSettings, RunConfig, RunHooks, Runner, RunState,
    set_tracing_disabled,
)
import httpx
from openai.types.shared import Reasoning
import psycopg
from psycopg.types.json import Jsonb

from app.vault_runtime.background_agent.action_bridge import ROUTES, _phase
from app.vault_runtime.background_agent.checkpoints import (
    GEMINI_ADAPTER_VERSION,
    MAX_CHECKPOINT_BYTES,
    SDK_VERSION,
    approval_fingerprint,
    build_sdk_checkpoint,
    validate_sdk_checkpoint,
)
from app.vault_runtime.background_agent.contracts import BackgroundRunRequest
from app.vault_runtime.background_agent.coordination_contracts import (
    ExecutionOutcome,
    WorkRequest,
    WorkScope,
    WorkState,
)
from app.vault_runtime.background_agent.agent_brief import (
    background_input,
    background_instructions,
    request_from_payload as _request_from_payload,
    strict_compatible,
)
from app.vault_runtime.background_agent.output_contract import BackgroundAgentOutput
from app.vault_runtime.background_agent.errors import (
    BackgroundRunAuthorizationError,
    BackgroundRunConflictError,
)
from app.vault_runtime.background_agent.run_events import RunEventWriter, reasoning_summaries
from app.vault_runtime.background_agent.sdk_runner import build_openai_sdk_provider
from app.vault_runtime.background_agent.tool_supply import (
    BackgroundToolGrant,
    BackgroundToolSupply,
    ToolBudgetExceeded,
)
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.definitions import ToolInvocationContext, ToolInvocationResult
from app.vault_runtime.tools.strict_json import parse_json_object_bytes


class _RunCancelled(Exception):
    pass


class _BudgetExceeded(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _UncertainEffectError(Exception):
    def __init__(self, code: str = "effect_outcome_unknown") -> None:
        super().__init__(code)
        self.code = code


def _coerce_request(request: BackgroundRunRequest | WorkRequest | dict[str, object]) -> BackgroundRunRequest:
    if isinstance(request, BackgroundRunRequest):
        return request
    if isinstance(request, WorkRequest):
        return request.request
    if isinstance(request, dict):
        inner = request.get("request") if isinstance(request.get("request"), dict) else request
        if isinstance(inner, BackgroundRunRequest):
            return inner
        if isinstance(inner, dict):
            return _request_from_payload(inner)
    raise ValueError("Expected BackgroundRunRequest, WorkRequest, or request payload")


class ResumableBackgroundExecutor:
    """Executes and resumes delegated background work through trusted approval checkpoints."""

    def __init__(
        self,
        *,
        credentials: Any = None,
        memories: Any = None,
        actions: Any = None,
        authority: Any = None,
        catalog: Any = None,
        database_url: str | None = None,
        jobs: Any = None,
        model_factory: Callable[..., Any] | None = None,
        gemini_transport: Callable[[str, dict[str, str], dict[str, object]], Any] | None = None,
        clock: Callable[[], float] = monotonic,
        sdk_version: str = SDK_VERSION,
    ) -> None:
        self._credentials = credentials
        self._memories = memories
        self._actions = actions
        self._authority = authority
        self._catalog = catalog
        self._database_url = database_url
        self._jobs = jobs
        self._model_factory = model_factory
        self._gemini_transport = gemini_transport
        self._clock = clock
        self._sdk_version = sdk_version
        # Reasoning summaries and phase evidence for the Background work detail (owner decision 5-D).
        self._run_events = RunEventWriter(database_url=database_url) if database_url else None
        # SkillActivation (composition sets it): the run owner's granted Skill catalog.
        self.skills: Any = None

    def attach_jobs(self, jobs: Any) -> None:
        self._jobs = jobs

    def _skill_catalog(self, scope: Any, tool_names: set[str]) -> str:
        """Granted Skill catalog for this run, only when the run is supplied the loader."""
        if self.skills is None or "load_agent_skill" not in tool_names:
            return ""
        text = self.skills.catalog_instructions(
            user_id=scope.user_id, workspace_id=scope.workspace_id, agent=AgentKind.BACKGROUND,
        )
        return "\n\n" + text if text else ""

    async def __call__(self, attempt: Any) -> ExecutionOutcome:
        """Adapter for BackgroundJobs._dispatch(attempt)."""
        run_request = _coerce_request(attempt.request)
        if self._catalog is None or self._authority is None:
            raise RuntimeError("ResumableBackgroundExecutor requires catalog and authority for job attempts")
        try:
            supply = BackgroundToolSupply(
                catalog=self._catalog,
                grant=BackgroundToolGrant(
                    autonomy=run_request.autonomy,
                    explicit_names=frozenset(run_request.requested_tool_names),
                    max_calls=run_request.limits.max_tool_calls,
                ),
                calls_used=attempt.tool_calls,
                background_scope=attempt.scope,
                authority=self._authority,
            )
        except BackgroundRunAuthorizationError:
            return ExecutionOutcome(WorkState.FAILED, failure_code="not_granted")

        outcome = await self.run_attempt(attempt, attempt.request, supply)
        if self._database_url is not None and attempt.scope.worker_id is not None:
            self._sync_worker_session_checkpoint(attempt.scope, outcome.checkpoint)
        return outcome

    async def run_attempt(self, attempt: Any, request, supply: BackgroundToolSupply) -> ExecutionOutcome:
        checkpoint = dict(attempt.checkpoint) if isinstance(attempt.checkpoint, dict) else None
        if checkpoint is not None:
            budget = dict(checkpoint.get("budget") or {})
            budget["tool_calls"] = max(int(budget.get("tool_calls", 0)), int(attempt.tool_calls))
            budget["model_turns"] = max(int(budget.get("model_turns", 0)), int(attempt.model_turns))
            budget["active_seconds"] = max(float(budget.get("active_seconds", 0.0)), float(attempt.active_seconds))
            checkpoint["budget"] = budget

        prior_tools = int(attempt.tool_calls)
        prior_turns = int(attempt.model_turns)
        last_turns = [prior_turns]

        def cancel_requested() -> bool:
            if self._jobs is not None:
                try:
                    self._jobs.validate_attempt(attempt)
                except BackgroundRunAuthorizationError:
                    return True
            return False

        try:
            outcome = await self.execute(
                attempt.scope,
                request,
                checkpoint,
                supply,
                cancel_requested,
                _initial_turns=prior_turns,
                _initial_seconds=float(attempt.active_seconds),
                _turn_counter_out=last_turns,
            )
        except BackgroundRunAuthorizationError:
            return ExecutionOutcome(WorkState.FAILED, failure_code="not_granted")

        delta_tools = max(0, supply.calls_used - prior_tools)
        delta_turns = max(0, last_turns[0] - prior_turns)
        if self._jobs is not None and (delta_tools or delta_turns):
            self._jobs.debit(attempt, tool_calls=delta_tools, model_turns=delta_turns)
        return outcome

    async def execute(
        self,
        scope: WorkScope,
        request: BackgroundRunRequest | WorkRequest | dict[str, object],
        checkpoint: dict[str, object] | None,
        tools: BackgroundToolSupply,
        cancel_requested: Callable[[], bool],
        *,
        _initial_turns: int = 0,
        _initial_seconds: float = 0.0,
        _turn_counter_out: list[int] | None = None,
    ) -> ExecutionOutcome:
        run_request = _coerce_request(request)
        self._validate_scope(scope)
        if checkpoint is not None and self._actions is None:
            return ExecutionOutcome(WorkState.FAILED, failure_code="approval_service_unavailable")
        local_session_id = None
        if scope.grant_id is None:
            if isinstance(request, WorkRequest):
                local_session_id = request.local_session_id
            elif isinstance(request, dict):
                local_session_id = request.get("local_session_id")
            if not isinstance(local_session_id, str) or not local_session_id.strip():
                return ExecutionOutcome(WorkState.FAILED, failure_code="not_granted")

        def tool_context(call_id: str) -> ToolInvocationContext:
            return ToolInvocationContext(
                agent=AgentKind.BACKGROUND, user_id=scope.user_id, workspace_id=scope.workspace_id,
                tool_call_id=call_id, local_session_id=local_session_id,
                execution_id=run_request.run_id, background_scope=scope,
            )

        provider_key, credential_value, auth_method, model_id = self._resolve_provider(scope)
        adapter_version = GEMINI_ADAPTER_VERSION if provider_key == "gemini" else self._sdk_version

        prior_turns = _initial_turns
        prior_seconds = _initial_seconds
        prior_tools = tools.calls_used
        if checkpoint is not None:
            try:
                validate_sdk_checkpoint(
                    checkpoint,
                    provider_key=provider_key,
                    model_id=model_id,
                    sdk_version=adapter_version,
                    scope=scope,
                    max_bytes=MAX_CHECKPOINT_BYTES,
                )
            except ValueError:
                return ExecutionOutcome(WorkState.FAILED, failure_code="invalid_checkpoint")
            saved_budget = checkpoint.get("budget")
            if isinstance(saved_budget, dict):
                prior_turns = max(prior_turns, int(saved_budget.get("model_turns", 0)))
                prior_seconds = max(prior_seconds, float(saved_budget.get("active_seconds", 0.0)))
                prior_tools = max(prior_tools, int(saved_budget.get("tool_calls", 0)))
                try:
                    tools.sync_calls_used(prior_tools)
                except ValueError:
                    return ExecutionOutcome(WorkState.FAILED, failure_code="tool_budget_exceeded")

        if _turn_counter_out is not None:
            _turn_counter_out[0] = prior_turns

        if provider_key == "gemini":
            outcome = await self._execute_gemini(
                scope=scope,
                request=run_request,
                checkpoint=checkpoint,
                tools=tools,
                tool_context=tool_context,
                cancel_requested=cancel_requested,
                api_key=credential_value,
                model_id=model_id,
                oauth=(auth_method == "gemini_oauth"),
                prior_turns=prior_turns,
                prior_seconds=prior_seconds,
                turn_counter_out=_turn_counter_out,
            )
            await self._record_evidence(scope, run_request, outcome)
            return outcome

        outcome = await self._execute_sdk(
            scope=scope,
            request=run_request,
            checkpoint=checkpoint,
            tools=tools,
            tool_context=tool_context,
            cancel_requested=cancel_requested,
            provider_key=provider_key,
            api_key=credential_value,
            auth_method=auth_method,
            model_id=model_id,
            prior_turns=prior_turns,
            prior_seconds=prior_seconds,
            turn_counter_out=_turn_counter_out,
        )
        await self._record_evidence(scope, run_request, outcome)
        return outcome

    async def _record_events(self, write: Callable[..., None], **kwargs: Any) -> None:
        if self._run_events is None:
            return
        try:
            await asyncio.to_thread(write, **kwargs)
        except Exception as exc:
            # The run itself does not depend on its activity record.
            logging.getLogger(__name__).warning("background_run_event_failed error=%s", type(exc).__name__)

    async def _record_evidence(self, scope: WorkScope, request: BackgroundRunRequest, outcome: ExecutionOutcome) -> None:
        if self._run_events is not None and outcome.output is not None:
            await self._record_events(self._run_events.evidence, user_id=scope.user_id,
                                      workspace_id=scope.workspace_id, run_id=request.run_id, output=outcome.output)

    async def _execute_sdk(
        self,
        *,
        scope: WorkScope,
        request: BackgroundRunRequest,
        checkpoint: dict[str, object] | None,
        tools: BackgroundToolSupply,
        tool_context: Callable[[str], ToolInvocationContext],
        cancel_requested: Callable[[], bool],
        provider_key: str,
        api_key: str,
        auth_method: str,
        model_id: str,
        prior_turns: int,
        prior_seconds: float,
        turn_counter_out: list[int] | None,
    ) -> ExecutionOutcome:
        set_tracing_disabled(True)
        started_at = self._clock()
        turns_used = [prior_turns]
        uncertain_effect = [False]
        write_in_flight = [False]
        control_error: list[BaseException | None] = [None]
        cached_results: dict[str, ToolInvocationResult] = {}
        interrupted_meta: dict[str, dict[str, str]] = {}

        def elapsed_active() -> float:
            return prior_seconds + max(0.0, float(self._clock() - started_at))

        def record_and_raise(exc: BaseException) -> None:
            if control_error[0] is None:
                control_error[0] = exc
            raise exc

        def check_step_guards(*, tool_name: str | None = None) -> None:
            if control_error[0] is not None:
                raise control_error[0]
            if cancel_requested():
                if write_in_flight[0] or uncertain_effect[0]:
                    record_and_raise(_UncertainEffectError("cancelled_during_effect"))
                record_and_raise(_RunCancelled())
            try:
                self._validate_scope(scope, tool_name=tool_name)
            except BackgroundRunAuthorizationError as exc:
                record_and_raise(exc)
            if elapsed_active() >= request.limits.max_seconds:
                record_and_raise(_BudgetExceeded("run_timeout"))

        resumed_call_id = str(checkpoint.get("call_id") or "") if checkpoint else ""
        resumed_action_id = str(checkpoint.get("pending_action_id") or "") if checkpoint else ""
        resumed_tool_name = str(checkpoint.get("tool_name") or "") if checkpoint else ""
        resumed_mode = str(checkpoint.get("action_mode") or "custom_write") if checkpoint else ""
        rejection_failure_code: str | None = None

        if checkpoint is not None:
            if not resumed_action_id or not resumed_tool_name:
                return ExecutionOutcome(WorkState.FAILED, failure_code="invalid_checkpoint")
            try:
                self._validate_scope(scope, tool_name=resumed_tool_name)
            except BackgroundRunAuthorizationError:
                return ExecutionOutcome(WorkState.FAILED, failure_code="tool_not_granted")
            if not tools.has_tool(resumed_tool_name):
                return ExecutionOutcome(WorkState.FAILED, failure_code="tool_not_granted")

            decision_state = self._resolve_action_decision(scope, resumed_action_id)
            if decision_state == "pending":
                return ExecutionOutcome(
                    WorkState.WAITING_APPROVAL,
                    checkpoint=checkpoint,
                    pending_action_id=resumed_action_id,
                )
            if decision_state == "approved":
                try:
                    check_step_guards(tool_name=resumed_tool_name)
                    if resumed_mode == "custom_write" and tools.calls_used >= request.limits.max_tool_calls:
                        raise _BudgetExceeded("tool_budget_exceeded")
                except _RunCancelled:
                    return ExecutionOutcome(WorkState.CANCELLED, failure_code="cancelled")
                except _BudgetExceeded as exc:
                    return ExecutionOutcome(WorkState.FAILED, failure_code=exc.code)
                except BackgroundRunAuthorizationError:
                    return ExecutionOutcome(WorkState.FAILED, failure_code="not_granted")
            elif decision_state == "denied":
                rejection_failure_code = "approval_denied"
            elif decision_state == "expired":
                rejection_failure_code = "approval_expired"
            else:
                return ExecutionOutcome(WorkState.FAILED, failure_code=f"action_{decision_state}")

        memories = (
            tuple(checkpoint["memories"])
            if checkpoint is not None and isinstance(checkpoint.get("memories"), list)
            else await asyncio.to_thread(self._memory_context, request, scope=scope)
        )

        function_tools = [
            self._build_sdk_tool(
                definition,
                scope=scope,
                request=request,
                tools=tools,
                tool_context=tool_context,
                cancel_requested=cancel_requested,
                check_step_guards=check_step_guards,
                cached_results=cached_results,
                interrupted_meta=interrupted_meta,
                resumed_call_id=resumed_call_id,
                resumed_action_id=resumed_action_id,
                resumed_mode=resumed_mode,
                write_in_flight=write_in_flight,
                uncertain_effect=uncertain_effect,
                record_and_raise=record_and_raise,
            )
            for definition in tools.definitions()
        ]

        base_url = (
            "https://api.x.ai/v1" if provider_key == "xai" else
            "https://chatgpt.com/backend-api/codex" if auth_method == "chatgpt_oauth" else None
        )
        client = None
        provider = None
        if self._model_factory is not None:
            model_obj = self._model_factory(provider_key, model_id, api_key, base_url)
            run_config = RunConfig(tracing_disabled=True)
        else:
            client, provider = build_openai_sdk_provider(api_key=api_key, base_url=base_url)
            model_obj = model_id
            run_config = RunConfig(model_provider=provider, tracing_disabled=True)

        executor = self

        class StepHooks(RunHooks):
            async def on_llm_start(self, _ctx, _agent, _system_prompt, _input_items) -> None:
                check_step_guards()
                if turns_used[0] >= request.limits.max_model_turns:
                    raise _BudgetExceeded("max_model_turns_exceeded")

            async def on_llm_end(self, _ctx, _agent, _response) -> None:
                turns_used[0] += 1
                if turn_counter_out is not None:
                    turn_counter_out[0] = turns_used[0]
                summaries = reasoning_summaries(_response)
                if summaries and executor._run_events is not None:
                    await executor._record_events(executor._run_events.reasoning, user_id=scope.user_id,
                                                  workspace_id=scope.workspace_id, run_id=request.run_id,
                                                  summaries=summaries)
                check_step_guards()

        skill_catalog = await asyncio.to_thread(
            self._skill_catalog, scope, {str(item["name"]) for item in tools.definitions()},
        )
        agent = Agent(
            name="ReSono Background Agent",
            instructions=background_instructions(request) + skill_catalog,
            model=model_obj,
            model_settings=ModelSettings(
                reasoning=Reasoning(effort="medium", summary="auto"),
                store=False if base_url else None,
            ) if isinstance(model_obj, str) else ModelSettings(),
            tools=function_tools,
            # The SDK enforces the result's exact shape (structured output). Without it the model
            # guessed field names and status words from the prose, and Vault rejected the run.
            output_type=AgentOutputSchema(BackgroundAgentOutput, strict_json_schema=True),
        )
        safe_context = {"user_id": scope.user_id, "workspace_id": scope.workspace_id, "work_id": scope.work_id}
        remaining_turns = max(1, request.limits.max_model_turns - turns_used[0] + 1)

        async def run_model(agent, input_value, **options):
            if auth_method != "chatgpt_oauth":
                return await Runner.run(agent, input_value, **options)
            streamed = Runner.run_streamed(agent, input=input_value, **options)
            try:
                async for _event in streamed.stream_events():
                    check_step_guards()
            except BaseException:
                streamed.cancel(mode="immediate")
                raise
            return streamed

        try:
            if checkpoint is None:
                result = await run_model(
                    agent,
                    background_input(request, memories=memories),
                    context=safe_context,
                    run_config=run_config,
                    max_turns=remaining_turns,
                    hooks=StepHooks(),
                )
            else:
                state = await RunState.from_json(
                    agent,
                    checkpoint["state"],
                    context_override=safe_context,
                )
                pending = await run_model(agent, state, run_config=run_config, max_turns=remaining_turns)
                if len(pending.interruptions) != 1:
                    return ExecutionOutcome(WorkState.FAILED, failure_code="invalid_checkpoint")
                interruption = pending.interruptions[0]
                if approval_fingerprint(interruption) != checkpoint.get("approval_hash"):
                    return ExecutionOutcome(WorkState.FAILED, failure_code="invalid_checkpoint")
                state = pending.to_state()
                if rejection_failure_code is None:
                    state.approve(interruption)
                else:
                    state.reject(interruption)
                result = await run_model(
                    agent,
                    state,
                    run_config=run_config,
                    max_turns=max(1, request.limits.max_model_turns - turns_used[0] + 1),
                    hooks=StepHooks(),
                )

            if control_error[0] is not None:
                raise control_error[0]

            if result.interruptions:
                interruption = result.interruptions[0]
                call_id = str(interruption.raw_item.call_id)
                tool_name = str(interruption.raw_item.name)
                meta = interrupted_meta.get(call_id) or {}
                action_id = meta.get("action_id")
                if not action_id:
                    return ExecutionOutcome(WorkState.FAILED, failure_code="missing_prepared_action")
                saved_checkpoint = build_sdk_checkpoint(
                    provider_key=provider_key,
                    model_id=model_id,
                    sdk_version=self._sdk_version,
                    approval_hash=approval_fingerprint(interruption),
                    state=result.to_state().to_json(include_tracing_api_key=False),
                    scope=scope,
                    pending_action_id=action_id,
                    tool_name=tool_name,
                    call_id=call_id,
                    action_mode=meta.get("mode", "custom_write"),
                    budget={
                        "model_turns": turns_used[0],
                        "tool_calls": tools.calls_used,
                        "active_seconds": round(elapsed_active(), 6),
                    },
                    memories=memories,
                    max_bytes=MAX_CHECKPOINT_BYTES,
                )
                return ExecutionOutcome(
                    WorkState.WAITING_APPROVAL,
                    checkpoint=saved_checkpoint,
                    pending_action_id=action_id,
                )

            # Revalidate ownership and cancellation before committing final result:
            check_step_guards()
            return self._finalize_output(result.final_output, rejection_failure_code=rejection_failure_code)

        except BackgroundRunAuthorizationError:
            raise
        except _UncertainEffectError as exc:
            return ExecutionOutcome(WorkState.UNKNOWN, failure_code=exc.code)
        except _RunCancelled:
            if uncertain_effect[0] or write_in_flight[0]:
                return ExecutionOutcome(WorkState.UNKNOWN, failure_code="cancelled_during_effect")
            return ExecutionOutcome(WorkState.CANCELLED, failure_code="cancelled")
        except (_BudgetExceeded, ToolBudgetExceeded) as exc:
            if uncertain_effect[0] or write_in_flight[0]:
                return ExecutionOutcome(WorkState.UNKNOWN, failure_code="effect_outcome_unknown")
            code = exc.code if isinstance(exc, _BudgetExceeded) else "tool_budget_exceeded"
            return ExecutionOutcome(WorkState.FAILED, failure_code=code, failure_message=str(exc)[:2048])
        except asyncio.CancelledError:
            if uncertain_effect[0] or write_in_flight[0]:
                return ExecutionOutcome(WorkState.UNKNOWN, failure_code="cancelled_during_effect")
            return ExecutionOutcome(WorkState.CANCELLED, failure_code="cancelled")
        except Exception as exc:
            if control_error[0] is not None and control_error[0] is not exc:
                stored_err = control_error[0]
                if isinstance(stored_err, BackgroundRunAuthorizationError):
                    raise stored_err
                if isinstance(stored_err, _UncertainEffectError):
                    return ExecutionOutcome(WorkState.UNKNOWN, failure_code=stored_err.code)
                if isinstance(stored_err, _RunCancelled):
                    if uncertain_effect[0] or write_in_flight[0]:
                        return ExecutionOutcome(WorkState.UNKNOWN, failure_code="cancelled_during_effect")
                    return ExecutionOutcome(WorkState.CANCELLED, failure_code="cancelled")
                if isinstance(stored_err, (_BudgetExceeded, ToolBudgetExceeded)):
                    code = stored_err.code if isinstance(stored_err, _BudgetExceeded) else "tool_budget_exceeded"
                    return ExecutionOutcome(WorkState.FAILED, failure_code=code, failure_message=str(stored_err)[:2048])
            if uncertain_effect[0] or write_in_flight[0]:
                return ExecutionOutcome(WorkState.UNKNOWN, failure_code="effect_outcome_unknown")
            return ExecutionOutcome(WorkState.FAILED, failure_code=type(exc).__name__.lower()[:120],
                                    failure_message=str(exc)[:2048])
        finally:
            if provider is not None:
                await provider.aclose()
            if client is not None:
                await client.close()

    def _build_sdk_tool(
        self,
        definition: dict[str, object],
        *,
        scope: WorkScope,
        request: BackgroundRunRequest,
        tools: BackgroundToolSupply,
        tool_context: Callable[[str], ToolInvocationContext],
        cancel_requested: Callable[[], bool],
        check_step_guards: Callable[..., None],
        cached_results: dict[str, ToolInvocationResult],
        interrupted_meta: dict[str, dict[str, str]],
        resumed_call_id: str,
        resumed_action_id: str,
        resumed_mode: str,
        write_in_flight: list[bool],
        uncertain_effect: list[bool],
        record_and_raise: Callable[[BaseException], None],
    ) -> FunctionTool:
        name = str(definition["name"])
        schema = definition["inputSchema"]
        is_write = tools.effect_class(name) in {"write", "delete"}

        def make_context(call_id: str) -> ToolInvocationContext:
            return tool_context(call_id or f"{request.run_id}:{name}")

        async def check_needs_approval(_run_ctx: Any, params: dict[str, Any], call_id: str) -> bool:
            check_step_guards(tool_name=name)
            if call_id == resumed_call_id and resumed_call_id:
                return True
            if name in ROUTES:
                phase = _phase(name, params)
                if phase == "prepare":
                    res = await asyncio.to_thread(tools.invoke, name, params, context=make_context(call_id))
                    sc = res.structured_content if isinstance(res.structured_content, dict) else {}
                    if res.is_error or sc.get("status") != "waiting_for_owner_approval" or not sc.get("actionId"):
                        cached_results[call_id] = res
                        return False
                    interrupted_meta[call_id] = {
                        "action_id": str(sc["actionId"]),
                        "action_hash": str(sc.get("contentHash", "")),
                        "tool_name": name,
                        "mode": "bridge_prepare",
                    }
                    return True
                if params.get("approve") is False:
                    return False
                route = ROUTES[name]
                action_id = str(params.get(route.id_field) or "") if route.id_field else ""
                if self._actions is not None and action_id:
                    row = self._actions.get(scope, action_id)
                    if row["state"] == "pending":
                        interrupted_meta[call_id] = {
                            "action_id": action_id,
                            "action_hash": str(row["action_hash"]),
                            "tool_name": name,
                            "mode": "bridge_confirm",
                        }
                        return True
                return False

            if is_write:
                if tools.calls_used >= request.limits.max_tool_calls:
                    record_and_raise(_BudgetExceeded("tool_budget_exceeded"))
                if self._actions is not None:
                    stored = {
                        "tool": name,
                        "tool_arguments": dict(params),
                        "summary": f"{name}: {json.dumps(params, sort_keys=True, ensure_ascii=False)}",
                    }
                    self._actions.check(scope, name, stored)
                    prepared = self._actions.prepare(scope, name, stored, "v1", call_id)
                    interrupted_meta[call_id] = {
                        "action_id": prepared.action_id,
                        "action_hash": prepared.action_hash,
                        "tool_name": name,
                        "mode": "custom_write",
                    }
                return True
            return False

        async def invoke_tool(tool_context: Any, raw_arguments: str) -> str:
            call_id = str(getattr(tool_context, "tool_call_id", "") or f"{request.run_id}:{name}")
            if call_id in cached_results:
                return json.dumps(cached_results.pop(call_id).mcp_result(), separators=(",", ":"))
            check_step_guards(tool_name=name)
            arguments = parse_json_object_bytes(raw_arguments.encode("utf-8"))

            if call_id == resumed_call_id and resumed_mode == "bridge_prepare" and self._actions is not None:
                write_in_flight[0] = True
                try:
                    row = self._actions.get(scope, resumed_action_id)
                    outcome = await asyncio.to_thread(self._actions.execute, scope, resumed_action_id, row["action_hash"])
                except BaseException as exc:
                    uncertain_effect[0] = True
                    record_and_raise(_UncertainEffectError("effect_outcome_unknown"))
                finally:
                    write_in_flight[0] = False
                if outcome.get("state") == "completed":
                    payload = {"status": "completed", "actionId": resumed_action_id, "result": outcome.get("result")}
                    result = ToolInvocationResult(json.dumps(payload, separators=(",", ":")), payload, is_error=False)
                elif outcome.get("state") == "failed":
                    payload = {"status": "not_done", "actionId": resumed_action_id, "code": outcome.get("code")}
                    result = ToolInvocationResult(json.dumps(payload, separators=(",", ":")), payload, is_error=True)
                else:
                    uncertain_effect[0] = True
                    record_and_raise(_UncertainEffectError("effect_outcome_unknown"))
                return json.dumps(result.mcp_result(), separators=(",", ":"))

            if is_write:
                write_in_flight[0] = True
            try:
                result = await asyncio.to_thread(tools.invoke, name, arguments, context=make_context(call_id))
                sc = result.structured_content if isinstance(result.structured_content, dict) else {}
                if is_write and sc.get("status") == "outcome_unknown":
                    uncertain_effect[0] = True
                    record_and_raise(_UncertainEffectError("effect_outcome_unknown"))
                if is_write and cancel_requested():
                    uncertain_effect[0] = True
                    record_and_raise(_UncertainEffectError("cancelled_during_effect"))
            except (ToolBudgetExceeded, _BudgetExceeded, _UncertainEffectError) as exc:
                record_and_raise(exc)
            except BaseException as exc:
                if is_write:
                    uncertain_effect[0] = True
                    record_and_raise(_UncertainEffectError("effect_outcome_unknown"))
                record_and_raise(exc)
            finally:
                write_in_flight[0] = False

            if not is_write and cancel_requested():
                record_and_raise(_RunCancelled())
            return json.dumps(result.mcp_result(), separators=(",", ":"))

        return FunctionTool(
            name=name,
            description=str(definition["description"]),
            params_json_schema=schema,
            on_invoke_tool=invoke_tool,
            strict_json_schema=strict_compatible(schema),
            needs_approval=check_needs_approval if (is_write or name in ROUTES) else False,
        )

    async def _execute_gemini(
        self,
        *,
        scope: WorkScope,
        request: BackgroundRunRequest,
        checkpoint: dict[str, object] | None,
        tools: BackgroundToolSupply,
        tool_context: Callable[[str], ToolInvocationContext],
        cancel_requested: Callable[[], bool],
        api_key: str,
        model_id: str,
        oauth: bool,
        prior_turns: int,
        prior_seconds: float,
        turn_counter_out: list[int] | None,
    ) -> ExecutionOutcome:
        started_at = self._clock()
        turns_used = prior_turns
        uncertain_effect = False
        write_in_flight = False
        rejection_failure_code: str | None = None

        def elapsed_active() -> float:
            return prior_seconds + max(0.0, float(self._clock() - started_at))

        def check_step_guards(*, tool_name: str | None = None) -> None:
            if cancel_requested():
                if write_in_flight or uncertain_effect:
                    raise _UncertainEffectError("cancelled_during_effect")
                raise _RunCancelled()
            self._validate_scope(scope, tool_name=tool_name)
            if elapsed_active() >= request.limits.max_seconds:
                raise _BudgetExceeded("run_timeout")

        memories = (
            tuple(checkpoint["memories"])
            if checkpoint is not None and isinstance(checkpoint.get("memories"), list)
            else await asyncio.to_thread(self._memory_context, request, scope=scope)
        )
        skill_catalog = await asyncio.to_thread(
            self._skill_catalog, scope, {str(item["name"]) for item in tools.definitions()},
        )
        declarations = [{
            "name": str(item["name"]),
            "description": str(item["description"]),
            "parameters": item["inputSchema"],
        } for item in tools.definitions()]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent"
        headers = (
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            if oauth else {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        )

        try:
            if checkpoint is None:
                contents: list[dict[str, object]] = [
                    {"role": "user", "parts": [{"text": background_input(request, memories=memories)}]}
                ]
            else:
                state = checkpoint["state"]
                contents = [dict(item) for item in state.get("contents", [])]
                pending_call = state.get("pending_call")
                if not isinstance(pending_call, dict):
                    return ExecutionOutcome(WorkState.FAILED, failure_code="invalid_checkpoint")
                call_name = str(pending_call.get("name") or "")
                call_args = pending_call.get("arguments")
                call_id = str(pending_call.get("call_id") or "")
                synthetic = SimpleNamespace(raw_item=SimpleNamespace(
                    name=call_name, call_id=call_id, arguments=json.dumps(call_args, sort_keys=True),
                ))
                if approval_fingerprint(synthetic) != checkpoint.get("approval_hash"):
                    return ExecutionOutcome(WorkState.FAILED, failure_code="invalid_checkpoint")
                if not tools.has_tool(call_name):
                    return ExecutionOutcome(WorkState.FAILED, failure_code="tool_not_granted")
                check_step_guards(tool_name=call_name)

                resumed_action_id = str(checkpoint.get("pending_action_id") or "")
                decision_state = self._resolve_action_decision(scope, resumed_action_id)
                if decision_state == "pending":
                    return ExecutionOutcome(
                        WorkState.WAITING_APPROVAL,
                        checkpoint=checkpoint,
                        pending_action_id=resumed_action_id,
                    )
                if decision_state == "approved":
                    mode = str(checkpoint.get("action_mode") or "custom_write")
                    write_in_flight = True
                    try:
                        if mode == "bridge_prepare" and self._actions is not None:
                            row = self._actions.get(scope, resumed_action_id)
                            outcome = await asyncio.to_thread(self._actions.execute, scope, resumed_action_id, row["action_hash"])
                            if outcome.get("state") == "completed":
                                payload = {"status": "completed", "actionId": resumed_action_id, "result": outcome.get("result")}
                                tool_res = ToolInvocationResult(json.dumps(payload), payload, is_error=False)
                            elif outcome.get("state") == "failed":
                                payload = {"status": "not_done", "actionId": resumed_action_id, "code": outcome.get("code")}
                                tool_res = ToolInvocationResult(json.dumps(payload), payload, is_error=True)
                            else:
                                uncertain_effect = True
                                raise _UncertainEffectError("effect_outcome_unknown")
                        else:
                            tool_res = await asyncio.to_thread(tools.invoke, call_name, call_args, context=tool_context(call_id))
                    except BaseException as exc:
                        uncertain_effect = True
                        raise _UncertainEffectError("effect_outcome_unknown") from exc
                    finally:
                        write_in_flight = False
                    contents.append({"role": "user", "parts": [{"functionResponse": {"name": call_name, "response": tool_res.mcp_result()}}]})
                else:
                    rejection_failure_code = "approval_denied" if decision_state == "denied" else "approval_expired"
                    denied_res = ToolInvocationResult("Tool execution was not approved.", is_error=True)
                    contents.append({"role": "user", "parts": [{"functionResponse": {"name": call_name, "response": denied_res.mcp_result()}}]})

            while turns_used < request.limits.max_model_turns:
                check_step_guards()
                body: dict[str, object] = {
                    "systemInstruction": {"parts": [{"text": background_instructions(request) + " Return only the required JSON object when complete." + skill_catalog}]},
                    "contents": contents,
                    **({"tools": [{"functionDeclarations": declarations}]} if declarations else {}),
                    "generationConfig": {"temperature": 0.2},
                }
                if self._gemini_transport is not None:
                    payload = self._gemini_transport(url, headers, body)
                    if asyncio.iscoroutine(payload):
                        payload = await payload
                else:
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        response = await client.post(url, headers=headers, json=body)
                        response.raise_for_status()
                        payload = response.json()

                turns_used += 1
                if turn_counter_out is not None:
                    turn_counter_out[0] = turns_used
                check_step_guards()

                candidates = payload.get("candidates", []) if isinstance(payload, dict) else []
                parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
                calls = [part.get("functionCall") for part in parts if isinstance(part, dict) and isinstance(part.get("functionCall"), dict)]
                if not calls:
                    text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict)).strip()
                    cleaned = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                    check_step_guards()
                    return self._finalize_output(
                        parse_json_object_bytes(cleaned.encode("utf-8")),
                        rejection_failure_code=rejection_failure_code,
                    )

                contents.append({"role": "model", "parts": parts})
                replies: list[dict[str, object]] = []
                for idx, call in enumerate(calls):
                    assert isinstance(call, dict)
                    name = str(call.get("name", ""))
                    arguments = call.get("args") if isinstance(call.get("args"), dict) else {}
                    call_id = f"{request.run_id}:{name}:{turns_used}:{idx}"
                    check_step_guards(tool_name=name)
                    is_write = tools.effect_class(name) in {"write", "delete"}
                    if is_write and self._actions is None:
                        return ExecutionOutcome(WorkState.FAILED, failure_code="approval_service_unavailable")

                    if name in ROUTES and _phase(name, arguments) == "prepare":
                        res = await asyncio.to_thread(tools.invoke, name, arguments, context=tool_context(call_id))
                        sc = res.structured_content if isinstance(res.structured_content, dict) else {}
                        if not res.is_error and sc.get("status") == "waiting_for_owner_approval" and sc.get("actionId"):
                            action_id = str(sc["actionId"])
                            synthetic = SimpleNamespace(raw_item=SimpleNamespace(
                                name=name, call_id=call_id, arguments=json.dumps(arguments, sort_keys=True),
                            ))
                            saved_checkpoint = build_sdk_checkpoint(
                                provider_key="gemini",
                                model_id=model_id,
                                sdk_version=GEMINI_ADAPTER_VERSION,
                                approval_hash=approval_fingerprint(synthetic),
                                state={"contents": contents, "pending_call": {"name": name, "arguments": arguments, "call_id": call_id}},
                                scope=scope,
                                pending_action_id=action_id,
                                tool_name=name,
                                call_id=call_id,
                                action_mode="bridge_prepare",
                                budget={"model_turns": turns_used, "tool_calls": tools.calls_used, "active_seconds": round(elapsed_active(), 6)},
                                memories=memories,
                                max_bytes=MAX_CHECKPOINT_BYTES,
                            )
                            return ExecutionOutcome(WorkState.WAITING_APPROVAL, checkpoint=saved_checkpoint, pending_action_id=action_id)
                        replies.append({"functionResponse": {"name": name, "response": res.mcp_result()}})
                        continue

                    if is_write and self._actions is not None:
                        stored = {"tool": name, "tool_arguments": dict(arguments), "summary": f"{name}: {json.dumps(arguments, sort_keys=True)}"}
                        self._actions.check(scope, name, stored)
                        prepared = self._actions.prepare(scope, name, stored, "v1", call_id)
                        synthetic = SimpleNamespace(raw_item=SimpleNamespace(
                            name=name, call_id=call_id, arguments=json.dumps(arguments, sort_keys=True),
                        ))
                        saved_checkpoint = build_sdk_checkpoint(
                            provider_key="gemini",
                            model_id=model_id,
                            sdk_version=GEMINI_ADAPTER_VERSION,
                            approval_hash=approval_fingerprint(synthetic),
                            state={"contents": contents, "pending_call": {"name": name, "arguments": arguments, "call_id": call_id}},
                            scope=scope,
                            pending_action_id=prepared.action_id,
                            tool_name=name,
                            call_id=call_id,
                            action_mode="custom_write",
                            budget={"model_turns": turns_used, "tool_calls": tools.calls_used, "active_seconds": round(elapsed_active(), 6)},
                            memories=memories,
                            max_bytes=MAX_CHECKPOINT_BYTES,
                        )
                        return ExecutionOutcome(WorkState.WAITING_APPROVAL, checkpoint=saved_checkpoint, pending_action_id=prepared.action_id)

                    result = await asyncio.to_thread(tools.invoke, name, arguments, context=tool_context(call_id))
                    if cancel_requested():
                        raise _RunCancelled()
                    replies.append({"functionResponse": {"name": name, "response": result.mcp_result()}})
                contents.append({"role": "user", "parts": replies})

            raise _BudgetExceeded("max_model_turns_exceeded")

        except BackgroundRunAuthorizationError:
            raise
        except _UncertainEffectError as exc:
            return ExecutionOutcome(WorkState.UNKNOWN, failure_code=exc.code)
        except _RunCancelled:
            return ExecutionOutcome(WorkState.CANCELLED, failure_code="cancelled")
        except (_BudgetExceeded, ToolBudgetExceeded) as exc:
            code = exc.code if isinstance(exc, _BudgetExceeded) else "tool_budget_exceeded"
            return ExecutionOutcome(WorkState.FAILED, failure_code=code, failure_message=str(exc)[:2048])

    def _resolve_provider(self, scope: WorkScope) -> tuple[str, str, str, str]:
        if self._credentials is None:
            return "openai", "offline-unused-key", "api_key", "gpt-5.4-mini"
        selector = getattr(self._credentials, "selected_provider", None)
        provider_key = (
            selector(user_id=scope.user_id, workspace_id=scope.workspace_id)
            if selector is not None else "openai"
        )
        try:
            credential, model_id = self._credentials.background_access(
                user_id=scope.user_id, workspace_id=scope.workspace_id, provider_key=provider_key,
            )
        except TypeError:
            credential, model_id = self._credentials.background_access(
                user_id=scope.user_id, workspace_id=scope.workspace_id,
            )
        return (
            str(provider_key),
            str(credential.value),
            str(getattr(credential, "auth_method", "api_key")),
            str(model_id),
        )

    def _validate_scope(self, scope: WorkScope, *, tool_name: str | None = None) -> None:
        if self._authority is not None:
            self._authority.validate(scope, tool_name=tool_name)

    def _resolve_action_decision(self, scope: WorkScope, action_id: str) -> str:
        row = self._actions.get(scope, action_id)
        state = str(row["state"])
        if state == "pending" and row["expires_at"] <= self._actions.now():
            return "expired"
        return state

    def _memory_context(self, request: BackgroundRunRequest, *, scope: WorkScope) -> tuple[dict[str, object], ...]:
        if self._memories is None:
            return ()
        query = " ".join((request.objective, request.original_request, request.context_summary)).strip()
        if not query:
            return ()
        return tuple({
            "memoryId": match.memory.memory_id,
            "domain": match.memory.domain,
            "memoryType": match.memory.memory_type,
            "memoryKey": match.memory.memory_key,
            "content": match.memory.content_text,
            "confidence": match.memory.confidence,
            "sensitivity": match.memory.sensitivity,
            "visibility": match.memory.visibility,
        } for match in self._memories.search(
            user_id=scope.user_id, workspace_id=scope.workspace_id, query=query, limit=8,
        ))

    @staticmethod
    def _finalize_output(final: Any, *, rejection_failure_code: str | None = None) -> ExecutionOutcome:
        if isinstance(final, BackgroundAgentOutput):
            typed = final
        elif isinstance(final, dict):
            typed = BackgroundAgentOutput.model_validate(final)
        else:
            typed = BackgroundAgentOutput.model_validate(parse_json_object_bytes(str(final).encode("utf-8")))
        value = typed.model_dump(mode="json")
        if rejection_failure_code is not None:
            return ExecutionOutcome(WorkState.FAILED, output=value, failure_code=rejection_failure_code)
        if typed.status == "complete":
            return ExecutionOutcome(WorkState.COMPLETED, output=value)
        message = typed.summary if typed.status == "blocked" else (
            typed.unresolved_issues[0] if typed.unresolved_issues else typed.summary
        )
        return ExecutionOutcome(WorkState.FAILED, output=value, failure_code="agent_incomplete",
                                failure_message=message[:1024])

    def _sync_worker_session_checkpoint(self, scope: WorkScope, checkpoint: dict[str, object] | None) -> None:
        if not self._database_url or not scope.worker_id:
            return
        with psycopg.connect(self._database_url) as connection:
            if checkpoint is not None:
                connection.execute(
                    """UPDATE vault_private.vault_background_sessions
                       SET provider_key=%s, model_id=%s, adapter_version=%s, checkpoint_version=%s,
                           checkpoint_json=%s, updated_at=now()
                       WHERE user_id=%s AND workspace_id=%s AND work_id=%s AND worker_id=%s AND worker_generation=%s""",
                    (
                        str(checkpoint.get("provider_key", "openai")),
                        str(checkpoint.get("model_id", "default")),
                        str(checkpoint.get("sdk_version", self._sdk_version)),
                        int(checkpoint.get("version", 1)),
                        Jsonb(checkpoint),
                        scope.user_id, scope.workspace_id, scope.work_id, scope.worker_id, scope.worker_generation,
                    ),
                )
            else:
                connection.execute(
                    """UPDATE vault_private.vault_background_sessions
                       SET checkpoint_json='{}'::jsonb, updated_at=now()
                       WHERE user_id=%s AND workspace_id=%s AND work_id=%s AND worker_id=%s AND worker_generation=%s""",
                    (scope.user_id, scope.workspace_id, scope.work_id, scope.worker_id, scope.worker_generation),
                )
