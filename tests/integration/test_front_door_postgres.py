"""Link Front Door v1 over the real composed Vault (shapes from Link connector/sdk/vectors/front-door.json)."""
import base64
import json
from io import BytesIO
from time import monotonic, sleep

from PIL import Image

from tests.support.genui_conversation import finish, grant
from tests.support.link_companion_chat import _chat, _pair
from tests.support.owner_approval_chat import _mount, _turn_with_gated_send


def _fd(m, method, path, token, payload=None, headers=None):
    head = {"Authorization": f"Bearer {token}"} if token else {}
    head |= headers or {}
    body = json.dumps(payload).encode() if payload is not None else b""
    return m.app.handle(method=method, target=path, headers=head, body=body)


def _create(m, token, text, key, conversation="sess-1", previous=None, images=()):
    content = [{"type": "input_text", "text": text}] + [
        {"type": "input_image", "image_url": f"data:image/png;base64,{data}"} for data in images]
    body = {"model": "agent", "input": [{"type": "message", "role": "user", "content": content}],
            "background": True, "store": True,
            "metadata": {"link_message_id": key, "link_conversation": conversation},
            "link": {"sender": {"kind": "owner"}}}
    if previous:
        body["previous_response_id"] = previous
    return _fd(m, "POST", "/v1/responses", token, body, {"Idempotency-Key": key})


def _until(m, token, response_id, done):
    deadline = monotonic() + 15
    while monotonic() < deadline:
        response = _fd(m, "GET", f"/v1/responses/{response_id}", token)
        assert response.status_code == 200, response.payload
        if done(response.payload):
            return response.payload
        sleep(0.05)
    raise AssertionError("front door response did not reach the expected state")


