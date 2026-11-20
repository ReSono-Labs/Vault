"""Background Agent brief: instructions, input, strict tool schemas and stored-request parsing.

Shared by the Background executor; holds no engine state."""

from __future__ import annotations

import json

from app.vault_runtime.background_agent.contracts import (
    AutonomyProfile,
    BackgroundRunRequest,
    ExecutionRecipe,
    RunLimits,
)
from app.vault_runtime.workspace_files.constants import WORKSPACE_AGENT_ROOT_GUIDANCE


def request_from_payload(raw: object) -> BackgroundRunRequest:
    """A stored run request (request_json) back to its contract."""
    data = raw if isinstance(raw, dict) else json.loads(str(raw))
    return BackgroundRunRequest(
        run_id=str(data["run_id"]), objective=str(data["objective"]),
        instruction_profile=str(data["instruction_profile"]),
        success_criteria=tuple(data["success_criteria"]), result_schema=dict(data["result_schema"]),
        recipe=ExecutionRecipe(data["recipe"]), autonomy=AutonomyProfile(data["autonomy"]),
        limits=RunLimits(**data["limits"]), goal_type=str(data["goal_type"]),
        context_summary=str(data["context_summary"]), expected_result=str(data["expected_result"]),
        scope=str(data["scope"]), exclusions=tuple(data["exclusions"]),
        source_requirements=str(data["source_requirements"]),
        workspace_destination=data["workspace_destination"],
        original_request=str(data["original_request"]),
        verification_method=str(data["verification_method"]),
        completion_conditions=tuple(data["completion_conditions"]),
        stop_conditions=tuple(data["stop_conditions"]),
        requested_tool_names=tuple(data["requested_tool_names"]),
    )


def strict_compatible(schema: object) -> bool:
    """Whether OpenAI's strict function mode accepts ``schema`` as it is.

    Strict mode needs every object to keep its properties closed and to require every
    property it lists. Named-property schemas may omit ``additionalProperties`` for
    SDK normalization, but free-form objects must opt out rather than lose arbitrary
    keys. Explicitly closed empty objects remain strict-compatible. Vault's own tools
    are written with closed schemas. Tools from
    Link Companion and MCP servers have optional fields (Link's card_preflight: ``data`` and
    ``fallback_text``), and one such tool made OpenAI refuse the whole Background Agent request
    (400 invalid_function_parameters, 2026-11-17), so every goal failed in seconds. Those tools
    are sent without strict mode, as Voice sends them; their arguments are still validated by
    the tool's own handler.
    """
    if isinstance(schema, list):
        return all(strict_compatible(item) for item in schema)
    if not isinstance(schema, dict):
        return True
    if schema.get("type") == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        # Closing a free-form object would discard its arbitrary keys.
        if not properties and schema.get("additionalProperties") is not False:
            return False
        # Named-property objects may use the SDK's existing strict normalization.
        if not isinstance(properties, dict) or schema.get("additionalProperties", False) is not False:
            return False
        required = schema.get("required", [])
        if not isinstance(required, list) or set(required) != set(properties):
            return False
        if not all(strict_compatible(value) for value in properties.values()):
            return False
    for key in ("items", "anyOf", "oneOf", "allOf", "$defs", "definitions"):
        value = schema.get(key)
        if isinstance(value, dict) and key in ("$defs", "definitions"):
            if not all(strict_compatible(item) for item in value.values()):
                return False
        elif value is not None and not strict_compatible(value):
            return False
    return True


def background_instructions(request: BackgroundRunRequest) -> str:
    return (
        "You are the one fixed ReSono Background Agent. Own the complete bounded reason-act-check "
        "loop for the supplied local goal. Use only granted tools and inspect actual results. You may "
        "work with a connected external A2A agent when the goal or user rules call for it, while retaining "
        "ownership of the goal and reviewing the combined result. Before working, review the authorized "
        "Vault memories supplied with the assignment. If relevant context is missing and memory_lookup "
        "is available, search for the specific project, preference, or prior decision you need. Treat "
        "memory as context and verify current facts with their sources. Never impersonate another agent. "
        "Preserve external-agent replies faithfully and attribute them. Completion conditions are successful end "
        "states; stop conditions are exceptional blockers and never successful completion. Return the "
        "typed BackgroundAgentOutput required by the SDK, including status, summary, safe artifact "
        "references, requirement outcomes, unresolved issues, verification summary, and concise phase "
        "evidence for the durable run record. Set status complete only after checking the requested result. "
        "For a scheduled check, set quiet=true only if the check succeeded and found no meaningful new "
        "information. Report failures and uncertainty. Include the actual deliverable in summary when it "
        "fits, or point to the saved artifact. Keep owner-facing text free of em dashes.\n\n"
        + WORKSPACE_AGENT_ROOT_GUIDANCE
    )


def background_input(
    request: BackgroundRunRequest, *, memories: tuple[dict[str, object], ...] = (),
) -> str:
    return json.dumps({
        "objective": request.objective, "originalRequest": request.original_request,
        "instructionProfile": request.instruction_profile,
        "successCriteria": list(request.success_criteria),
        "completionConditions": list(request.completion_conditions),
        "stopConditions": list(request.stop_conditions), "goalType": request.goal_type,
        "context": request.context_summary, "expectedResult": request.expected_result,
        "scope": request.scope, "exclusions": list(request.exclusions),
        "sourceRequirements": request.source_requirements,
        "workspaceDestination": request.workspace_destination,
        "verificationMethod": request.verification_method,
        "authorizedMemory": memories,
    }, sort_keys=True, separators=(",", ":"))
