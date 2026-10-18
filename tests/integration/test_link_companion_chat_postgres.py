"""Link Companion owner chat over the real composed Vault: pairing credential, chat, history, revocation."""
import base64
import json
from io import BytesIO
from time import monotonic, sleep

import psycopg
from PIL import Image

from tests.integration.test_mounted_voice_decision_review_postgres import mounted  # noqa: F401
from tests.integration.test_genui_conversation_postgres import finish


def _image(fmt):
    buffer = BytesIO()
    Image.new("RGB", (8, 8), (200, 40, 120)).save(buffer, format=fmt)
    return base64.b64encode(buffer.getvalue()).decode()


def _pair(m, poll="poll-secret"):
    started = m.post("/link-companion/pairing/start", {"displayName": "This computer", "pollToken": poll}, {})
    assert started.status_code == 201
    code, pairing = started.payload["pairingCode"], started.payload["pairingId"]
    shown = m.app.handle(method="GET", target=f"/link-companion/pairing/{code}", headers=m.headers)
    assert shown.status_code == 200
    approved = m.post(f"/link-companion/pairing/{pairing}/approve", {}, m.headers)
    assert approved.status_code == 200 and approved.payload["status"] == "paired"
    assert "companionToken" not in approved.payload
    first = m.post("/link-companion/pairing/status", {"pairingId": pairing, "pollToken": poll}, {})
    again = m.post("/link-companion/pairing/status", {"pairingId": pairing, "pollToken": poll}, {})
    assert first.payload["status"] == "approved" and len(first.payload["companionToken"]) > 40
    assert again.payload == {"status": "approved"}, "credential must be delivered exactly once"
    return first.payload["companionToken"], pairing


def _chat(m, method, path, token, payload=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    body = json.dumps(payload).encode() if payload is not None else b""
    return m.app.handle(method=method, target=f"/link-companion/chat/{path}", headers=headers, body=body)


def _run(m, token, run_id):
    deadline = monotonic() + 15
    while monotonic() < deadline:
        response = _chat(m, "GET", f"runs/{run_id}", token)
        assert response.status_code == 200, response.payload
        if response.payload["state"] not in {"queued", "running"}:
            return response.payload
        sleep(0.05)
    raise AssertionError("bounded companion run did not finish")


def test_companion_owner_chat_end_to_end(mounted):
    m = mounted
    runtime = m.app._conversation_runtime
    runtime.memories._embedder_factory = None
    seen = []

    async def runner(**kwargs):
        seen.append(kwargs)
        return finish(kwargs, "Hello from Vault.")

    runtime.runner = runner
    assert _chat(m, "GET", "health", None).payload == {"ready": False, "images": False}

    token, pairing = _pair(m)
    assert _chat(m, "GET", "health", None).payload == {"ready": True, "images": True}

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
    assert done == {"state": "completed", "session_id": session, "text": "Hello from Vault."}
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
                    {"draft_id": "draft-1", "revision": 1, "text": "What did I say about Dana last week?"})
    assert drafted.status_code == 202 and isinstance(drafted.payload["state"], str), drafted.payload
    status = _chat(m, "GET", f"sessions/{session}/draft?draft_id=draft-1&revision=1", token)
    assert status.status_code == 200 and set(status.payload) == {"revision", "state", "memories", "tools"}
    assert _chat(m, "DELETE", f"sessions/{session}/draft", token).status_code == 200

    # The phone conversation is the owner's normal Vault chat.
    listed = m.app.handle(method="GET", target="/conversations", headers=m.headers).payload["items"]
    assert any(item["conversationId"] == session for item in listed)

    # Safe codes only.
    assert _chat(m, "GET", "sessions/missing/messages", token).payload == {"error": {"code": "not_found", "retryable": False}}
    assert _chat(m, "GET", "runs/missing", token).payload == {"error": {"code": "not_found", "retryable": False}}
    assert _chat(m, "POST", f"sessions/{session}/messages", token, {"text": ""}).payload == {"error": {"code": "rejected", "retryable": False}}
    too_many = [{"media_type": "image/png", "data": _image("PNG")}] * 5
    assert _chat(m, "POST", f"sessions/{session}/messages", token,
                 {"text": "x", "images": too_many}).payload == {"error": {"code": "rejected", "retryable": False}}
    assert _chat(m, "POST", f"sessions/{session}/messages", token,
                 {"text": "x", "images": [{"media_type": "image/bmp", "data": _image("BMP")}]}).payload == {"error": {"code": "rejected", "retryable": False}}
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
    assert _chat(m, "GET", "health", None).payload == {"ready": False, "images": False}
    with psycopg.connect(m.url) as connection:
        reasons = {r[0]: r[1] for r in connection.execute(
            "SELECT pairing_id, revocation_reason FROM vault_private.link_companion_pairings").fetchall()}
    assert reasons[pairing] == "replaced_by_new_pairing"
    assert "owner_unpaired" in reasons.values()
