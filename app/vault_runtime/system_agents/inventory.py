from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AgentKind(StrEnum):
    VOICE = "voice"
    BACKGROUND = "background"


@dataclass(frozen=True, slots=True)
class SystemAgentDefinition:
    kind: AgentKind
    display_name: str
    interactive: bool


# This is intentionally a constant with no registration/mutation surface.
SYSTEM_AGENT_INVENTORY: tuple[SystemAgentDefinition, ...] = (
    SystemAgentDefinition(AgentKind.VOICE, "Voice Agent", True),
    SystemAgentDefinition(AgentKind.BACKGROUND, "Background Agent", False),
)


def system_agent(kind: AgentKind) -> SystemAgentDefinition:
    return next(item for item in SYSTEM_AGENT_INVENTORY if item.kind is kind)
