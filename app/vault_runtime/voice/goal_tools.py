from __future__ import annotations

from uuid import uuid4

from app.vault_runtime.background_agent.contracts import (
    AutonomyProfile,
    BackgroundRunRequest,
    ExecutionRecipe,
)
from app.vault_runtime.background_agent.output_contract import background_output_schema
from app.vault_runtime.background_agent.service import BackgroundAgentService
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult
from app.vault_runtime.voice.modes import VoiceModeService


def register_goal_tools(
    catalog: ToolCatalog, service: BackgroundAgentService, voice_modes: VoiceModeService,
) -> None:
    catalog.register(ToolDefinition(
        tool_id="builtin.goal.start.v1", name="goal_start",
        description=(
            "Start one Background Agent goal when the user explicitly asks Background Agent to do work. "
            "Provide the user's goal and only the simple rules they stated."
        ),
        input_schema={"type": "object", "properties": {
            "goal": {"type": "string", "minLength": 1, "maxLength": 16384},
            "rules": {
                "type": "array",
                "items": {"type": "string", "minLength": 1, "maxLength": 2048},
                "maxItems": 12, "uniqueItems": True,
            },
        }, "required": ["goal", "rules"], "additionalProperties": False},
        handler=lambda context, args: _start(service, context, args, voice_modes),
        effect_class="write", audiences=frozenset({AgentKind.VOICE}),
    ))
    catalog.register(ToolDefinition(
        tool_id="builtin.goal.inspect.v1", name="goal_inspect",
        description="Check the current state or final result of a background goal by its run ID.",
        input_schema=_run_schema(),
        handler=lambda context, args: _inspect(service, context, args),
        effect_class="read", audiences=frozenset({AgentKind.VOICE}),
    ))
    catalog.register(ToolDefinition(
        tool_id="builtin.goal.cancel.v1", name="goal_cancel",
        description="Request cancellation of an active background goal by its run ID.",
        input_schema=_run_schema(),
        handler=lambda context, args: _cancel(service, context, args),
        effect_class="write", audiences=frozenset({AgentKind.VOICE}),
    ))


def _start(
    service: BackgroundAgentService, context: ToolInvocationContext,
    args: dict[str, object], voice_modes: VoiceModeService,
) -> ToolInvocationResult:
    if not context.voice_session_id:
        return ToolInvocationResult("A live Voice session is required to start a goal.", is_error=True)
    goal = str(args["goal"]).strip()
    rules = tuple(str(item).strip() for item in args.get("rules", []))
    rule_context = "\n".join(f"- {item}" for item in rules)
    try:
        run = service.submit(
            user_id=context.user_id, workspace_id=context.workspace_id,
            local_session_id=context.local_session_id,
            request=BackgroundRunRequest(
                run_id=str(uuid4()), objective=goal, instruction_profile="voice-goal",
                success_criteria=("Complete the stated goal while following every supplied rule.",),
                result_schema=background_output_schema(),
                recipe=ExecutionRecipe.SELF_REVIEW, autonomy=AutonomyProfile.EXPANDED,
                context_summary=("User rules:\n" + rule_context if rules else "User supplied no additional rules."),
                expected_result="A completed result that satisfies the goal and follows the supplied rules.",
                original_request=goal,
                verification_method="Review the completed work against the stated goal and every supplied rule.",
                completion_conditions=("The goal is completed and the result has been reviewed against the supplied rules.",),
            ),
        )
    except Exception as error:
        return ToolInvocationResult(str(error), is_error=True)
    return ToolInvocationResult(
        f"Goal accepted with run ID {run.request.run_id}.",
        {"runId": run.request.run_id, "state": run.state.value, "recipe": run.request.recipe.value},
        provider_session_update=voice_modes.restore_primary(context.voice_session_id),
    )


def _inspect(service: BackgroundAgentService, context: ToolInvocationContext, args: dict[str, object]) -> ToolInvocationResult:
    try:
        run = service.inspect_workspace(
            user_id=context.user_id, workspace_id=context.workspace_id,
            local_session_id=context.local_session_id, run_id=str(args["runId"]),
        )
    except Exception as error:
        return ToolInvocationResult(str(error), is_error=True)
    return ToolInvocationResult(
        f"Goal is {run.state.value}.",
        {
            "runId": run.request.run_id, "state": run.state.value,
            "output": run.output, "failureCode": run.failure_code,
            "failureMessage": run.failure_message,
        },
    )


def _cancel(service: BackgroundAgentService, context: ToolInvocationContext, args: dict[str, object]) -> ToolInvocationResult:
    try:
        run = service.cancel_workspace(
            user_id=context.user_id, workspace_id=context.workspace_id,
            local_session_id=context.local_session_id, run_id=str(args["runId"]),
        )
    except Exception as error:
        return ToolInvocationResult(str(error), is_error=True)
    return ToolInvocationResult(
        "Cancellation requested.", {"runId": run.request.run_id, "state": run.state.value},
    )


def _run_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {"runId": {"type": "string", "minLength": 1}},
        "required": ["runId"], "additionalProperties": False,
    }
