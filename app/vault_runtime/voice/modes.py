from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock

from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult


PRIMARY_MODE = "primary"
GOAL_INTAKE_MODE = "goal_intake"
MODE_SWITCH_TOOL = "voice_mode_switch"
GOAL_SUBMIT_TOOL = "goal_start"

PRIMARY_DELEGATION_INSTRUCTION = (
    "When the user clearly asks you to delegate substantial work to the Background Agent, "
    "call voice_mode_switch with modeKey goal_intake. Do not make the user know or say the "
    "word mode. Do not switch for ordinary questions or direct Mail, Calendar, Tasks, Memory, "
    "Web Search, or installed Agent Skill requests. Switch only when the user explicitly "
    "requests substantial work by the Background Agent or explicitly asks to delegate a goal. "
    "If delegation intent is materially ambiguous, ask one concise clarifying question before "
    "switching. Never say there is no Background Agent; it is the fixed non-interactive worker. "
    "If the user says Background Agent should work with a remote agent, start a Background Agent "
    "goal and let that agent own the remote interaction."
)

GOAL_INTAKE_INSTRUCTION = (
    "You are Goal Intake inside the user's existing live Voice session. Collect only two things: "
    "the user's goal and any simple rules the user stated. Preserve the user's wording. "
    "Do not ask for recipes, tools, or implementation details; Background Agent decides its approach. "
    "When the goal is clear, call goal_start once with goal and rules. A successful goal_start "
    "automatically restores Primary Voice. If submission fails, remain in Goal Intake and explain "
    "the actual failure. If the user cancels, call voice_mode_switch with modeKey primary. "
    "Never execute the background work yourself."
)


@dataclass(frozen=True, slots=True)
class _SessionProfile:
    mode: str
    primary_instructions: str
    primary_tools: Callable[[], tuple[dict[str, object], ...]]
    goal_intake_tools: Callable[[], tuple[dict[str, object], ...]]


class VoiceModeService:
    def __init__(self) -> None:
        self._sessions: dict[str, _SessionProfile] = {}
        self._lock = RLock()

    def open_session(
        self,
        session_id: str,
        *,
        primary_instructions: str,
        primary_tools: Callable[[], tuple[dict[str, object], ...]],
        goal_intake_tools: Callable[[], tuple[dict[str, object], ...]],
    ) -> None:
        if not session_id:
            return
        with self._lock:
            self._sessions[session_id] = _SessionProfile(
                PRIMARY_MODE, primary_instructions, primary_tools, goal_intake_tools,
            )

    def close_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def mode(self, session_id: str | None) -> str:
        if not session_id:
            return PRIMARY_MODE
        with self._lock:
            profile = self._sessions.get(session_id)
            return profile.mode if profile else PRIMARY_MODE

    def allows(self, tool_name: str, context: ToolInvocationContext) -> bool:
        if context.agent is not AgentKind.VOICE or not context.voice_session_id:
            return True
        mode = self.mode(context.voice_session_id)
        if mode == GOAL_INTAKE_MODE:
            return tool_name in {MODE_SWITCH_TOOL, GOAL_SUBMIT_TOOL}
        return tool_name != GOAL_SUBMIT_TOOL

    def switch(self, session_id: str | None, mode: str) -> ToolInvocationResult:
        if not session_id:
            return ToolInvocationResult("A live Voice session is required.", is_error=True)
        if mode not in {PRIMARY_MODE, GOAL_INTAKE_MODE}:
            return ToolInvocationResult("Voice mode is invalid.", is_error=True)
        with self._lock:
            current = self._sessions.get(session_id)
            if current is None:
                return ToolInvocationResult("The live Voice session is unavailable.", is_error=True)
            duplicate = current.mode == mode
            if not duplicate:
                current = _SessionProfile(
                    mode, current.primary_instructions, current.primary_tools, current.goal_intake_tools,
                )
                self._sessions[session_id] = current
        return ToolInvocationResult(
            f"Voice is already in {mode} mode." if duplicate else f"Switched to {mode} mode.",
            {"modeKey": mode, **({"duplicate": True} if duplicate else {})},
            provider_session_update=self._session_update(current),
        )

    def restore_primary(self, session_id: str | None) -> dict[str, object] | None:
        if not session_id:
            return None
        with self._lock:
            current = self._sessions.get(session_id)
            if current is None:
                return None
            updated = _SessionProfile(
                PRIMARY_MODE, current.primary_instructions, current.primary_tools, current.goal_intake_tools,
            )
            self._sessions[session_id] = updated
        return self._session_update(updated)

    @staticmethod
    def _session_update(profile: _SessionProfile) -> dict[str, object]:
        if profile.mode == GOAL_INTAKE_MODE:
            instructions, tools = GOAL_INTAKE_INSTRUCTION, list(profile.goal_intake_tools())
        else:
            instructions, tools = profile.primary_instructions, list(profile.primary_tools())
        return {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "instructions": instructions,
                "tools": tools,
                "tool_choice": "auto",
            },
        }


def register_voice_mode_tool(catalog: ToolCatalog, service: VoiceModeService) -> None:
    catalog.register(ToolDefinition(
        tool_id="builtin.voice.mode-switch.v1",
        name=MODE_SWITCH_TOOL,
        description=(
            "Change the live Voice profile. Use goal_intake only when the user explicitly "
            "requests substantial Background Agent work or asks to delegate a goal."
        ),
        input_schema={
            "type": "object",
            "properties": {"modeKey": {"type": "string", "enum": [PRIMARY_MODE, GOAL_INTAKE_MODE]}},
            "required": ["modeKey"],
            "additionalProperties": False,
        },
        handler=lambda context, args: service.switch(context.voice_session_id, str(args["modeKey"])),
        effect_class="write",
        audiences=frozenset({AgentKind.VOICE}),
    ))
