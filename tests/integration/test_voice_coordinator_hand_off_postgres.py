"""Voice hands work to the chat coordinator (2026-11-18), end to end on the real composition.

- Coordinator intake is the only way to coordinator_hand_off on Realtime; the hand-off posts the
  spoken request as the owner's own message in their Link chat and returns Voice to Primary.
- The coordinator does the work there; an approval it needs is listed for the call
  (pending_hand_off_approvals, which the phone call shows) and can be answered from the call.
- After the call, the same approval rides on the phone's next run in that chat (Link's sheet).
- coordinator_status reports what the coordinator carries.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace as NS

import psycopg
import pytest

from app.vault_runtime.background_agent.coordination_contracts import OwnerScope
from app.vault_runtime.composition import build_local_app
from app.vault_runtime.link_companion.chat import decide_background_action, is_background_action
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.definitions import ToolInvocationContext
from app.vault_runtime.voice.modes import GOAL_INTAKE_MODE
from tests.support.background_mounted_runtime import (
    _api, _boot_config, _onboard_owner, _reset_schemas, _wait_until,
)
from tests.support.genui_conversation import call, finish
from tests.support.link_companion_chat import _chat, _pair, _run


def test_voice_hands_requests_to_the_coordinator_and_its_approvals_reach_the_phone(tmp_path, monkeypatch):
    url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Exact isolated database required")
    _reset_schemas(url)
    monkeypatch.setattr("app.vault_runtime.memory.service.MemoryService.ensure_vectors", lambda *a, **k: (0, 0))
    monkeypatch.setattr("app.vault_runtime.agent_network.service.A2AService.start", lambda *_: None)
    monkeypatch.setattr("app.vault_runtime.agent_network.inbound.A2AInboundHttpServer.start", lambda *_: None)
    monkeypatch.setattr("app.vault_runtime.extensions.mcp_runtime.McpRuntimeSupervisor.restore_on_boot", lambda *_: None)

    app = build_local_app(_boot_config(tmp_path, url))
    principal, headers = _onboard_owner(app)
    runtime = app._conversation_runtime
    runtime.memories._embedder_factory = None
    runtime.title_runner = None
    holder = NS(app=app, headers=headers, principal=principal, url=url,
                post=lambda path, payload, hdrs: _api(app, "POST", path, hdrs, payload))
    token, _ = _pair(holder)
    seen = []

    async def runner(**kwargs):
        latest = json.loads(kwargs["input_text"])["history"][-1]["input"]
        seen.append(latest)
        if "This turn was started by Vault" in kwargs["instructions"]:
            return finish(kwargs, "The briefer's weekday schedule is saved.")
        if latest.startswith("[Spoken on a voice call]"):
            # The owner spoke it: their specialist and its routine are created at once; giving it
            # memory search is privacy-sensitive, so that is what asks.
            tool, raw = call(kwargs, "s", "s-call", "background_propose_specialist", {
                "role_key": "briefer", "purpose": "Daily briefs", "instructions": "Brief the day.", "tool_names": []})
            assert json.loads(await tool.on_invoke_tool(NS(tool_call_id="s-call"), raw))["structuredContent"]["status"] == "created"
            tool, raw = call(kwargs, "r", "r-call", "background_propose_routine", {
                "objective": "Brief me on my day", "cron": "0 8 * * 1-5", "role_key": "briefer",
                "timezone": "America/New_York", "tool_names": []})
            assert json.loads(await tool.on_invoke_tool(NS(tool_call_id="r-call"), raw))["structuredContent"]["status"] == "scheduled"
            tool, raw = call(kwargs, "m", "m-call", "background_propose_memory_lookup", {"role_key": "briefer"})
            assert json.loads(await tool.on_invoke_tool(NS(tool_call_id="m-call"), raw))["structuredContent"]["status"] == "waiting_approval"
            return finish(kwargs, "Approve the briefer's schedule and I'll confirm.")
        return finish(kwargs, "Hello.")

    runtime.runner = runner
    conversation = _chat(holder, "POST", "sessions", token, {}).payload["id"]
    first = _chat(holder, "POST", f"sessions/{conversation}/messages", token, {"text": "hi"}).payload["run_id"]
    assert _run(holder, token, first)["state"] == "completed"
    with psycopg.connect(url) as connection:
        link_session, = connection.execute(
            "SELECT activity_session_id FROM vault_private.vault_conversations WHERE conversation_id=%s",
            (conversation,)).fetchone()
    link_principal = LocalIdentityRepository(database_url=url).resolve_review_principal(
        principal.user_id, principal.workspace_id, link_session)

    # A phone call (Link session): Realtime offers the hand-off only in Coordinator intake.
    voice = app._voice_sessions.create_session(
        user_id=principal.user_id, workspace_id=principal.workspace_id, local_session_id=link_session,
        provider_key="openai", model_key="gpt-realtime", connection_mode="webrtc")
    modes = app._voice_tools._voice_modes if hasattr(app._voice_tools, "_voice_modes") else None
    assert modes is not None
    modes.open_session(voice.voice_session_id, primary_instructions="p", primary_tools=lambda: (),
                       goal_intake_tools=lambda: ())
    context = ToolInvocationContext(agent=AgentKind.VOICE, user_id=principal.user_id,
        workspace_id=principal.workspace_id, local_session_id=link_session,
        voice_session_id=voice.voice_session_id, tool_call_id="hand-1")
    from dataclasses import replace
    definitions = app._voice_tools.definitions(user_id=principal.user_id, workspace_id=principal.workspace_id)
    app._voice_tools._authority.ensure_builtin_grants(user_id=principal.user_id, workspace_id=principal.workspace_id,
                                                      definitions=definitions)
    names = {d.name for d in definitions}
    assert {"coordinator_hand_off", "coordinator_status", "voice_mode_switch"} <= names and "goal_start" not in names
    blocked = app._voice_tools.invoke(name="coordinator_hand_off", arguments={"request": "x"}, context=context)
    assert blocked.is_error  # Primary: intake first
    assert not app._voice_tools.invoke(name="voice_mode_switch", arguments={"modeKey": GOAL_INTAKE_MODE},
                                       context=replace(context, tool_call_id="switch-1")).is_error
    handed = app._voice_tools.invoke(name="coordinator_hand_off", arguments={
        "request": "Create a briefer and have it brief me every weekday at 8",
        "details": "Keep it short"}, context=replace(context, tool_call_id="hand-2"))
    assert not handed.is_error, handed.text
    assert handed.structured_content["conversationId"] == conversation  # their Link chat
    assert handed.provider_session_update is not None and modes.mode(voice.voice_session_id) == "primary"
    assert runtime.voice_hand_offs[voice.voice_session_id] == conversation
    _wait_until(lambda: any(item.startswith("[Spoken on a voice call]") for item in seen))
    shown = _chat(holder, "GET", f"sessions/{conversation}/messages", token).payload["messages"]
    assert any(m["role"] == "user" and "Create a briefer" in m["text"] for m in shown)

    # The coordinator's reply comes back on the call (said by the voice model), once.
    from app.vault_runtime.voice.companion import CompanionCall, CompanionVoiceService
    from app.vault_runtime.voice.coordinator_tools import coordinator_replies
    service = app._companion_voice_service()
    assert service.hand_off_replies is not None and service.hand_offs is runtime.voice_hand_offs
    sent = []
    fake_call = CompanionCall(voice.voice_session_id, link_principal, "", "", None, 60, 60)
    fake_call.protocol = "openai-realtime"
    fake_call.send = lambda event: sent.append(event) or True
    spoken: set[str] = set()
    # Every finished coordinator reply in the chat is said once. A Vault-started turn (the saved
    # routine) can finish before the hand-off reply, so wait for the hand-off reply among them (TST-08).
    def said_texts():
        return [e["item"]["content"][0]["text"] for e in sent if e.get("type") == "conversation.item.create"]
    _wait_until(lambda: (service._hand_off_tick(fake_call, set(), spoken) or True) and any(
        "Approve the briefer's schedule and I'll confirm." in text for text in said_texts()), timeout=20)
    said = next(text for text in said_texts() if "Approve the briefer's schedule" in text)
    assert "[Automated message from Vault" in said
    assert {"type": "response.create"} in sent
    assert any(e["type"] == "coordinator_reply" for e in fake_call.events)
    count = len(sent)
    service._hand_off_tick(fake_call, set(), spoken)
    assert len([e for e in sent[count:] if e.get("type") == "conversation.item.create"]) == 0  # said once
    assert coordinator_replies(runtime)(link_principal, conversation, 0)

    # During the call: the coordinator's approval is listed for the call and answered from it.
    coordinator = runtime.background_coordinator
    owner = OwnerScope(principal.user_id, principal.workspace_id)
    pending = _wait_until(lambda: coordinator.pending_hand_off_approvals(owner, [conversation]))
    assert pending[0]["kind"] == "background" and pending[0]["choices"] == ["allow_once", "deny"]
    action_id = pending[0]["id"]
    assert is_background_action(runtime, link_principal, action_id)

    # After a call: the same approval rides on the phone's next run in that chat.
    nxt = _chat(holder, "POST", f"sessions/{conversation}/messages", token, {"text": "anything else?"}).payload["run_id"]
    permission = _wait_until(lambda: _chat(holder, "GET", f"runs/{nxt}", token).payload.get("permission_request"))
    assert permission["action_id"] == action_id

    # Answered from the call: applied, and the coordinator follows through on its own.
    assert decide_background_action(runtime, link_principal, action_id=action_id, choice="allow_once",
                                    decision_id="voice-test-allow") == "approved"
    assert _run(holder, token, nxt)["state"] == "completed"
    _wait_until(lambda: _chat(holder, "GET", f"sessions/{conversation}/messages", token).payload["messages"][-1]["text"]
                == "The briefer's weekday schedule is saved.", timeout=30)
    assert coordinator.pending_hand_off_approvals(owner, [conversation]) == []

    status = app._voice_tools.invoke(name="coordinator_status", arguments={}, context=replace(context, tool_call_id="status-1"))
    assert not status.is_error
    assert any(item["kind"] == "specialist_routine" for item in status.structured_content["scheduled"])
    assert status.structured_content["latestReply"] == "The briefer's weekday schedule is saved."
