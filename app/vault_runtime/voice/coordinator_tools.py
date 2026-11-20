"""Voice hands work to the chat coordinator (2026-11-18). Replaces the Background Agent goal tools.

Voice keeps its intake mode (voice/modes.py): Primary switches to Coordinator intake, which calls
``coordinator_hand_off`` once and returns to Primary. The hand-off posts the user's spoken request as
their own message in a chat the coordinator owns, so the coordinator does it with its full tools,
follow-ups, routines and wakes (conversation/runtime.py), and replies there. Rakazo's voice calls work
the same way: remaining work becomes a normal reply in the bot's own thread.

Shared by every Voice path: Realtime (browser and Link phone) and GPT-Live with an API key reach
these tools through the intake mode; GPT-Live with ChatGPT sign-in offers them to Vault's agent
directly (VoiceModeService.allow_direct_hand_off).
"""
from __future__ import annotations

import logging
from time import monotonic, sleep
from typing import Any, Callable

import psycopg

from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult
from app.vault_runtime.voice.modes import GOAL_SUBMIT_TOOL, STATUS_TOOL, VoiceModeService

logger = logging.getLogger(__name__)

VOICE_REQUESTS_KEY = "voice-requests"
RECENT_CHAT_DAYS = 7


def _target_conversation(database_url: str, principal, *, link_call: bool) -> str | None:
    """The chat the user is using on this surface: their latest Link chat for a phone call, their
    latest browser chat otherwise (open, used in the last week)."""
    surface = "c.create_key LIKE 'link-companion:%%'" if link_call else (
        "c.create_key NOT LIKE 'link-companion:%%' AND c.create_key NOT LIKE 'voice-review:%%'")
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            f"""SELECT c.conversation_id FROM vault_private.vault_conversations c
                WHERE c.user_id=%s AND c.workspace_id=%s AND c.state='open' AND {surface}
                  AND COALESCE(c.activity_at, c.updated_at) > now() - make_interval(days => %s)
                ORDER BY COALESCE(c.activity_at, c.updated_at) DESC LIMIT 1""",
            (principal.user_id, principal.workspace_id, RECENT_CHAT_DAYS)).fetchone()
    return str(row[0]) if row else None


def _is_link_session(database_url: str, session_id: str) -> bool:
    with psycopg.connect(database_url) as connection:
        if connection.execute("SELECT to_regclass('vault_private.link_companion_link')").fetchone()[0] is None:
            return False
        return connection.execute("SELECT 1 FROM vault_private.link_companion_link WHERE session_id=%s",
                                  (session_id,)).fetchone() is not None


def coordinator_replies(runtime):
    """``(principal, conversation_id, since_epoch) -> [(turn_id, text)]``: finished coordinator replies
    in that chat since the call's first hand-off (hidden NO_RESPONSE turns are already left out)."""
    def replies(principal, conversation_id, since):
        page = runtime.store.display_history(principal, conversation_id, limit=12)
        return [(turn["turnId"], turn["answer"]) for turn in page["turns"]
                if turn.get("state") == "completed" and turn.get("answer")
                and (turn.get("createdAt") or 0) >= since - 2]
    return replies


