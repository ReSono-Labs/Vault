from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock

from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult


PRIMARY_MODE = "primary"
# Coordinator intake (2026-11-18) replaces Goal Intake: the same two-step mode, but the request goes
# to the chat coordinator (voice/coordinator_tools.py) instead of a Background Agent goal.
GOAL_INTAKE_MODE = "coordinator_intake"
MODE_SWITCH_TOOL = "voice_mode_switch"
GOAL_SUBMIT_TOOL = "coordinator_hand_off"
STATUS_TOOL = "coordinator_status"

GOAL_INTAKE_INSTRUCTION = (
    "You are Coordinator intake inside the user's live Voice session. Collect only what the coordinator "
    "needs: the request in the user's own words, any time or schedule they gave ('in ten minutes', 'every "
    "weekday at 8') and any simple rules they stated. For a reminder, routine or anything recurring, if "
    "the user did not say when, ask one short question first ('When, and how often?'). If the user is "
    "answering a question the coordinator asked on this call, hand off their answer as it is. Do not ask "
    "for tools or steps; the coordinator decides how to do it. When the request is clear, call "
    "coordinator_hand_off once. A successful hand-off restores "
    "Primary Voice: then tell the user in one sentence that the coordinator has it; its reply comes back on "
    "this call and stays in their chat, and any approval it needs appears on their phone. If the hand-off fails, stay here and "
    "say what failed. If the user cancels, call voice_mode_switch with modeKey primary. Never do the work yourself."
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
        self._direct: set[str] = set()
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
            self._direct.discard(session_id)

    def allow_direct_hand_off(self, session_id: str) -> None:
        """GPT-Live with client delegation: Vault's agent behind the live model has no intake mode,
        so coordinator_hand_off is offered to it directly."""
        if session_id:
            with self._lock:
                self._direct.add(session_id)

    def mode(self, session_id: str | None) -> str:
        if not session_id:
            return PRIMARY_MODE
        with self._lock:
            profile = self._sessions.get(session_id)
            return profile.mode if profile else PRIMARY_MODE

    def allows(self, tool_name: str, context: ToolInvocationContext) -> bool:
        if context.agent is AgentKind.BACKGROUND:
            return tool_name not in {MODE_SWITCH_TOOL, GOAL_SUBMIT_TOOL}
        if context.agent is not AgentKind.VOICE or not context.voice_session_id:
            return True
        with self._lock:
            if context.voice_session_id in self._direct:
                return tool_name != MODE_SWITCH_TOOL
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
            "Change the live Voice profile. Use coordinator_intake to hand the user's request to the "
            "coordinator: 'ask the coordinator', reminders, schedules and routines, anything for later, "
            "follow-ups, or longer work. Use primary to return."
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
