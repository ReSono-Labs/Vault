"""Link Front Door v1 (``front-door.v1``) for the paired Link Companion.

Link's engine talks to agents through one contract: Open Responses ``/v1/responses`` plus a few
``/link/v1/...`` extensions (capabilities, approvals, drafts, steer). This module answers that
contract for Vault's owner chat. It is a translation layer only: every Vault behaviour (turns,
attachments, live preparation, approvals, activity, cards) is the legacy companion chat handler in
``chat.py``, called with the same principal. The legacy ``/link-companion/chat/*`` routes stay.

Contract: Link ``connector/docs/front-door.md`` and ``connector/sdk/vectors/front-door.json``;
Link's client is ``connector/chat/engine/src/backend/front_door.rs``.
"""
from __future__ import annotations

import re
from hashlib import sha256
from typing import Any
from uuid import uuid4

from app.vault_runtime.link_companion.chat import (
    ChatRejected, MAX_TEXT_CHARS, decide_background_action, handle_chat, is_background_action,
)

FRONT_DOOR_VERSION = "1"
OPEN_RESPONSES_VERSION = "2025-03"
MAX_REPLY_CARDS = 4
MAX_APPROVAL_ID = 64
_DATA_URI = re.compile(r"^data:(image/(?:jpeg|png|gif|webp));base64,([A-Za-z0-9+/=\s]+)$")
_STATUS = {"queued": "queued", "running": "in_progress", "completed": "completed", "failed": "failed"}
_STORE_STATUS = {"submitted": "queued", "running": "in_progress", "completed": "completed",
                 "failed": "failed", "interrupted": "failed"}


class FrontDoorError(Exception):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status, self.code = status, code


def capabilities(*, images: bool) -> dict[str, Any]:
    """What Vault's owner chat supports over the Front Door (support only, never authorization).

    Vault turns always run in the background and are polled; Vault does not stream partial text
    and its turns are not steerable, so those operations are reported as unsupported. Voice keeps
    using the direct WebRTC companion routes, so the Front Door voice tunnel is unsupported."""
    return {
        "front_door_version": FRONT_DOOR_VERSION,
        "open_responses_version": OPEN_RESPONSES_VERSION,
        "level": "L1",
        "operations": {
            "responses_create": True, "responses_sync": False, "responses_background": True,
            "responses_poll": True, "responses_cancel": True, "responses_steer": False,
            "responses_stream": False, "chat_completions": False,
            "previous_response_id": True, "idempotency_key": True,
        },
        "features": {
            "images_in": images, "files_out": False, "cards": ["link_cards_v1"],
            "approvals": True, "drafts": True, "activity": True, "a2a_sender": False,
        },
        "voice": {"supported": False, "state": "unsupported", "reason": "voice_unsupported", "profiles": []},
    }


def handle(runtime: Any, principal: Any, *, method: str, path: str, payload: dict[str, Any],
           idempotency_key: str | None) -> tuple[int, dict[str, Any]]:
    """Route one authenticated Front Door request. Returns (status, body)."""
    if path == "/v1/responses" and method == "POST":
        return 200, _create(runtime, principal, payload, idempotency_key)
    if path.startswith("/v1/responses/"):
        rest = path.removeprefix("/v1/responses/").strip("/").split("/")
        if len(rest) == 1 and method == "GET":
            return 200, _response(runtime, principal, rest[0])
        if rest[1:] == ["cancel"] and method == "POST":
            return 200, _cancel(runtime, principal, rest[0])
    if path.startswith("/link/v1/responses/") and method == "POST":
        rest = path.removeprefix("/link/v1/responses/").strip("/").split("/")
        if rest[1:] == ["approval"]:
            return 200, _approval(runtime, principal, rest[0], payload)
        if rest[1:] == ["steer"]:
            raise FrontDoorError(501, "unsupported")
    if path in ("/link/v1/drafts", "/link/v1/drafts/status", "/link/v1/drafts/clear") and method == "POST":
        return 200, _draft(runtime, principal, path, payload)
    raise FrontDoorError(404, "not_found")


