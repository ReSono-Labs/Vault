"""Link Companion owner chat over the real composed Vault: pairing credential, chat, history, revocation."""
import base64
import json
from io import BytesIO
from time import monotonic, sleep

import psycopg
from PIL import Image

from tests.support.genui_conversation import finish
from tests.support.link_companion_chat import _pair, _chat, _run


def _image(fmt):
    buffer = BytesIO()
    Image.new("RGB", (8, 8), (200, 40, 120)).save(buffer, format=fmt)
    return base64.b64encode(buffer.getvalue()).decode()


def test_companion_owner_chat_end_to_end(mounted):
    m = mounted
    runtime = m.app._conversation_runtime
    runtime.memories._embedder_factory = None
    seen = []

    async def runner(**kwargs):
        seen.append(kwargs)
        return finish(kwargs, "Hello from Vault.")

    runtime.runner = runner
    assert _chat(m, "GET", "health", None).payload == {"ready": False, "images": False, "linkTools": False}

    token, pairing = _pair(m)
    assert _chat(m, "GET", "health", None).payload | {"linkTools": None} == {"ready": True, "images": True, "linkTools": None}

    # Only the companion credential opens chat: not nothing, not a forged token, not the owner's browser session.
    assert _chat(m, "POST", "sessions", None, {}).payload == {"error": {"code": "not_paired", "retryable": False}}
    assert _chat(m, "POST", "sessions", "forged", {}).status_code == 401
    cookie_only = m.app.handle(method="POST", target="/link-companion/chat/sessions", headers=m.headers, body=b"{}")
    assert cookie_only.status_code == 401

    created = _chat(m, "POST", "sessions", token, {})
    assert created.status_code == 201
    session = created.payload["id"]
    sent = _chat(m, "POST", f"sessions/{session}/messages", token, {
        "text": "What is in these pictures?", "client_message_id": "phone-1",
        "images": [{"media_type": "image/png", "data": _image("PNG")},
                   {"media_type": "image/gif", "data": _image("GIF")}]})
    assert sent.status_code == 202, sent.payload
    run_id = sent.payload["run_id"]
    retried = _chat(m, "POST", f"sessions/{session}/messages", token, {
        "text": "What is in these pictures?", "client_message_id": "phone-1",
        "images": [{"media_type": "image/png", "data": _image("PNG")},
                   {"media_type": "image/gif", "data": _image("GIF")}]})
    assert retried.status_code == 202 and retried.payload["run_id"] == run_id, "retries must not send twice"

    done = _run(m, token, run_id)
    # text stays for older clients; messages[] is the ordered bubble list for new clients.
    assert done == {"state": "completed", "session_id": session, "text": "Hello from Vault.",
                    "messages": [{"text": "Hello from Vault."}]}
    assert len(seen) == 1
    with psycopg.connect(m.url) as connection:
        mimes = [r[0] for r in connection.execute(
            "SELECT mime FROM vault_private.vault_conversation_attachments WHERE conversation_id=%s ORDER BY name",
            (session,)).fetchall()]
    assert mimes == ["image/png", "image/png"], "GIF arrives as its first frame in PNG"

    history = _chat(m, "GET", f"sessions/{session}/messages", token)
    assert history.status_code == 200
    messages = history.payload["messages"]
    assert [(x["role"], x["text"]) for x in messages] == [
        ("user", "What is in these pictures?"), ("assistant", "Hello from Vault.")]
    assert all(isinstance(x["timestamp"], int) and x["timestamp"] > 1_700_000_000 for x in messages)
    assert set(messages[0]) == {"id", "role", "text", "timestamp"}

    # Live preparation while typing goes through the same engine as browser Chat.
    drafted = _chat(m, "POST", f"sessions/{session}/draft", token,
                    {"draft_id": "draft-1", "revision": 1, "text": "What did I say about Dana last week?", "wait": 0.5})
    assert drafted.status_code == 200 and set(drafted.payload) == {"revision", "state", "memories", "tools"}, drafted.payload
    status = _chat(m, "POST", f"sessions/{session}/draft/status", token, {"draft_id": "draft-1", "revision": 1})
    assert status.status_code == 200 and set(status.payload) == {"revision", "state", "memories", "tools"}
    assert _chat(m, "POST", f"sessions/{session}/draft/clear", token, {}).status_code == 200

    # The phone conversation is the owner's normal Vault chat.
    listed = m.app.handle(method="GET", target="/conversations", headers=m.headers).payload["items"]
    assert any(item["conversationId"] == session for item in listed)

    # Safe codes only.
    assert _chat(m, "GET", "sessions/missing/messages", token).payload == {"error": {"code": "not_found", "retryable": False}}
    assert _chat(m, "GET", "runs/missing", token).payload == {"error": {"code": "not_found", "retryable": False}}
    # A refusal says why in Vault's own fixed wording (never the message text or image bytes).
    def rejected(payload):
        error = payload["error"]
        return (error["code"], error["retryable"]) == ("rejected", False) and bool(error.get("reason"))
    empty = _chat(m, "POST", f"sessions/{session}/messages", token, {"text": ""}).payload
    assert rejected(empty) and empty["error"]["reason"] == "empty message"
    too_many = [{"media_type": "image/png", "data": _image("PNG")}] * 5
    assert rejected(_chat(m, "POST", f"sessions/{session}/messages", token,
                          {"text": "x", "images": too_many}).payload)
    assert rejected(_chat(m, "POST", f"sessions/{session}/messages", token,
                          {"text": "x", "images": [{"media_type": "image/bmp", "data": _image("BMP")}]}).payload)
    image_only = _chat(m, "POST", f"sessions/{session}/messages", token,
                       {"images": [{"media_type": "image/jpeg", "data": _image("JPEG")}]})
    assert image_only.status_code == 202 and _run(m, token, image_only.payload["run_id"])["state"] == "completed"

    # The same credential now authorises Agent Network apply (A2A is off here, so 400 rather than 403).
    apply = m.app.handle(method="POST", target="/link-companion/agent-network/apply",
                         headers={"Authorization": f"Bearer {token}"}, body=b'{"inbound":[],"outbound":[]}')
    assert apply.status_code in (200, 400), apply.payload
    unauth = m.app.handle(method="POST", target="/link-companion/agent-network/apply", headers={},
                          body=b'{"inbound":[],"outbound":[]}')
    assert unauth.status_code == 403

    # Re-pairing replaces the companion; the old credential stops working immediately.
    second, _ = _pair(m, poll="poll-two")
    assert _chat(m, "GET", f"sessions/{session}/messages", token).status_code == 401
    assert _chat(m, "GET", f"sessions/{session}/messages", second).status_code == 200

    # Owner unpair revokes it and records why.
    assert m.post("/link-companion/unpair", {}, m.headers).status_code == 200
    assert _chat(m, "GET", f"sessions/{session}/messages", second).status_code == 401
    assert _chat(m, "GET", "health", None).payload == {"ready": False, "images": False, "linkTools": False}
    with psycopg.connect(m.url) as connection:
        reasons = {r[0]: r[1] for r in connection.execute(
            "SELECT pairing_id, revocation_reason FROM vault_private.link_companion_pairings").fetchall()}
    assert reasons[pairing] == "replaced_by_new_pairing"
    assert "owner_unpaired" in reasons.values()


