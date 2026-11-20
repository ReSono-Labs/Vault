from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.vault_runtime.system_agents.inventory import AgentKind


class ExtensionKind(StrEnum):
    PLUGIN = "plugin"
    SKILL = "skill"
    MCP = "mcp"


class ExtensionState(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class ExtensionAudience:
    agents: frozenset[AgentKind]

    def __post_init__(self) -> None:
        if not self.agents or not self.agents.issubset(frozenset(AgentKind)):
            raise ValueError("extension audience must use fixed system agents")

    @classmethod
    def parse(cls, values: object) -> "ExtensionAudience":
        if not isinstance(values, (list, tuple, set, frozenset)):
            raise ValueError("extension audience must be a list")
        try:
            agents = frozenset(AgentKind(str(value)) for value in values)
        except ValueError as exc:
            raise ValueError("unknown system-agent audience") from exc
        return cls(agents)
