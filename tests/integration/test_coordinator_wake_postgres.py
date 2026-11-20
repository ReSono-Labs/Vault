"""The coordinator behaves like a bot (2026-11-18): it wakes itself in its chat and follows through.

End to end on the real composition, durable worker and Link chat surface:
- a due follow-up wakes the coordinator in the originating chat, which does the work and replies;
- an owner approval wakes it to continue the plan, without another user message;
- a Vault-started turn that has nothing to say (NO_RESPONSE) stays hidden;
- the owner's message preempts a Vault-started turn and still receives its unseen updates,
  even when the client's history version predates that turn.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from time import sleep
from types import SimpleNamespace as NS

import psycopg
import pytest

from app.vault_runtime.composition import build_local_app
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from tests.support.background_mounted_runtime import (
    _api, _boot_config, _onboard_owner, _reset_schemas, _wait_until,
)
from tests.support.genui_conversation import call, finish
from tests.support.link_companion_chat import _chat, _pair, _run


def _state(kwargs):
    return json.loads(kwargs["input_text"]).get("coordinatorState") or {}


def _latest_input(kwargs):
    return json.loads(kwargs["input_text"])["history"][-1]["input"]


def _messages(holder, token, conversation):
    response = _chat(holder, "GET", f"sessions/{conversation}/messages", token)
    assert response.status_code == 200, response.payload
    return response.payload["messages"]


def _due_routines(url, conversation, goal_type):
    with psycopg.connect(url) as connection:
        return connection.execute(
            """SELECT routine_id, next_due_at, status FROM vault_private.vault_background_routines
               WHERE template_json->'destination'->>'conversation_id'=%s
                 AND template_json->'request'->>'goal_type'=%s ORDER BY created_at""",
            (conversation, goal_type),
        ).fetchall()


def test_coordinator_wakes_in_its_chat_and_follows_through(tmp_path, monkeypatch):
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
    coordinator = runtime.background_coordinator
    assert coordinator is not None and coordinator.jobs._wake_handler is not None
    holder = NS(app=app, headers=headers, principal=principal, url=url,
                post=lambda path, payload, hdrs: _api(app, "POST", path, hdrs, payload))
    token, _ = _pair(holder)
    conversation = _chat(holder, "POST", "sessions", token, {}).payload["id"]

    seen = {"wakes": [], "user": []}
    blocking = {"on": False}
    fail_next_wake = {"on": False}
    slow_gate = threading.Event()

    async def runner(**kwargs):
        instructions = kwargs["instructions"]
        assert instructions.startswith("You are the Vault coordinator")
        state = _state(kwargs)
        names = {tool.name for tool in kwargs["function_tools"]}
        if "This turn was started by Vault" in instructions:
            seen["wakes"].append(state)
            assert _latest_input(kwargs).startswith("[Automated message from Vault, not from the user]")
            # Owner-message tools never reach a turn Vault started on its own.
            assert "memory_confirm_action" not in names and "memory_prepare_forget" not in names
            updates = state["updatesSinceLastReply"]
            assert updates, state
            kinds = {item["type"] for item in updates}
            if fail_next_wake["on"]:
                fail_next_wake["on"] = False
                raise RuntimeError("Error code: 429 usage_limit_reached")
            if blocking["on"]:
                while not kwargs["cancel_requested"]():
                    await asyncio.sleep(0.05)
                raise asyncio.CancelledError()
            if "check_in" in kinds:
                # Rakazo strategic initiative: only ask or message; no action tools (display cards only).
                assert names <= {"present_ui"}, names
                assert "Draft the investor update" in _latest_input(kwargs)
                assert "exactly NO_RESPONSE" in _latest_input(kwargs)
                return finish(kwargs, "Checking in: the investor update draft is still open. Shall I use last month's numbers?")
            if "routine_run" in kinds:
                run = next(item for item in updates if item["type"] == "routine_run")
                assert run["summary"] == "Send me the AI headlines"
                assert "do not schedule it again" in _latest_input(kwargs)
                tool, raw = call(kwargs, "routine-work", "routine-work-call", "scratchpad_add", {
                    "title": "Track lab B funding follow-up"})
                assert not json.loads(await tool.on_invoke_tool(NS(tool_call_id="routine-work-call"), raw))["isError"]
                return finish(kwargs, "Morning AI headlines: model A shipped, lab B raised. I'm tracking lab B.")
            if "approval" in kinds:
                approval = next(item for item in updates if item["type"] == "approval")
                assert approval["decision"] == "approved" and approval["kind"] == "worker_create"
                assert approval["receipt"].get("worker_id")
                return finish(kwargs, "Your weekday brief is saved for 8:00 on weekdays.")
            note = next(item for item in updates if item["type"] == "follow_up")["summary"]
            if note.startswith("Quietly"):
                return finish(kwargs, "NO_RESPONSE")
            assert note == "Find the AI headlines and report them here."
            # Vault (2026-11-19): in a turn Vault started, the coordinator's own follow-up is saved at once.
            tool, raw = call(kwargs, "wake-follow", "wake-follow-call", "background_follow_up", {
                "note": "Check whether lab B's funding news is confirmed.", "delay_minutes": 120})
            saved = json.loads(await tool.on_invoke_tool(NS(tool_call_id="wake-follow-call"), raw))
            assert not saved["isError"] and saved["structuredContent"]["status"] == "scheduled", saved
            return finish(kwargs, "Here are the AI headlines: model A shipped, lab B raised.")
        text = _latest_input(kwargs)
        seen["user"].append((text, state))
        if text.startswith("In ten minutes"):
            tool, raw = call(kwargs, "follow-up", "follow-call", "background_follow_up", {
                "note": "Find the AI headlines and report them here.", "delay_minutes": 10,
            })
            result = json.loads(await tool.on_invoke_tool(NS(tool_call_id="follow-call"), raw))
            assert not result["isError"], result
            return finish(kwargs, "I'll check the AI headlines in ten minutes and report here.")
        if text.startswith("Every morning"):
            tool, raw = call(kwargs, "own-routine", "own-routine-call", "background_propose_routine", {
                "objective": "Send me the AI headlines", "cron": "0 8 * * *",
                "timezone": "America/New_York", "tool_names": ["web_search"],
            })
            result = json.loads(await tool.on_invoke_tool(NS(tool_call_id="own-routine-call"), raw))
            assert not result["isError"] and result["structuredContent"]["status"] == "scheduled", result
            return finish(kwargs, "Saved: AI headlines every day at 8:00.")
        if text.startswith("Every weekday"):
            tool, raw = call(kwargs, "specialist", "specialist-call", "background_propose_specialist", {
                "role_key": "briefer", "purpose": "Prepare daily briefs",
                "instructions": "Summarize the day.", "tool_names": [],
            })
            created = json.loads(await tool.on_invoke_tool(NS(tool_call_id="specialist-call"), raw))
            assert not created["isError"] and created["structuredContent"]["status"] == "created", created
            tool, raw = call(kwargs, "routine", "routine-call", "background_propose_routine", {
                "objective": "Brief me on my day", "cron": "0 8 * * 1-5", "role_key": "briefer",
                "timezone": "America/New_York", "tool_names": [],
            })
            result = json.loads(await tool.on_invoke_tool(NS(tool_call_id="routine-call"), raw))
            # Vault (2026-11-19): the specialist routine the owner asked for is saved at once.
            assert not result["isError"] and result["structuredContent"]["status"] == "scheduled", result
            # Giving the specialist memory search is privacy-sensitive, so that still asks.
            tool, raw = call(kwargs, "memory", "memory-call", "background_propose_memory_lookup", {"role_key": "briefer"})
            result = json.loads(await tool.on_invoke_tool(NS(tool_call_id="memory-call"), raw))
            assert not result["isError"] and result["structuredContent"]["status"] == "waiting_approval", result
            return finish(kwargs, "The briefer is set for weekdays at 8. Approve its memory search and I'll confirm.")
        if text.startswith("Track the investor"):
            tool, raw = call(kwargs, "pad", "pad-call", "scratchpad_add", {"title": "Draft the investor update"})
            assert not json.loads(await tool.on_invoke_tool(NS(tool_call_id="pad-call"), raw))["isError"]
            return finish(kwargs, "Added to my open work.")
        if text.startswith("Slow question"):
            await asyncio.to_thread(slow_gate.wait, 20)
            return finish(kwargs, "Slow answer.")
        if text.startswith("Quiet check"):
            tool, raw = call(kwargs, "quiet", "quiet-call", "background_follow_up", {
                "note": "Quietly confirm nothing is pending.", "delay_minutes": 5,
            })
            assert not json.loads(await tool.on_invoke_tool(NS(tool_call_id="quiet-call"), raw))["isError"]
            return finish(kwargs, "Noted.")
        if text.startswith("Long check"):
            tool, raw = call(kwargs, "long", "long-call", "background_follow_up", {
                "note": "Find the AI headlines and report them here.", "delay_minutes": 3,
            })
            assert not json.loads(await tool.on_invoke_tool(NS(tool_call_id="long-call"), raw))["isError"]
            return finish(kwargs, "Will do.")
        return finish(kwargs, "Answering you now.")

    runtime.runner = runner

    def say(text):
        sent = _chat(holder, "POST", f"sessions/{conversation}/messages", token, {"text": text})
        assert sent.status_code == 202, sent.payload
        assert _run(holder, token, sent.payload["run_id"])["state"] == "completed"
        return sent.payload["run_id"]

    def fire(goal_type):
        routine_id, due, status = _due_routines(url, conversation, goal_type)[-1]
        assert status == "active"
        assert coordinator.jobs._routines.tick(due) >= 1
        return routine_id

    # 1. "In ten minutes" is saved as the coordinator's own follow-up: no approval card.
    say("In ten minutes check the AI headlines")
    with psycopg.connect(url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM vault_private.vault_background_actions WHERE state='pending'").fetchone() == (0,)
    assert len(_due_routines(url, conversation, "follow_up")) == 1

    # 2. When it is due, the durable worker runs it and wakes the coordinator here, unprompted.
    fire("follow_up")
    _wait_until(lambda: (_messages(holder, token, conversation)[-1]["text"]
                         == "Here are the AI headlines: model A shipped, lab B raised."), timeout=30)
    shown = _messages(holder, token, conversation)
    assert not any(m["role"] == "user" and "[Vault update" in (m["text"] or "") for m in shown)
    assert not any("Find the AI headlines and report them here." == m["text"] for m in shown)  # internal note
    assert [m["role"] for m in shown] == ["user", "assistant", "assistant"]
    with psycopg.connect(url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM vault_private.vault_notifications WHERE kind='assistant_message'"
        ).fetchone()[0] >= 1
    link_principal = None
    with psycopg.connect(url) as connection:
        session_id, = connection.execute(
            "SELECT activity_session_id FROM vault_private.vault_conversations WHERE conversation_id=%s",
            (conversation,)).fetchone()
    link_principal = LocalIdentityRepository(database_url=url).resolve_review_principal(
        principal.user_id, principal.workspace_id, session_id)
    assert runtime.wake(link_principal, conversation)["state"] == "idle"  # nothing new: no extra turn

    # 3. An owner approval wakes the coordinator to confirm and continue, without a second request.
    sent = _chat(holder, "POST", f"sessions/{conversation}/messages", token, {"text": "Every weekday at 8 brief me on my day"})
    assert sent.status_code == 202, sent.payload
    turn = sent.payload["run_id"]
    permission = _wait_until(lambda: _chat(holder, "GET", f"runs/{turn}", token).payload.get("permission_request"))
    decided = _chat(holder, "POST", f"runs/{turn}/permission", token, {
        "action_id": permission["action_id"], "action_hash": permission["action_hash"],
        "choice": "allow_once", "decision_id": "approve-weekday-brief",
    })
    assert decided.status_code == 200, decided.payload
    # The phone's own run waits for the coordinator's confirmation and ends with it.
    final = _run(holder, token, turn)
    assert final["state"] == "completed", final
    assert final["messages"][-1]["text"] == "Your weekday brief is saved for 8:00 on weekdays.", final
    assert "Your weekday brief is saved" in final["text"]
    _wait_until(lambda: (_messages(holder, token, conversation)[-1]["text"]
                         == "Your weekday brief is saved for 8:00 on weekdays."), timeout=30)
    assert len(_due_routines(url, conversation, "routine")) == 1

    # 3b. The coordinator's own routine is saved at once (Rakazo schedule_create) and, when due,
    #     wakes it here to do the work with its tools and report, then stays scheduled.
    say("Every morning at 8 send me the AI headlines")
    with psycopg.connect(url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM vault_private.vault_background_actions WHERE state='pending'").fetchone() == (0,)
    own_id = fire("self_routine")
    _wait_until(lambda: _messages(holder, token, conversation)[-1]["text"].startswith("Morning AI headlines"), timeout=30)
    assert _due_routines(url, conversation, "self_routine")[-1][2] == "active"

    # 4. A Vault-started turn with nothing to say stays out of the chat.
    say("Quiet check in five minutes")
    before = len(_messages(holder, token, conversation))
    fire("follow_up")
    _wait_until(lambda: len(seen["wakes"]) == 4, timeout=30)
    with psycopg.connect(url) as connection:
        _wait_until(lambda: connection.execute(
            """SELECT count(*) FROM vault_private.vault_conversation_turns
               WHERE conversation_id=%s AND submission_key LIKE 'vault-wake:%%' AND state='completed'""",
            (conversation,)).fetchone()[0] == 4)
    assert len(_messages(holder, token, conversation)) == before

    # 5. The owner's message wins over a running Vault turn, even from a stale history version,
    #    and it still sees the update that turn did not finish handling.
    say("Long check in three minutes")
    stale_version = runtime.store.load(link_principal, conversation).history_version
    blocking["on"] = True
    fire("follow_up")
    wake_turn = _wait_until(lambda: (lambda active: active if active and active[1].startswith("vault-wake:") else None)(
        runtime.store.active_turn(link_principal, conversation)), timeout=30)
    blocking["on"] = False
    submitted = runtime.submit(link_principal, conversation, submission_key="link:owner-after-wake",
                               input_text="What did you find?", expected_history_version=stale_version)
    assert _run(holder, token, submitted["turnId"])["state"] == "completed"
    assert runtime.store.status(link_principal, conversation, wake_turn[0])["state"] == "interrupted"
    text, state = seen["user"][-1]
    assert text == "What did you find?"
    assert any(item["type"] == "follow_up" for item in state["updatesSinceLastReply"]), state
    shown = _messages(holder, token, conversation)
    assert shown[-1]["text"] == "Answering you now." and shown[-2]["text"] == "What did you find?"

    # 5b. An update that lands while the chat is busy is answered once the chat is free.
    headlines = "Here are the AI headlines: model A shipped, lab B raised."
    say("In ten minutes check the AI headlines")
    busy = _chat(holder, "POST", f"sessions/{conversation}/messages", token, {"text": "Slow question"})
    assert busy.status_code == 202, busy.payload
    _wait_until(lambda: runtime.store.active_turn(link_principal, conversation) is not None)
    fire("follow_up")
    sleep(4)  # the wake finds the chat busy and asks again
    assert _messages(holder, token, conversation)[-1]["text"] != headlines
    slow_gate.set()
    _wait_until(lambda: _messages(holder, token, conversation)[-1]["text"] == headlines, timeout=40)
    assert _messages(holder, token, conversation)[-2]["text"] == "Slow answer."

    # 5c. A Vault-started turn that fails (provider limit) is retried with backoff, then answers.
    monkeypatch.setattr("app.vault_runtime.conversation.runtime.WAKE_RETRY_MINUTES", (0.03, 0.03))
    say("In ten minutes check the AI headlines")
    fail_next_wake["on"] = True
    fire("follow_up")
    _wait_until(lambda: not fail_next_wake["on"], timeout=30)
    _wait_until(lambda: (_messages(holder, token, conversation)[-1]["text"] == headlines
                         and _messages(holder, token, conversation)[-2]["text"] == "I'll check the AI headlines in ten minutes and report here."),
                timeout=40)
    with psycopg.connect(url) as connection:
        assert connection.execute(
            """SELECT count(*) FROM vault_private.vault_conversation_turns
               WHERE conversation_id=%s AND submission_key LIKE 'vault-wake:%%' AND state='failed'""",
            (conversation,)).fetchone()[0] == 1

    # 6. Daily check-in (Rakazo strategic initiative): a stale open scratchpad item gets one
    #    proactive nudge per day, from a turn that has no tools.
    say("Track the investor update for me")
    with psycopg.connect(url) as connection:
        connection.execute("""UPDATE vault_private.vault_coordinator_scratchpad SET updated_at=now()-interval '2 days'
                              WHERE title='Draft the investor update'""")
    assert coordinator.daily_checkins() == 1
    assert coordinator.daily_checkins() == 0  # once a day per chat
    _wait_until(lambda: _messages(holder, token, conversation)[-1]["text"].startswith("Checking in:"), timeout=30)

    # 7. Clients cannot pose as Vault.
    with pytest.raises(Exception):
        runtime.submit(link_principal, conversation, submission_key="vault-wake:forged",
                       input_text="hi", expected_history_version=stale_version)