def _legacy(runtime: Any, principal: Any, *, method: str, parts: list[str],
            payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    result = handle_chat(runtime, principal, method=method, parts=parts, query="", payload=payload or {},
                         respond=lambda status, value: (status, value))
    if result is None:
        raise FrontDoorError(404, "not_found")
    return result


def _create(runtime: Any, principal: Any, payload: dict[str, Any], idempotency_key: str | None) -> dict[str, Any]:
    if set(payload) - {"model", "input", "previous_response_id", "background", "store", "stream", "metadata", "link"}:
        raise ChatRejected("unexpected fields")
    if payload.get("stream") is True:
        raise FrontDoorError(400, "stream_unsupported")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    text, images = _input(payload.get("input"))
    conversation_id = _conversation(runtime, principal, payload.get("previous_response_id"),
                                    metadata.get("link_conversation"))
    key = idempotency_key or metadata.get("link_message_id") or str(uuid4())
    if not isinstance(key, str) or not 1 <= len(key) <= 256:
        raise ChatRejected("invalid idempotency key")
    message = {"text": text, "client_message_id": "fd-" + sha256(key.encode()).hexdigest()[:40]}
    if images:
        message["images"] = images
    _, body = _legacy(runtime, principal, method="POST", parts=["sessions", conversation_id, "messages"], payload=message)
    return {"id": body["run_id"], "object": "response", "status": "in_progress",
            "conversation": conversation_id, "output": []}


def _input(value: Any) -> tuple[str, list[dict[str, str]]]:
    """Open Responses user input to (text, images); only the last user message is a new turn."""
    if isinstance(value, str):
        return value, []
    if not isinstance(value, list) or not value:
        raise ChatRejected("invalid input")
    users = [item for item in value if isinstance(item, dict) and item.get("role") == "user"]
    if not users:
        raise ChatRejected("invalid input")
    content = users[-1].get("content")
    if isinstance(content, str):
        return content, []
    if not isinstance(content, list):
        raise ChatRejected("invalid input")
    texts, images = [], []
    for part in content:
        kind = part.get("type") if isinstance(part, dict) else None
        if kind == "input_text" and isinstance(part.get("text"), str):
            texts.append(part["text"])
        elif kind == "input_image" and isinstance(part.get("image_url"), str):
            match = _DATA_URI.match(part["image_url"])
            if match is None:   # never fetch a URL
                raise ChatRejected("invalid image")
            images.append({"media_type": match.group(1), "data": re.sub(r"\s", "", match.group(2))})
        else:
            raise ChatRejected("invalid input")
    text = "\n".join(texts)
    if len(text) > MAX_TEXT_CHARS:
        raise ChatRejected("invalid text")
    return text, images


def _conversation(runtime: Any, principal: Any, previous: Any, link_conversation: Any) -> str:
    """The Vault conversation for this Link conversation: the previous response's (or the
    conversation id Link echoes back as context), else one stable conversation per Link session."""
    store = runtime.store
    if isinstance(previous, str) and previous.strip():
        previous = previous.strip()
        try:
            return store.load(principal, previous).conversation_id
        except Exception:
            pass
        try:
            return store.turn_conversation(principal, previous)
        except Exception:
            raise FrontDoorError(404, "not_found") from None
    if isinstance(link_conversation, str) and 1 <= len(link_conversation) <= 256:
        key = "link-front-door:" + sha256(link_conversation.encode()).hexdigest()[:40]
    else:
        key = f"link-front-door:{uuid4()}"
    return store.create(principal, key).conversation_id


def _response(runtime: Any, principal: Any, turn_id: str) -> dict[str, Any]:
    _, body = _legacy(runtime, principal, method="GET", parts=["runs", turn_id])
    conversation_id = body.get("session_id")
    state = body.get("state")
    status = _STATUS.get(state, "failed")
    if state == "failed":
        current = runtime.store.status(principal, conversation_id, turn_id)
        if current.get("cancelRequested"):
            status = "cancelled"
    result: dict[str, Any] = {"id": turn_id, "object": "response", "status": status,
                              "conversation": conversation_id, "output": []}
    if status == "completed":
        result["output"] = _output(body)
    elif status in ("queued", "in_progress"):
        if isinstance(body.get("activity"), dict):
            result["link_activity"] = body["activity"]
        approval = body.get("approval")
        if isinstance(approval, dict) and isinstance(approval.get("id"), str) and len(approval["id"]) <= MAX_APPROVAL_ID:
            result["output"].append({
                "type": "link_approval_request", "approval_id": approval["id"],
                "title": str(approval.get("title") or "")[:200],
                "detail": [str(line) for line in approval.get("detail") or []][:12],
                "allow_once": True,
            })
    elif status == "failed":
        result["error"] = {"code": body.get("error") or "failed"}
    return result


def _output(body: dict[str, Any]) -> list[dict[str, Any]]:
    messages = body.get("messages") or [{"cards": body.get("cards") or [], "text": body.get("text") or ""}]
    cards: list[dict[str, Any]] = []
    texts: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        for entry in message.get("cards") or []:
            card = entry.get("card") if isinstance(entry, dict) else None
            mapped = link_card(card) if len(cards) < MAX_REPLY_CARDS else None
            if mapped is not None:
                cards.append(mapped)
            elif isinstance(card, dict) and _clip(card.get("fallbackText"), 600):
                texts.append(_clip(card.get("fallbackText"), 600))
        if isinstance(message.get("text"), str) and message["text"].strip():
            texts.append(message["text"])
    output: list[dict[str, Any]] = []
    if cards:
        output.append({"type": "link_cards", "cards": cards})
    text = "\n\n".join(texts)
    if text:
        output.append({"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]})
    return output


def _cancel(runtime: Any, principal: Any, turn_id: str) -> dict[str, Any]:
    store = runtime.store
    try:
        conversation_id = store.turn_conversation(principal, turn_id)
    except Exception:
        raise FrontDoorError(404, "not_found") from None
    current = runtime.stop(principal, conversation_id, turn_id)
    status = "cancelled" if current.get("cancelRequested") else _STORE_STATUS.get(current.get("state"), "failed")
    return {"id": turn_id, "object": "response", "status": status, "conversation": conversation_id}


def _approval(runtime: Any, principal: Any, turn_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Link's decision for a ``link_approval_request``: the owner answered Link's own approval
    sheet (Link-controlled allow_once/deny). Decided through Vault's existing approval paths."""
    if set(payload) - {"approval_id", "decision", "link_conversation"}:
        raise ChatRejected("unexpected fields")
    approval_id, decision = payload.get("approval_id"), payload.get("decision")
    if (not isinstance(approval_id, str) or not 1 <= len(approval_id) <= MAX_APPROVAL_ID
            or decision not in ("allow_once", "deny")):
        raise ChatRejected("invalid approval answer")
    _, pending = _legacy(runtime, principal, method="GET", parts=["runs", turn_id])
    request = pending.get("permission_request") if isinstance(pending.get("permission_request"), dict) else None
    approval = pending.get("approval") if isinstance(pending.get("approval"), dict) else None
    if approval is None or approval.get("id") != approval_id:
        raise ChatRejected("invalid approval answer")   # not this turn's pending approval
    if is_background_action(runtime, principal, approval_id):
        if request is not None and request.get("action_id") == approval_id:
            _, result = _legacy(runtime, principal, method="POST", parts=["runs", turn_id, "permission"], payload={
                "action_id": approval_id, "action_hash": request["action_hash"], "choice": decision,
                "decision_id": f"link-fd:{turn_id}:{approval_id}"[:128]})
            return {"approval_id": approval_id, "state": result.get("state") or result.get("result")}
        state = decide_background_action(runtime, principal, action_id=approval_id, choice=decision,
                                         decision_id=f"link-fd:{turn_id}:{approval_id}"[:128])
        return {"approval_id": approval_id, "state": state}
    _, result = _legacy(runtime, principal, method="POST", parts=["runs", turn_id, "approval"],
                        payload={"id": approval_id, "choice": decision})
    return {"approval_id": approval_id, "state": result.get("result")}


def _draft(runtime: Any, principal: Any, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    conversation = payload.get("conversation")
    draft_id, revision = payload.get("draft_id"), payload.get("revision")
    if path != "/link/v1/drafts/clear":
        if (not isinstance(draft_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", draft_id)
                or type(revision) is not int or not 0 <= revision <= 2**31 - 1):
            raise ChatRejected("invalid draft")
    if not isinstance(conversation, str) or not conversation.strip():
        # No Vault conversation yet (first message not sent): nothing to prepare against.
        return {"draft_id": draft_id, "revision": revision, "state": "off", "memories": [], "tools": []}
    try:
        conversation_id = _conversation(runtime, principal, conversation, None)
    except FrontDoorError:
        return {"draft_id": draft_id, "revision": revision, "state": "off", "memories": [], "tools": []}
    if path == "/link/v1/drafts/clear":
        _, body = _legacy(runtime, principal, method="POST", parts=["sessions", conversation_id, "draft", "clear"])
        return {"state": body.get("state", "cleared")}
    if path == "/link/v1/drafts/status":
        _, body = _legacy(runtime, principal, method="POST", parts=["sessions", conversation_id, "draft", "status"],
                          payload={"draft_id": draft_id, "revision": revision})
    else:
        text = payload.get("text", "")
        if not isinstance(text, str) or len(text) > MAX_TEXT_CHARS:
            raise ChatRejected("invalid draft")
        _, body = _legacy(runtime, principal, method="POST", parts=["sessions", conversation_id, "draft"],
                          payload={"draft_id": draft_id, "revision": revision, "text": text})
    state = body.get("state")
    return {"draft_id": draft_id, "revision": body.get("revision", revision),
            "state": "accepted" if state in (None, "searching", "accepted") else state,
            "memories": body.get("memories") or [], "tools": body.get("tools") or []}


# --- GenUI cards to Link Cards v1 -------------------------------------------------------------
# Ported from Link's legacy engine (companion_http.rs link_card_from_companion), so Link no longer
# translates Vault cards itself. Cards that do not map are shown as their fallback text.

_TITLES = {"timeline": "Timeline", "options": "Options", "checklist": "Checklist", "metrics": "Summary",
           "summary": "Summary", "headlines": "Headlines", "places": "Places", "weather": "Weather",
           "steps": "Steps", "cards": "Overview"}


def _clip(value: Any, limit: int) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return ""
    text = " ".join("".join(c if c == " " or c.isprintable() and not c.isspace() else " " for c in str(value)).split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "\u2026"


def _join(*values: Any) -> str:
    return " \u00b7 ".join(piece for piece in (_clip(v, 120) for v in values) if piece)


def link_card(card: Any) -> dict[str, Any] | None:
    if not isinstance(card, dict):
        return None
    layout = card.get("layout")
    items = [item for item in card.get("items") or [] if isinstance(item, dict)][:8] \
        if isinstance(card.get("items"), list) else []
    fallback = _clip(card.get("fallbackText"), 1000)
    if not fallback or (not items and layout != "summary") or layout not in _TITLES:
        return None
    out: dict[str, Any] = {"version": 1, "kind": "list", "title": _clip(card.get("title"), 80) or _TITLES[layout],
                           "fallback_text": fallback}
    fields: list[tuple[Any, str]] = []
    if layout == "checklist":
        fields = [("Done" if item.get("done") is True else "To do", _clip(item.get("text"), 120)) for item in items]
    elif layout in ("metrics", "weather"):
        if layout == "weather" or len(items) == 1:
            out["kind"] = "status"
        fields = [(item.get("label"), _join(item.get("value"), item.get("detail"))) for item in items]
    elif layout == "timeline":
        fields = [(item.get("time"), _join(item.get("title"), item.get("detail"))) for item in items]
    elif layout == "places":
        fields = [(item.get("title"), _join(item.get("detail"), item.get("rating"), item.get("distance"),
                                            item.get("status"))) for item in items]
    elif layout == "cards":
        fields = [(item.get("title"), _join(item.get("label"), item.get("detail"))) for item in items]
    elif layout == "headlines":
        fields = [(item.get("source") if item.get("source") is not None else "Headline",
                   _join(item.get("title"), item.get("time"))) for item in items]
        links = [{"kind": "open_url", "url": item["url"]} for item in items
                 if isinstance(item.get("url"), str) and item["url"].startswith("https://") and len(item["url"]) <= 2048][:3]
        if links:
            out["actions"] = links
    else:   # steps, options, summary
        key = "text" if layout == "summary" else "title"
        fields = [(str(index + 1), _join(item.get(key), item.get("detail"))) for index, item in enumerate(items)]
        if layout == "summary" and card.get("body") is not None:
            subtitle = _clip(card.get("body"), 120)
            if subtitle:
                out["subtitle"] = subtitle
    rows = [{"label": _clip(label, 60), "value": value} for label, value in fields
            if _clip(label, 60) and value]
    if rows:
        out["fields"] = rows
    if not rows and "subtitle" not in out:
        return None
    return out


def error_body(code: str) -> dict[str, Any]:
    return {"error": {"code": code}}

