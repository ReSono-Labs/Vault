from __future__ import annotations

import json

from app.vault_runtime.memory.repository import MemoryRepository
from app.vault_runtime.memory.service import MemoryService
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult


def register_memory_tools(
    *, catalog: ToolCatalog, repository: MemoryRepository, service: MemoryService
) -> None:
    """Port the R1 memory tools into the canonical two-agent catalog."""

    def lookup(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        query = str(arguments.get("query", "")).strip()
        limit = int(arguments.get("limit", 8))
        matches = service.search(
            user_id=context.user_id, workspace_id=context.workspace_id,
            query=query, limit=limit,
        )
        payload = {
            "items": [
                {
                    "memoryId": match.memory.memory_id,
                    "domain": match.memory.domain,
                    "memoryType": match.memory.memory_type,
                    "memoryKey": match.memory.memory_key,
                    "content": match.memory.content_text,
                    "confidence": match.memory.confidence,
                    "sensitivity": match.memory.sensitivity,
                    "visibility": match.memory.visibility,
                    "score": match.score,
                    "matchMethods": list(match.match_methods),
                }
                for match in matches
            ],
            "embeddingsAvailable": service.embeddings_available(
                user_id=context.user_id, workspace_id=context.workspace_id,
            ),
        }
        return ToolInvocationResult(json.dumps(payload, separators=(",", ":")), payload)

    def prepare_correction(
        context: ToolInvocationContext, arguments: dict[str, object]
    ) -> ToolInvocationResult:
        if not context.voice_session_id or context.user_utterance_id is None:
            return ToolInvocationResult("A current Voice user utterance is required.", is_error=True)
        memory_id = str(arguments.get("memoryId", "")).strip()
        new_content = str(arguments.get("newContent", "")).strip()
        memory = repository.memory(
            user_id=context.user_id, workspace_id=context.workspace_id, memory_id=memory_id
        )
        action_id = repository.prepare_action(
            user_id=context.user_id, workspace_id=context.workspace_id,
            voice_session_id=context.voice_session_id,
            prepared_entry_index=context.user_utterance_id,
            action_kind="correct", memory_id=memory_id, proposed_content=new_content,
        )
        payload = {
            "prepared": True, "actionId": action_id, "oldContent": memory.content_text,
            "newContent": new_content, "confirmationRequired": True,
        }
        return ToolInvocationResult(json.dumps(payload, separators=(",", ":")), payload)

    def explain(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        memory_id = str(arguments.get("memoryId", "")).strip()
        memory = repository.memory(
            user_id=context.user_id, workspace_id=context.workspace_id, memory_id=memory_id
        )
        payload = {
            "found": True, "memoryId": memory.memory_id, "domain": memory.domain,
            "memoryType": memory.memory_type, "content": memory.content_text,
            "confidence": memory.confidence, "status": memory.lifecycle_status,
            "evidence": list(repository.memory_evidence(
                user_id=context.user_id, workspace_id=context.workspace_id, memory_id=memory_id,
            )),
        }
        return ToolInvocationResult(json.dumps(payload, separators=(",", ":")), payload)

    def remember_intent(
        context: ToolInvocationContext, _arguments: dict[str, object]
    ) -> ToolInvocationResult:
        if not context.voice_session_id or not context.user_utterance:
            return ToolInvocationResult("A current Voice user utterance is required.", is_error=True)
        entry = repository.append_transcript_next(
            user_id=context.user_id, workspace_id=context.workspace_id,
            voice_session_id=context.voice_session_id, role="user",
            event_type="memory.intent.remember", text_content=context.user_utterance,
            metadata={"explicitRememberIntent": True},
        )
        payload = {"recorded": True, "voiceSessionId": context.voice_session_id,
                   "entryIndex": entry.entry_index}
        return ToolInvocationResult(json.dumps(payload, separators=(",", ":")), payload)

    def prepare_forget(
        context: ToolInvocationContext, arguments: dict[str, object]
    ) -> ToolInvocationResult:
        if not context.voice_session_id or context.user_utterance_id is None:
            return ToolInvocationResult("A current Voice user utterance is required.", is_error=True)
        memory_id = str(arguments.get("memoryId", "")).strip()
        memory = repository.memory(
            user_id=context.user_id, workspace_id=context.workspace_id, memory_id=memory_id
        )
        action_id = repository.prepare_action(
            user_id=context.user_id, workspace_id=context.workspace_id,
            voice_session_id=context.voice_session_id,
            prepared_entry_index=context.user_utterance_id,
            action_kind="forget", memory_id=memory_id,
        )
        payload = {
            "prepared": True, "actionId": action_id, "content": memory.content_text,
            "confirmationRequired": True,
        }
        return ToolInvocationResult(json.dumps(payload, separators=(",", ":")), payload)

    def confirm(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        if not context.voice_session_id or context.user_utterance_id is None:
            return ToolInvocationResult("A later Voice user confirmation is required.", is_error=True)
        result = service.confirm_action(
            user_id=context.user_id, workspace_id=context.workspace_id,
            voice_session_id=context.voice_session_id,
            action_id=str(arguments.get("actionId", "")).strip(),
            confirmation_entry_index=context.user_utterance_id,
        )
        payload = {
            "applied": True, "action": result.action, "memoryId": result.memory_id,
            "content": result.memory.content_text if result.memory is not None else None,
        }
        return ToolInvocationResult(json.dumps(payload, separators=(",", ":")), payload)

    definitions = (
        ToolDefinition(
            tool_id="builtin.memory-lookup.v1", name="memory_lookup",
            description="Search authorized Vault memory in the active local workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 4096},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 25},
                },
                "required": ["query"], "additionalProperties": False,
            },
            handler=lookup, effect_class="read",
            audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
        ),
        ToolDefinition(
            tool_id="builtin.memory-explain.v1", name="memory_explain",
            description="Explain one stored memory and the session evidence supporting it.",
            input_schema={
                "type": "object", "properties": {"memoryId": {"type": "string", "minLength": 1}},
                "required": ["memoryId"], "additionalProperties": False,
            },
            handler=explain, effect_class="read",
            audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
        ),
        ToolDefinition(
            tool_id="builtin.memory-remember-intent.v1", name="memory_remember_intent",
            description="Mark the user's current statement as an explicit remember request for post-session review.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=remember_intent, effect_class="write",
            audiences=frozenset({AgentKind.VOICE}),
        ),
        ToolDefinition(
            tool_id="builtin.memory-prepare-correction.v1", name="memory_prepare_correction",
            description="Prepare an exact memory correction for later user confirmation.",
            input_schema={
                "type": "object",
                "properties": {
                    "memoryId": {"type": "string", "minLength": 1},
                    "newContent": {"type": "string", "minLength": 1, "maxLength": 4096},
                },
                "required": ["memoryId", "newContent"], "additionalProperties": False,
            },
            handler=prepare_correction, effect_class="write",
            audiences=frozenset({AgentKind.VOICE}),
        ),
        ToolDefinition(
            tool_id="builtin.memory-prepare-forget.v1", name="memory_prepare_forget",
            description="Prepare forgetting one memory for later user confirmation.",
            input_schema={
                "type": "object", "properties": {"memoryId": {"type": "string", "minLength": 1}},
                "required": ["memoryId"], "additionalProperties": False,
            },
            handler=prepare_forget, effect_class="delete",
            audiences=frozenset({AgentKind.VOICE}),
        ),
        ToolDefinition(
            tool_id="builtin.memory-confirm-action.v1", name="memory_confirm_action",
            description="Apply a prepared memory correction or deletion after a later user confirmation.",
            input_schema={
                "type": "object", "properties": {"actionId": {"type": "string", "minLength": 1}},
                "required": ["actionId"], "additionalProperties": False,
            },
            handler=confirm, effect_class="write",
            audiences=frozenset({AgentKind.VOICE}),
        ),
    )
    for definition in definitions:
        catalog.register(definition)