def register_coordinator_voice_tools(
    *, catalog, database_url: str, runtime, resolve_principal: Callable[[str, str, str], Any],
    voice_modes: VoiceModeService, on_hand_off: Callable[[str, str], None] | None = None,
) -> None:
    from app.vault_runtime.conversation.contracts import ConflictError
    from app.vault_runtime.background_agent.coordination_contracts import OwnerScope

    handed: dict[str, str] = {}   # voice session -> the chat it handed work to

    def _principal(context: ToolInvocationContext):
        return resolve_principal(context.user_id, context.workspace_id, context.local_session_id)

    def _submit(principal, conversation_id, key, text):
        deadline = monotonic() + 8.0
        while True:
            version = runtime.store.load(principal, conversation_id).history_version
            try:
                return runtime.submit(principal, conversation_id, submission_key=key, input_text=text,
                                      expected_history_version=version)
            except ConflictError:
                if monotonic() >= deadline:
                    raise
                sleep(0.5)

    def hand_off(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        if not context.voice_session_id:
            return ToolInvocationResult("A live Voice session is required to hand off work.", is_error=True)
        request = " ".join(str(arguments.get("request") or "").split())
        if not request:
            return ToolInvocationResult("Say what the coordinator should do.", is_error=True)
        details = str(arguments.get("details") or "").strip()
        try:
            principal = _principal(context)
            link_call = _is_link_session(database_url, principal.session_id)
            conversation_id = handed.get(context.voice_session_id) or _target_conversation(
                database_url, principal, link_call=link_call)
            if conversation_id is None:
                conversation_id = runtime.store.create(principal, VOICE_REQUESTS_KEY).conversation_id
                runtime.store.set_title_if_empty(principal, conversation_id, "Voice requests")
            text = ("[Spoken on a voice call] " + request
                    + (f"\n\nDetails from the call: {details}" if details else ""))[:16000]
            key = f"voice-{context.voice_session_id}-{context.tool_call_id or 'call'}"[:200]
            try:
                status = _submit(principal, conversation_id, key, text)
            except ConflictError:
                # That chat stayed busy: start a fresh one rather than lose the request.
                conversation_id = runtime.store.create(
                    principal, f"{VOICE_REQUESTS_KEY}:{context.voice_session_id}").conversation_id
                runtime.store.set_title_if_empty(principal, conversation_id, "Voice requests")
                status = _submit(principal, conversation_id, key, text)
        except Exception as error:  # Voice explains the actual failure.
            logger.warning("voice_coordinator_hand_off_failed")
            return ToolInvocationResult(f"The hand-off failed: {error}", is_error=True)
        handed[context.voice_session_id] = conversation_id
        if on_hand_off is not None:
            try:
                on_hand_off(context.voice_session_id, conversation_id)
            except Exception:
                logger.warning("voice_coordinator_hand_off_watch_failed")
        title = ""
        try:
            title = runtime.store.load(principal, conversation_id).title
        except Exception:
            pass
        where = "your Link chat" if link_call else "Chat"
        return ToolInvocationResult(
            f"Handed to the coordinator. It replies in {where}" + (f" '{title}'" if title else "")
            + ". Approvals it needs appear on the phone or in Chat.",
            {"status": "handed_off", "conversationId": conversation_id, "turnId": status["turnId"]},
            provider_session_update=voice_modes.restore_primary(context.voice_session_id),
        )

    def coordinator_status(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        coordinator = getattr(runtime, "background_coordinator", None)
        if coordinator is None:
            return ToolInvocationResult("The coordinator is unavailable.", is_error=True)
        try:
            principal = _principal(context)
            conversation_id = (handed.get(context.voice_session_id or "")
                               or _target_conversation(database_url, principal,
                                                       link_call=_is_link_session(database_url, principal.session_id)))
            if conversation_id is None:
                return ToolInvocationResult("The coordinator has no work from you yet.", {"openWork": [], "scheduled": []})
            state = coordinator.conversation_state(OwnerScope(principal.user_id, principal.workspace_id),
                                                   conversation_id, since=None)
            page = runtime.store.display_history(principal, conversation_id, limit=6, include_background=True)
        except Exception as error:
            return ToolInvocationResult(f"Couldn't read the coordinator's status: {error}", is_error=True)
        replies = [t["answer"] for t in page["turns"] if t.get("answer")]
        data = {
            "openWork": state.get("openWork", []),
            "scheduled": state.get("scheduled", []),
            "pendingApprovals": state.get("pendingApprovals", []),
            "scratchpad": state.get("scratchpad"),
            "latestReply": (replies[-1][:1500] if replies else None),
        }
        return ToolInvocationResult(
            f"{len(data['openWork'])} open item(s), {len(data['scheduled'])} scheduled, "
            f"{len(data['pendingApprovals'])} waiting for approval.", data)

    catalog.register(ToolDefinition(
        tool_id="builtin.voice.coordinator-hand-off.v1", name=GOAL_SUBMIT_TOOL,
        description=("Hand the user's request to their Vault coordinator, who does the work and replies in the "
                     "user's chat. Pass the request in the user's own words, including any time or schedule, "
                     "and any details from this call it needs. Call it once per request."),
        input_schema={"type": "object", "properties": {
            "request": {"type": "string", "minLength": 1, "maxLength": 8000,
                        "description": "The user's request, in their words, with any time or schedule."},
            "details": {"type": "string", "maxLength": 8000,
                        "description": "Context from this call the coordinator needs (names, places, constraints)."},
        }, "required": ["request"], "additionalProperties": False},
        handler=hand_off, effect_class="write", audiences=frozenset({AgentKind.VOICE}),
    ))
    catalog.register(ToolDefinition(
        tool_id="builtin.voice.coordinator-status.v1", name=STATUS_TOOL,
        description=("What the user's Vault coordinator is working on: open work, scheduled reminders, follow-ups "
                     "and routines with their next run, approvals waiting for the user, and its latest reply."),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=coordinator_status, effect_class="read", audiences=frozenset({AgentKind.VOICE}),
    ))
