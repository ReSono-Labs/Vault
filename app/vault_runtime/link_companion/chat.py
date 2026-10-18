"""Owner chat for the paired Link Companion (Link iPhone app → connector → companion → Vault).

A thin adapter over the normal Chat runtime: the same conversations, tools, memory, review and
authorization the owner gets in the browser. Nothing here waits for the agent; turns are polled.
Responses carry only what the user and agent visibly said, and failures only a short safe code.
"""
from __future__ import annotations

import base64
import binascii
from io import BytesIO
from time import monotonic, sleep
from typing import Any, Callable
from urllib.parse import parse_qs
from uuid import uuid4

MAX_IMAGES = 4
MAX_IMAGE_BYTES = 1_500_000
MAX_TEXT_CHARS = 16_384  # Matches the Link chat helper; 4-byte UTF-8 still fits the 64 KiB turn limit.
IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "png", "image/webp": "webp"}
IMAGE_ONLY_TEXT = "(Image attached.)"
RUN_STATES = {"submitted": "queued", "running": "running", "completed": "completed",
              "failed": "failed", "interrupted": "failed"}


class ChatRejected(ValueError):
    """Request is well-formed HTTP but not acceptable; maps to the safe code ``rejected``."""


def _images(value: Any) -> list[tuple[str, str]]:
    """Validate and normalise images to (filename, base64). GIF becomes its first frame as PNG."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_IMAGES:
        raise ChatRejected("too many images")
    out = []
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict) or set(item) - {"media_type", "data"}:
            raise ChatRejected("invalid image")
        media_type, data = item.get("media_type"), item.get("data")
        if media_type not in IMAGE_TYPES or not isinstance(data, str) or len(data) > MAX_IMAGE_BYTES * 4 // 3 + 8:
            raise ChatRejected("invalid image")
        try:
            raw = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError):
            raise ChatRejected("invalid image") from None
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise ChatRejected("invalid image")
        if media_type == "image/gif":
            raw = _gif_first_frame_png(raw)
            data = base64.b64encode(raw).decode()
        out.append((f"image-{index}.{IMAGE_TYPES[media_type]}", data))
    return out


def _gif_first_frame_png(raw: bytes) -> bytes:
    from PIL import Image
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format != "GIF" or image.width * image.height > 16_000_000:
                raise ValueError("not a bounded GIF")
            image.seek(0)
            buffer = BytesIO()
            image.convert("RGBA").save(buffer, format="PNG")
    except Exception:
        raise ChatRejected("invalid image") from None
    if buffer.tell() > 5 * 1024 * 1024:
        raise ChatRejected("invalid image")
    return buffer.getvalue()


def _epoch(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def handle_chat(runtime: Any, principal: Any, *, method: str, parts: list[str], query: str,
                payload: dict[str, Any], respond: Callable[[int, dict[str, Any]], Any]) -> Any:
    """Route ``/link-companion/chat/...`` (``parts`` excludes the ``link-companion/chat`` prefix)."""
    from app.vault_runtime.conversation.contracts import identifier

    store = runtime.store
    if parts == ["sessions"] and method == "POST":
        conversation = store.create(principal, f"link-companion:{uuid4()}")
        return respond(201, {"id": conversation.conversation_id})

    if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "messages":
        conversation_id = identifier(parts[1])
        if method == "POST":
            if set(payload) - {"text", "images", "client_message_id"}:
                raise ChatRejected("unexpected fields")
            text = payload.get("text", "")
            if not isinstance(text, str) or len(text) > MAX_TEXT_CHARS:
                raise ChatRejected("invalid text")
            images = _images(payload.get("images"))
            text = text.strip() or (IMAGE_ONLY_TEXT if images else "")
            if not text:
                raise ChatRejected("empty message")
            client_id = payload.get("client_message_id")
            if client_id is not None and (not isinstance(client_id, str) or not 1 <= len(client_id) <= 100):
                raise ChatRejected("invalid client_message_id")
            key = client_id or str(uuid4())
            conversation = store.load(principal, conversation_id)
            attachment_ids = []
            if images:
                if runtime.attachments is None:
                    raise ChatRejected("images unsupported")
                for index, (name, data) in enumerate(images):
                    staged = runtime.attachments.stage(principal, conversation_id,
                        upload_key=f"link:{key}:{index}"[:128], name=name, data=data)
                    attachment_ids.append(staged["id"])
            result = runtime.submit(principal, conversation_id, submission_key=f"link:{key}",
                input_text=text, expected_history_version=conversation.history_version,
                attachment_ids=attachment_ids or None)
            return respond(202, {"run_id": result["turnId"]})
        if method == "GET":
            values = parse_qs(query, keep_blank_values=True)
            if set(values) - {"before", "limit"} or any(len(v) != 1 for v in values.values()):
                raise ChatRejected("invalid cursor")
            try:
                before = int(values["before"][0]) if "before" in values else None
                limit = int(values.get("limit", ["50"])[0])
            except ValueError:
                raise ChatRejected("invalid cursor") from None
            page = store.display_history(principal, conversation_id, before=before, limit=max(1, min(limit, 100)))
            messages = []
            for turn in page["turns"]:
                messages.append({"id": f"{turn['turnId']}:user", "role": "user", "text": turn["input"],
                                 "timestamp": _epoch(turn.get("createdAt"))})
                if turn.get("answer"):
                    cards = [{"id": u.get("cardId"), "card": u.get("card")} for u in turn.get("ui") or []
                             if isinstance(u, dict) and isinstance(u.get("card"), dict)]
                    messages.append({"id": f"{turn['turnId']}:assistant", "role": "assistant",
                                     "text": turn["answer"], "timestamp": _epoch(turn.get("updatedAt")),
                                     **({"cards": cards} if cards else {})})
            return respond(200, {"messages": messages, "next_before": page.get("nextBefore")})

    # Live preparation while typing: the same engine browser Chat uses (live memory + live tool route).
    # The final send picks the prepared result up automatically when the text matches.
    if len(parts) in (3, 4) and parts[0] == "sessions" and parts[2] == "draft":
        conversation_id = identifier(parts[1])
        preparation = runtime.preparation
        if preparation is None:
            return respond(200, {"state": "off", "memories": [], "tools": []})
        def view(draft_id: str, revision: int) -> dict[str, Any]:
            value = preparation.status(principal, conversation_id, identifier(draft_id), revision)
            return {"revision": value.get("revision", revision), "state": value.get("state"),
                    "memories": [{"text": m.get("text")} for m in value.get("memories") or []],
                    "tools": [{"name": t.get("name"), "description": t.get("description")} for t in value.get("tools") or []]}

        def cursor(source: dict[str, Any]) -> tuple[str, int]:
            draft_id, revision = source.get("draft_id"), source.get("revision")
            if isinstance(revision, str) and revision.isdigit():
                revision = int(revision)
            if (not isinstance(draft_id, str) or not 1 <= len(draft_id) <= 100 or type(revision) is not int
                    or not 0 <= revision <= 2**31 - 1):
                raise ChatRejected("invalid draft")
            return draft_id, revision

        if method == "POST" and parts[2:] == ["draft"]:
            # One call does it all: accept the draft, wait briefly (default 1 s, max 2 s) for the
            # prepared result and return it, so a phone over Link needs no status polling.
            if set(payload) - {"draft_id", "revision", "text", "wait"}:
                raise ChatRejected("unexpected fields")
            draft_id, revision = cursor(payload)
            text, wait = payload.get("text"), payload.get("wait", 1.0)
            if not isinstance(text, str) or len(text) > MAX_TEXT_CHARS or type(wait) not in (int, float):
                raise ChatRejected("invalid draft")
            result = preparation.update(principal, conversation_id,
                                        {"utteranceId": draft_id, "revision": revision, "text": text, "composing": False})
            if isinstance(result, dict) and result.get("enabled") is False:
                return respond(200, {"revision": revision, "state": "off", "memories": [], "tools": []})
            deadline = monotonic() + max(0.0, min(float(wait), 2.0))
            current = view(draft_id, revision)
            while current["state"] in ("searching", "accepted", None) and monotonic() < deadline:
                sleep(0.1)
                current = view(draft_id, revision)
            return respond(200, current)
        if method == "POST" and parts[2:] == ["draft", "status"]:
            if set(payload) - {"draft_id", "revision"}:
                raise ChatRejected("unexpected fields")
            return respond(200, view(*cursor(payload)))
        if method == "POST" and parts[2:] == ["draft", "clear"]:
            preparation.discard(principal, conversation_id)
            return respond(200, {"state": "cleared"})
        if method == "GET" and parts[2:] == ["draft"]:
            values = parse_qs(query, keep_blank_values=True)
            return respond(200, view(*cursor({k: v[0] for k, v in values.items() if v})))
        if method == "DELETE" and parts[2:] == ["draft"]:
            preparation.discard(principal, conversation_id)
            return respond(200, {"state": "cleared"})

    if len(parts) == 2 and parts[0] == "runs" and method == "GET":
        turn_id = identifier(parts[1])
        conversation_id = store.turn_conversation(principal, turn_id)
        status = store.status(principal, conversation_id, turn_id)
        state = RUN_STATES.get(status["state"], "failed")
        body: dict[str, Any] = {"state": state, "session_id": conversation_id}
        if state == "completed":
            body["text"] = store.final_text(principal, conversation_id, turn_id) or ""
            cards = store.turn_cards(principal, conversation_id, turn_id)
            if cards:
                body["cards"] = cards
        elif state == "failed":
            body["error"] = "interrupted" if status["state"] == "interrupted" else "failed"
        return respond(200, body)

    return None