def _png():
    buffer = BytesIO()
    Image.new("RGB", (8, 8), (10, 120, 200)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def test_front_door_turns_history_drafts_cancel_and_auth(mounted):
    m = mounted
    runtime = m.app._conversation_runtime
    runtime.memories._embedder_factory = None
    seen = []

    async def runner(**kwargs):
        seen.append(kwargs)
        return finish(kwargs, "Hi there")

    runtime.runner = runner
    token, _ = _pair(m)

    # Bearer is checked before anything else (adv-01): missing, forged and the browser session are refused.
    assert _fd(m, "GET", "/link/v1/capabilities", None).status_code == 401
    assert _fd(m, "POST", "/v1/responses", "wrong-key-0123456789abcdefghijklmnopqrstuvwxyz",
               {"model": "agent", "input": []}).status_code == 401
    assert m.app.handle(method="GET", target="/link/v1/capabilities", headers=m.headers).status_code == 401

    caps = _fd(m, "GET", "/link/v1/capabilities", token)
    assert caps.status_code == 200
    assert caps.payload["front_door_version"] == "1" and caps.payload["level"] == "L1"
    ops = caps.payload["operations"]
    assert ops["responses_create"] and ops["responses_background"] and ops["responses_poll"] and ops["responses_cancel"]
    assert not ops["responses_sync"] and not ops["responses_steer"] and not ops["responses_stream"]
    assert ops["previous_response_id"] and ops["idempotency_key"] and not ops["chat_completions"]
    assert caps.payload["features"]["cards"] == ["link_cards_v1"] and caps.payload["features"]["approvals"]
    assert caps.payload["voice"] == {"supported": False, "state": "unsupported", "reason": "voice_unsupported",
                                     "profiles": []}

    # turn-02: background create, then poll to completed.
    created = _create(m, token, "Hello", "m:sess-1:cmr-001", images=[_png()])
    assert created.status_code == 200, created.payload
    response_id, conversation = created.payload["id"], created.payload["conversation"]
    assert created.payload["status"] == "in_progress" and created.payload["output"] == []
    again = _create(m, token, "Hello", "m:sess-1:cmr-001", images=[_png()])
    assert again.payload["id"] == response_id, "the same Idempotency-Key never sends twice"
    done = _until(m, token, response_id, lambda p: p["status"] not in ("queued", "in_progress"))
    assert done["status"] == "completed" and done["conversation"] == conversation
    assert done["output"] == [{"type": "message", "role": "assistant",
                               "content": [{"type": "output_text", "text": "Hi there"}]}]
    assert len(seen) == 1

    # Later turns stay in the same Vault conversation: by previous_response_id (Link echoes the
    # conversation as its context) and by the stable link_conversation.
    second = _create(m, token, "And now?", "m:sess-1:cmr-002", previous=conversation)
    assert second.payload["conversation"] == conversation
    _until(m, token, second.payload["id"], lambda p: p["status"] == "completed")
    third = _create(m, token, "Third", "m:sess-1:cmr-003")
    assert third.payload["conversation"] == conversation
    _until(m, token, third.payload["id"], lambda p: p["status"] == "completed")
    other = _create(m, token, "Elsewhere", "m:sess-2:cmr-001", conversation="sess-2")
    assert other.payload["conversation"] != conversation
    _until(m, token, other.payload["id"], lambda p: p["status"] == "completed")
    assert _create(m, token, "x", "m:sess-1:cmr-004", previous="missing-turn").status_code == 404

    # Drafts reuse live preparation (l1-03): valid, bad id, bad revision, then clear.
    drafted = _fd(m, "POST", "/link/v1/drafts", token,
                  {"conversation": conversation, "draft_id": "d_01", "revision": 2, "text": "typing..."})
    assert drafted.status_code == 200 and drafted.payload["draft_id"] == "d_01" and drafted.payload["revision"] == 2
    assert _fd(m, "POST", "/link/v1/drafts", token,
               {"conversation": conversation, "draft_id": "../escape", "revision": 1, "text": "x"}).status_code == 400
    assert _fd(m, "POST", "/link/v1/drafts", token,
               {"conversation": conversation, "draft_id": "d_01", "revision": -1, "text": "x"}).status_code == 400
    assert _fd(m, "POST", "/link/v1/drafts/status", token,
               {"conversation": conversation, "draft_id": "d_01", "revision": 2}).status_code == 200
    assert _fd(m, "POST", "/link/v1/drafts/clear", token, {"conversation": conversation}).status_code == 200
    assert _fd(m, "POST", "/link/v1/drafts", token,
               {"conversation": "", "draft_id": "d_02", "revision": 0, "text": "x"}).payload["state"] == "off"

    # Steer is reported unsupported and never reaches the turn (ctrl-07).
    assert _fd(m, "POST", f"/link/v1/responses/{response_id}/steer", token,
               {"text": "change course", "link_conversation": "sess-1", "message_id": "s1"}).status_code == 501

    # Cancel stops a running turn (turn-03).
    release = []

    async def slow(**kwargs):
        while not release:
            sleep(0.02)
        return finish(kwargs, "Too late")

    runtime.runner = slow
    running = _create(m, token, "Long job", "m:sess-1:cmr-005")
    cancelled = _fd(m, "POST", f"/v1/responses/{running.payload['id']}/cancel", token)
    assert cancelled.status_code == 200 and cancelled.payload["status"] == "cancelled"
    release.append(True)
    final = _until(m, token, running.payload["id"], lambda p: p["status"] not in ("queued", "in_progress"))
    assert final["status"] == "cancelled" and final["output"] == []
    assert _fd(m, "POST", "/v1/responses/missing/cancel", token).status_code == 404

    # Unknown routes and bad input get safe codes.
    assert _fd(m, "GET", "/v1/responses/missing", token).status_code == 404
    assert _fd(m, "POST", "/v1/responses", token, {"model": "agent", "input": [
        {"role": "user", "content": [{"type": "input_image", "image_url": "https://attacker.example/x.png"}]}]},
        {"Idempotency-Key": "m:sess-1:cmr-006"}).status_code == 400, "a remote image URL is never fetched"


def test_front_door_approval_request_and_decision(mounted):
    m = mounted
    m.app._conversation_runtime.memories._embedder_factory = None
    grant(m)
    _mount(m)
    seen = {}
    _turn_with_gated_send(m, seen)
    token, _ = _pair(m)
    created = _create(m, token, "Send Sam the lunch email", "m:sess-1:appr-1")
    response_id = created.payload["id"]
    waiting = _until(m, token, response_id, lambda p: any(i["type"] == "link_approval_request" for i in p["output"]))
    assert waiting["status"] == "in_progress"
    request = next(i for i in waiting["output"] if i["type"] == "link_approval_request")
    assert request["title"] == "Send an email" and request["allow_once"] is True
    assert request["detail"] == ["To: sam@example.com", "Subject: Lunch"]
    assert isinstance(waiting["link_activity"]["updated_at"], int)

    # Only this turn's pending approval can be decided; chat text never approves.
    assert _fd(m, "POST", f"/link/v1/responses/{response_id}/approval", token,
               {"approval_id": "other", "decision": "allow_once", "link_conversation": "sess-1"}).status_code == 400
    assert _fd(m, "POST", f"/link/v1/responses/{response_id}/approval", token,
               {"approval_id": request["approval_id"], "decision": "maybe"}).status_code == 400
    decided = _fd(m, "POST", f"/link/v1/responses/{response_id}/approval", token,
                  {"approval_id": request["approval_id"], "decision": "allow_once", "link_conversation": "sess-1"})
    assert decided.status_code == 200, decided.payload
    done = _until(m, token, response_id, lambda p: p["status"] not in ("queued", "in_progress"))
    assert done["status"] == "completed"
    assert done["output"][-1]["content"][0]["text"] == "Done."
    assert "denied" not in json.dumps(seen["tool"])


def test_legacy_companion_chat_still_answers(mounted):
    m = mounted
    m.app._conversation_runtime.memories._embedder_factory = None

    async def runner(**kwargs):
        return finish(kwargs, "Legacy ok")

    m.app._conversation_runtime.runner = runner
    token, _ = _pair(m)
    session = _chat(m, "POST", "sessions", token, {}).payload["id"]
    sent = _chat(m, "POST", f"sessions/{session}/messages", token, {"text": "hi", "client_message_id": "legacy-1"})
    assert sent.status_code == 202
