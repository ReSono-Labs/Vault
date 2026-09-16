"""Production adapter for the one fixed Background Agent using the R1 SDK runner."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

import httpx

from agents import FunctionTool

from app.vault_runtime.background_agent.contracts import BackgroundRunRequest
from app.vault_runtime.background_agent.sdk_runner import AgentTurnObservation, run_agent_turn
from app.vault_runtime.background_agent.service import RunProgressRecorder
from app.vault_runtime.background_agent.tool_supply import BackgroundToolSupply
from app.vault_runtime.background_agent.output_contract import BackgroundAgentOutput
from app.vault_runtime.memory.service import MemoryService
from app.vault_runtime.tools.definitions import ToolInvocationContext
from app.vault_runtime.tools.strict_json import parse_json_object_bytes
from app.vault_runtime.voice.credentials import VoiceProviderCredentialStore
from app.vault_runtime.workspace_files.constants import WORKSPACE_AGENT_ROOT_GUIDANCE


class OpenAIBackgroundExecutor:
    """Provider-selected executor retaining the fixed Vault Background Agent."""

    def __init__(
        self, *, credentials: VoiceProviderCredentialStore,
        memories: MemoryService | None = None,
        runner: Callable[..., Any] = run_agent_turn,
    ) -> None:
        self._credentials = credentials
        self._memories = memories
        self._runner = runner

    def execute(
        self, request: BackgroundRunRequest, *, tools: BackgroundToolSupply,
        context: ToolInvocationContext, progress: RunProgressRecorder,
    ) -> dict[str, object]:
        selector = getattr(self._credentials, "selected_provider", None)
        provider_key = selector(user_id=context.user_id, workspace_id=context.workspace_id) if selector else "openai"
        try:
            credential, model = self._credentials.background_access(
                user_id=context.user_id, workspace_id=context.workspace_id,
                provider_key=provider_key,
            )
        except TypeError:
            credential, model = self._credentials.background_access(
                user_id=context.user_id, workspace_id=context.workspace_id,
            )
        memory_context = self._memory_context(request, context=context)
        progress.context_frozen(tuple(str(item["memoryId"]) for item in memory_context))
        if provider_key == "gemini":
            return self._execute_gemini(
                credential.value, model, request=request, tools=tools,
                context=context, progress=progress, memories=memory_context,
                oauth=getattr(credential, "auth_method", "api_key") == "gemini_oauth",
            )
        function_tools = [self._function_tool(definition, tools=tools, base_context=context)
                          for definition in tools.definitions()]

        def observe(observation: AgentTurnObservation) -> None:
            if observation.model_turns:
                progress.model_turn(observation.model_turns)
            if observation.reasoning_summaries:
                progress.reasoning(observation.reasoning_summaries)

        final = asyncio.run(self._runner(
            api_key=credential.value, model=model,
            instructions=_instructions(request),
            input_text=_input(request, memories=memory_context),
            base_url=("https://api.x.ai/v1" if provider_key == "xai" else
                      "https://chatgpt.com/backend-api/codex" if getattr(credential, "auth_method", "api_key") == "chatgpt_oauth" else None),
            max_turns=request.limits.max_model_turns, reasoning_effort="medium",
            agent_name="ReSono Background Agent", function_tools=function_tools,
            observation_sink=observe, output_type=BackgroundAgentOutput,
        ))
        if isinstance(final, BackgroundAgentOutput):
            return final.model_dump(mode="json")
        if isinstance(final, dict):
            return final
        return parse_json_object_bytes(str(final).encode("utf-8"))

    def _execute_gemini(
        self, api_key: str, model: str, *, request: BackgroundRunRequest,
        tools: BackgroundToolSupply, context: ToolInvocationContext,
        progress: RunProgressRecorder, memories: tuple[dict[str, object], ...], oauth: bool,
    ) -> dict[str, object]:
        declarations = [{
            "name": str(item["name"]), "description": str(item["description"]),
            "parameters": item["inputSchema"],
        } for item in tools.definitions()]
        contents: list[dict[str, object]] = [{"role": "user", "parts": [{"text": _input(request, memories=memories)}]}]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for _turn in range(request.limits.max_model_turns):
            progress.model_turn()
            response = httpx.post(
                url, headers=({"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                              if oauth else {"x-goog-api-key": api_key, "Content-Type": "application/json"}),
                json={
                    "systemInstruction": {"parts": [{"text": _instructions(request) + " Return only the required JSON object when complete."}]},
                    "contents": contents,
                    **({"tools": [{"functionDeclarations": declarations}]} if declarations else {}),
                    "generationConfig": {"temperature": 0.2},
                }, timeout=120.0,
            )
            response.raise_for_status()
            payload = response.json()
            candidates = payload.get("candidates", []) if isinstance(payload, dict) else []
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            calls = [part.get("functionCall") for part in parts if isinstance(part, dict) and isinstance(part.get("functionCall"), dict)]
            if not calls:
                text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict)).strip()
                cleaned = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                return BackgroundAgentOutput.model_validate(parse_json_object_bytes(cleaned.encode("utf-8"))).model_dump(mode="json")
            contents.append({"role": "model", "parts": parts})
            replies: list[dict[str, object]] = []
            for call in calls:
                assert isinstance(call, dict)
                name = str(call.get("name", ""))
                arguments = call.get("args") if isinstance(call.get("args"), dict) else {}
                result = tools.invoke(name, arguments, context=ToolInvocationContext(
                    agent=context.agent, user_id=context.user_id, workspace_id=context.workspace_id,
                    tool_call_id=f"{context.execution_id}:{name}:{_turn}",
                    local_session_id=context.local_session_id, execution_id=context.execution_id,
                ))
                replies.append({"functionResponse": {"name": name, "response": result.mcp_result()}})
            contents.append({"role": "user", "parts": replies})
        raise RuntimeError("max_model_turns_exceeded")

    def _memory_context(
        self, request: BackgroundRunRequest, *, context: ToolInvocationContext,
    ) -> tuple[dict[str, object], ...]:
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
            user_id=context.user_id, workspace_id=context.workspace_id, query=query, limit=8,
        ))

    @staticmethod
    def _function_tool(
        definition: dict[str, object], *, tools: BackgroundToolSupply,
        base_context: ToolInvocationContext,
    ) -> FunctionTool:
        name = str(definition["name"])

        async def invoke(tool_context, raw_arguments: str):
            arguments = parse_json_object_bytes(raw_arguments.encode("utf-8"))
            tool_call_id = str(getattr(tool_context, "tool_call_id", "") or f"{base_context.execution_id}:{name}")
            result = tools.invoke(name, arguments, context=ToolInvocationContext(
                agent=base_context.agent, user_id=base_context.user_id,
                workspace_id=base_context.workspace_id, tool_call_id=tool_call_id,
                local_session_id=base_context.local_session_id,
                execution_id=base_context.execution_id,
            ))
            return json.dumps(result.mcp_result(), separators=(",", ":"))

        return FunctionTool(
            name=name, description=str(definition["description"]),
            params_json_schema=definition["inputSchema"], on_invoke_tool=invoke,
            strict_json_schema=True,
        )


def _instructions(request: BackgroundRunRequest) -> str:
    return (
        "You are the one fixed ReSono Background Agent. Own the complete bounded reason-act-check "
        "loop for the supplied local goal. Use only granted tools and inspect actual results. You may "
        "work with a connected external A2A agent when the goal or user rules call for it, while retaining "
        "ownership of the goal and reviewing the combined result. Never impersonate another agent. "
        "Preserve external-agent replies faithfully and attribute them. Completion conditions are successful end "
        "states; stop conditions are exceptional blockers and never successful completion. Return the "
        "typed BackgroundAgentOutput required by the SDK, including status, summary, safe artifact "
        "references, requirement outcomes, unresolved issues, verification summary, and concise phase "
        "evidence for the durable run record. Set status complete only after checking the requested result.\n\n"
        + WORKSPACE_AGENT_ROOT_GUIDANCE
    )


def _input(
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
