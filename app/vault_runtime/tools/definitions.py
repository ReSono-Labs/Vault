from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.vault_runtime.system_agents.inventory import AgentKind

TOOL_EFFECTS = frozenset({"read", "write", "delete"})


@dataclass(frozen=True, slots=True)
class ToolInvocationContext:
    agent: AgentKind
    user_id: str
    workspace_id: str
    tool_call_id: str
    local_session_id: str
    voice_session_id: str | None = None
    user_utterance: str | None = None
    user_utterance_id: int | None = None
    execution_id: str | None = None

    def __post_init__(self) -> None:
        for value in (self.user_id, self.workspace_id, self.tool_call_id, self.local_session_id):
            if not value or value.strip() != value:
                raise ValueError("tool context identifiers must be non-empty and trimmed")


@dataclass(frozen=True, slots=True)
class ToolInvocationResult:
    text: str
    structured_content: dict[str, object] | None = None
    is_error: bool = False
    provider_session_update: dict[str, object] | None = None

    def mcp_result(self) -> dict[str, object]:
        result: dict[str, object] = {
            "content": [{"type": "text", "text": self.text}],
            "isError": self.is_error,
        }
        if self.structured_content is not None:
            result["structuredContent"] = self.structured_content
        if self.provider_session_update is not None:
            result["resonoSessionUpdate"] = self.provider_session_update
        return result


ContextToolHandler = Callable[[ToolInvocationContext, dict[str, object]], ToolInvocationResult]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    tool_id: str
    name: str
    description: str
    input_schema: dict[str, object]
    handler: ContextToolHandler
    effect_class: str = "read"
    audiences: frozenset[AgentKind] = frozenset({AgentKind.VOICE, AgentKind.BACKGROUND})
    scope_user_id: str | None = None
    scope_workspace_id: str | None = None
    availability: Callable[[str, str], bool] | None = None

    def __post_init__(self) -> None:
        if not self.tool_id or not self.name or not self.description:
            raise ValueError("tool identity and description are required")
        if self.effect_class not in TOOL_EFFECTS:
            raise ValueError("unsupported tool effect")
        if not self.audiences:
            raise ValueError("tool requires at least one fixed system-agent audience")
        if not self.audiences.issubset(frozenset(AgentKind)):
            raise ValueError("tool audience is not a fixed system agent")
        if (self.scope_user_id is None) != (self.scope_workspace_id is None):
            raise ValueError("tool scope requires both user and workspace")
        if self.scope_user_id is not None and (
            not self.scope_user_id.strip() or not self.scope_workspace_id
            or not self.scope_workspace_id.strip()
        ):
            raise ValueError("tool scope identifiers must be non-empty")

    def visible_in(self, *, user_id: str | None, workspace_id: str | None) -> bool:
        scoped = self.scope_user_id is None or (
            self.scope_user_id == user_id and self.scope_workspace_id == workspace_id
        )
        return scoped and (self.availability is None or user_id is None or workspace_id is None or self.availability(user_id, workspace_id))

    def mcp_definition(self) -> dict[str, object]:
        return {"name": self.name, "description": self.description, "inputSchema": self.input_schema}

    def realtime_definition(self) -> dict[str, object]:
        return {
            "type": "function", "name": self.name,
            "description": self.description, "parameters": self.input_schema,
        }