def test_a_running_companion_turn_reports_its_tool_steps_without_their_content(mounted):
    """Link #107: while a phone turn runs, the run status carries what the turn is doing: tool
    names and states and the time of its latest event; never a tool's arguments or result, never
    the reply's text. A finished turn carries no activity."""
    import asyncio
    import threading
    from types import SimpleNamespace as NS

    from tests.support.genui_conversation import call, grant

    m = mounted
    runtime = m.app._conversation_runtime
    runtime.memories._embedder_factory = None
    grant(m)
    release = threading.Event()

    async def runner(**kwargs):
        tool, raw = call(kwargs, "r1", "call-contacts", "contacts_search", {"query": "secret-name"})
        await tool.on_invoke_tool(NS(tool_call_id="call-contacts"), raw)
        while not release.is_set():
            await asyncio.sleep(0.02)
        return finish(kwargs, "Found them.")

    runtime.runner = runner
    token, _ = _pair(m)
    session = _chat(m, "POST", "sessions", token, {}).payload["id"]
    sent = _chat(m, "POST", f"sessions/{session}/messages", token, {"text": "Who is secret-name?", "client_message_id": "phone-a"})
    run_id = sent.payload["run_id"]
    deadline = monotonic() + 15
    while True:
        running = _chat(m, "GET", f"runs/{run_id}", token).payload
        steps = running.get("activity", {}).get("steps")
        if steps and steps[-1]["status"] != "in_progress":
            break
        # The call shows while it runs, then with its outcome.
        assert steps in (None, [], [{"title": "contacts search", "status": "in_progress"}]), running
        assert monotonic() < deadline, running
        sleep(0.05)
    try:
        assert running["state"] == "running"
        activity = running["activity"]
        assert activity["steps"] == [{"title": "contacts search", "status": "completed"}], activity
        assert activity["replying"] is False and activity["plan"] == []
        assert isinstance(activity["updated_at"], int) and activity["updated_at"] > 1_700_000_000
        assert "secret" not in json.dumps(running), running
    finally:
        release.set()
    done = _run(m, token, run_id)
    assert done["state"] == "completed" and "activity" not in done, done
