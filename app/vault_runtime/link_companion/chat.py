"""Owner chat for the paired Link Companion (Link iPhone app → connector → companion → Vault).

A thin adapter over the normal Chat runtime: the same conversations, tools, memory, review and
authorization the owner gets in the browser. Nothing here waits for the agent; turns are polled.
Responses carry only what the user and agent visibly said, and failures only a short safe code.
"""
from __future__ import annotations

import logging
import base64
import binascii
from io import BytesIO
from time import monotonic, sleep
from typing import Any, Callable
from urllib.parse import parse_qs
from uuid import uuid4

_LOG = logging.getLogger(__name__)

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
            try:
                result = runtime.submit(principal, conversation_id, submission_key=f"link:{key}",
                    input_text=text, expected_history_version=conversation.history_version,
                    attachment_ids=attachment_ids or None)
            except Exception:
                # A refused turn must not leave its images staged: they would count against the
                # conversation's file limit and refuse every later image.
                if attachment_ids:
                    try:
                        runtime.attachments.release(principal, conversation_id, attachment_ids)
                    except Exception:
                        logging.getLogger(__name__).warning("link_companion_attachment_release_failed")
                raise
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
            history_options = {"include_background": True} if getattr(runtime, "background_coordinator", None) else {}
            page = store.display_history(principal, conversation_id, before=before,
                                         limit=max(1, min(limit, 100)), **history_options)
            messages = []
            for turn in page["turns"]:
                if turn["input"] is not None:
                    messages.append({"id": f"{turn['turnId']}:user", "role": "user", "text": turn["input"],
                                     "timestamp": _epoch(turn.get("createdAt"))})
                if turn.get("answer"):
                    cards = [{"id": u.get("cardId"), "card": u.get("card")} for u in turn.get("ui") or []
                             if isinstance(u, dict) and isinstance(u.get("card"), dict)]
                    # Ordered reply bubbles: each card then the reply text, mirroring the
                    # run response's messages[] so reloaded history renders the same way.
                    bubbles = [{"cards": [card]} for card in cards]
                    bubbles.append({"text": turn["answer"]})
                    messages.append({"id": f"{turn['turnId']}:assistant", "role": "assistant",
                                     "text": turn["answer"], "timestamp": _epoch(turn.get("updatedAt")),
                                     **({"cards": cards} if cards else {}),
                                     "bubbles": bubbles})
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
        approval, permission_request = _pending_run_action(
            runtime, principal, conversation_id=conversation_id, turn_id=turn_id,
        )
        # Keep the operation running within the bounded permission window if a pending action
        # is still waiting on this turn, even if the conversational reply text already finished.
        if permission_request is not None and state == "completed":
            state = "running"
        # An approval answered on this run wakes the coordinator, which confirms it. The phone only
        # follows the run it sent, so the run waits for that confirmation and carries it as its last
        # reply (2026-11-18): "received and done" always shows where the owner approved.
        follow_up = None
        if state == "completed" and permission_request is None:
            follow_up = _approval_follow_up(runtime, principal, conversation_id=conversation_id, turn_id=turn_id)
            if follow_up == "waiting":
                state = "running"
        body: dict[str, Any] = {"state": state, "session_id": conversation_id}
        if state == "completed":
            body["text"] = store.final_text(principal, conversation_id, turn_id) or ""
            cards = store.turn_cards(principal, conversation_id, turn_id)
            if cards:
                body["cards"] = cards
            # Ordered reply bubbles for clients that render several messages per run
            # (e.g. multiple cards). Older clients keep using text/cards above.
            messages = store.turn_messages(principal, conversation_id, turn_id)
            if isinstance(follow_up, str) and follow_up not in {"waiting", "none"}:
                confirmation = [m for m in store.turn_messages(principal, conversation_id, follow_up)
                                if (m.get("text") or "").strip() != "NO_RESPONSE"]
                if confirmation:
                    messages = list(messages or []) + confirmation
                    body["text"] = "\n\n".join(m["text"] for m in messages if m.get("text")) or body["text"]
            if messages:
                body["messages"] = messages
        elif state == "failed":
            body["error"] = "interrupted" if status["state"] == "interrupted" else "failed"
        else:
            # Link #107: tool names and states while the turn runs, for the phone's "still working".
            body["activity"] = store.turn_activity(principal, conversation_id, turn_id)
            if approval is not None:
                body["approval"] = approval
            if permission_request is not None:
                body["permission_request"] = permission_request
        return respond(200, body)

    if len(parts) == 3 and parts[0] == "runs" and parts[2] == "permission" and method == "POST":
        turn_id = identifier(parts[1])
        if set(payload) != {"action_id", "action_hash", "choice", "decision_id"} or any(
            not isinstance(payload.get(k), str) or not str(payload.get(k)).strip()
            for k in ("action_id", "action_hash", "choice", "decision_id")
        ):
            raise ChatRejected("invalid permission answer")
        choice = str(payload["choice"]).strip()
        if choice not in {"allow_once", "deny"}:
            raise ChatRejected("invalid permission answer")
        conversation_id = store.turn_conversation(principal, turn_id)
        result = _decide_run_action(
            runtime,
            principal,
            conversation_id=conversation_id,
            turn_id=turn_id,
            action_id=str(payload["action_id"]).strip(),
            action_hash=str(payload["action_hash"]).strip(),
            choice=choice,
            decision_id=str(payload["decision_id"]).strip(),
        )
        return respond(200, {"action_id": str(payload["action_id"]).strip(), "state": result, "result": result})

    if len(parts) == 3 and parts[0] == "runs" and parts[2] == "approval" and method == "POST":
        # Link's answer: {"id": approval id, "choice": "allow_once" | "deny"}, from the paired phone.
        turn_id = identifier(parts[1])
        approvals = getattr(runtime, "approvals", None)
        if approvals is None and getattr(runtime, "background_actions", None) is None:
            raise ChatRejected("approvals unavailable")
        if set(payload) - {"id", "choice", "action_hash", "decision_id"} or not isinstance(payload.get("id"), str) or not isinstance(payload.get("choice"), str):
            raise ChatRejected("invalid approval answer")
        conversation_id = store.turn_conversation(principal, turn_id)        # the turn must be this owner's
        from app.vault_runtime.background_agent.errors import (
            BackgroundRunAuthorizationError, BackgroundRunConflictError)
        try:
            if approvals is not None and "action_hash" not in payload:
                result = approvals.answer(principal, payload["id"], payload["choice"], channel="link", turn_id=turn_id)
                if result == "expired":
                    raise ChatRejected("invalid approval answer")
            else:
                result = _decide_run_action(
                    runtime,
                    principal,
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    action_id=payload["id"].strip(),
                    action_hash=str(payload.get("action_hash") or "").strip() or None,
                    choice=payload["choice"].strip(),
                    decision_id=str(payload.get("decision_id") or f"link:{payload['id'].strip()}"),
                )
        except (ValueError, BackgroundRunAuthorizationError, BackgroundRunConflictError):
            # Unknown, another turn's, or already answered differently: never counted as an allow.
            raise ChatRejected("invalid approval answer") from None
        return respond(200, {"id": payload["id"], "result": result})

    return None


APPROVAL_CONFIRMATION_WAIT_SECONDS = 90


def _approval_follow_up(runtime: Any, principal: Any, *, conversation_id: str, turn_id: str) -> str:
    """For a finished run whose approval was answered: ``waiting`` until the coordinator's
    confirmation turn finishes, then that turn's id (``none`` when nothing was answered on it, or
    the confirmation did not come within APPROVAL_CONFIRMATION_WAIT_SECONDS)."""
    actions = _actions_service(runtime)
    coordinator = getattr(runtime, "background_coordinator", None)
    jobs = getattr(coordinator, "jobs", None)
    # Wait only where Vault can wake the coordinator (durable worker up, wake attached).
    if (actions is None or jobs is None or getattr(jobs, "_wake_handler", None) is None
            or jobs.health().get("state") != "running"):
        return "none"
    with actions._repo._connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT max(a.updated_at) AS decided FROM vault_private.vault_background_actions a
               WHERE a.user_id=%s AND a.workspace_id=%s AND a.work_id IS NULL
                 AND a.kind IN ('worker_create','execution_grant','routine_create')
                 AND a.state IN ('approved','completed','denied','failed')
                 AND (a.origin_turn_id=%s OR a.origin_json->>'turn_id'=%s
                      OR a.origin_json->>'link_review_turn_id'=%s)""",
            (principal.user_id, principal.workspace_id, turn_id, turn_id, turn_id),
        )
        decided = (cursor.fetchone() or {}).get("decided")
        if decided is None:
            return "none"
        cursor.execute(
            """SELECT turn_id, state FROM vault_private.vault_conversation_turns
               WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s
                 AND submission_key LIKE 'vault-wake:%%' AND created_at >= %s - interval '2 seconds'
               ORDER BY created_at LIMIT 1""",
            (principal.user_id, principal.workspace_id, conversation_id, decided),
        )
        wake = cursor.fetchone()
        cursor.execute("SELECT now() - %s > make_interval(secs => %s) AS late", (decided, APPROVAL_CONFIRMATION_WAIT_SECONDS))
        late = cursor.fetchone()["late"]
    if wake is None:
        return "none" if late else "waiting"
    if wake["state"] in {"submitted", "running"}:
        return "none" if late else "waiting"
    return str(wake["turn_id"]) if wake["state"] == "completed" else "none"


def _actions_service(runtime: Any):
    actions = getattr(runtime, "background_actions", None)
    if actions is not None:
        return actions
    approvals = getattr(runtime, "approvals", None)
    if approvals is not None and getattr(approvals, "_actions", None) is not None:
        return approvals._actions
    return None


def _pending_run_action(
    runtime: Any, principal: Any, *, conversation_id: str, turn_id: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    from datetime import datetime, timedelta, timezone

    approvals = getattr(runtime, "approvals", None)
    actions = _actions_service(runtime)
    if approvals is None and actions is None:
        return None, None
    repo = getattr(approvals, "_repo", None) or getattr(actions, "_repo", None)
    if repo is None:
        return None, None
    source_keys = (f"chat:{conversation_id}:{turn_id}", f"conversation_turn:{conversation_id}:{turn_id}")
    now = datetime.now(timezone.utc)
    with repo._connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT a.*
               FROM vault_private.vault_background_actions a
               LEFT JOIN vault_private.vault_background_work w
                 ON w.user_id = a.user_id AND w.workspace_id = a.workspace_id AND w.work_id = a.work_id
               WHERE a.user_id = %s AND a.workspace_id = %s AND a.state = 'pending' AND a.expires_at > now()
                 AND (
                   a.origin_turn_id = %s
                   OR (a.origin_json->>'turn_id') = %s
                   OR (a.origin_json->>'link_review_turn_id') = %s
                   OR (a.kind <> 'owner_approval'
                       AND COALESCE(a.origin_conversation_id, a.origin_json->>'conversation_id') = %s)
                   OR (
                     a.work_id IS NULL
                     AND a.origin_turn_id IS NULL
                     AND a.origin_voice_session_id IS NULL
                     AND (a.origin_json->>'turn_id') IS NULL
                     AND a.kind IN ('worker_create', 'execution_grant', 'routine_create')
                   )
                   OR (
                     a.work_id IS NOT NULL
                     AND w.state IN ('waiting_approval', 'running', 'queued', 'ready', 'proposed')
                     AND (
                       w.source_key IN (%s, %s)
                       OR (w.request_json->'destination'->>'turn_id') = %s
                       OR (w.request_json->'destination'->>'conversation_id') = %s
                     )
                   )
                 )
               ORDER BY CASE WHEN a.origin_json->>'link_review_turn_id'=%s THEN 0 ELSE 1 END,
                        CASE WHEN a.origin_json->>'link_review_turn_id'=%s THEN a.created_at END,
                        a.created_at DESC, a.action_id
               LIMIT 1""",
            (principal.user_id, principal.workspace_id, turn_id, turn_id, turn_id, conversation_id,
             source_keys[0], source_keys[1], turn_id, conversation_id, turn_id, turn_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None, None
        created_at = row.get("created_at") or now
        # A proposal left open in this chat earlier gets the same window from this run's start.
        cursor.execute("""SELECT created_at FROM vault_private.vault_conversation_turns
                          WHERE user_id=%s AND workspace_id=%s AND turn_id=%s""",
                       (principal.user_id, principal.workspace_id, turn_id))
        turn_row = cursor.fetchone()
        turn_started = (turn_row["created_at"] if isinstance(turn_row, dict) else turn_row[0]) if turn_row else created_at
        created_at = max(created_at, turn_started)
        relayed = (row.get("origin_json") or {}).get("link_review_turn_id") == turn_id
        bounded_deadline = row["expires_at"] if relayed else min(row["expires_at"], created_at + timedelta(seconds=300))
        if bounded_deadline <= now:
            # The phone's permission window for this run is over. The proposal itself stays pending
            # until the owner answers it (Rakazo: a card waits for the owner), so a slow answer is
            # reviewed later from chat instead of expiring the request.
            return None, None
    expires_epoch = int(bounded_deadline.timestamp())
    detail_lines = list(
        row.get("detail_lines")
        or [line for line in str(row.get("detail") or "").splitlines() if line.strip()]
    )
    detail_text = str(row.get("detail") or "\n".join(detail_lines))
    approval = {
        "id": row["action_id"],
        "title": row["title"],
        "detail": detail_lines,
        "choices": ["allow_once", "deny"],
        "expires_at": expires_epoch,
    }
    permission_request = {
        "action_id": row["action_id"],
        "action_hash": row["action_hash"],
        "title": row["title"],
        "detail": detail_text,
        "expires_at": expires_epoch,
    }
    return approval, permission_request


def _decide_run_action(
    runtime: Any,
    principal: Any,
    *,
    conversation_id: str,
    turn_id: str,
    action_id: str,
    action_hash: str | None,
    choice: str,
    decision_id: str,
) -> str:
    from app.vault_runtime.background_agent.coordination_contracts import ApprovalDecision
    from app.vault_runtime.background_agent.errors import (
        BackgroundRunAuthorizationError,
        BackgroundRunConflictError,
    )

    actions = _actions_service(runtime)
    if actions is None:
        raise ChatRejected("approvals unavailable")
    repo = actions._repo
    source_keys = (f"chat:{conversation_id}:{turn_id}", f"conversation_turn:{conversation_id}:{turn_id}")
    with repo._connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT a.action_id, a.action_hash, a.kind, a.arguments_json, a.origin_turn_id, a.work_id
               FROM vault_private.vault_background_actions a
               LEFT JOIN vault_private.vault_background_work w
                 ON w.user_id = a.user_id AND w.workspace_id = a.workspace_id AND w.work_id = a.work_id
               WHERE a.user_id = %s AND a.workspace_id = %s AND a.action_id = %s
                 AND (
                   a.origin_turn_id = %s
                   OR (a.origin_json->>'turn_id') = %s
                   OR (a.origin_json->>'link_review_turn_id') = %s
                   OR COALESCE(a.origin_conversation_id, a.origin_json->>'conversation_id') = %s
                   OR (
                     a.work_id IS NULL
                     AND a.origin_turn_id IS NULL
                     AND a.origin_voice_session_id IS NULL
                     AND (a.origin_json->>'turn_id') IS NULL
                     AND a.kind IN ('worker_create', 'execution_grant', 'routine_create')
                   )
                   OR (
                     a.work_id IS NOT NULL
                     AND (
                       w.source_key IN (%s, %s)
                       OR (w.request_json->'destination'->>'turn_id') = %s
                       OR (w.request_json->'destination'->>'conversation_id') = %s
                     )
                   )
                 )""",
            (principal.user_id, principal.workspace_id, action_id, turn_id, turn_id, turn_id, conversation_id,
             source_keys[0], source_keys[1], turn_id, conversation_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise ChatRejected("invalid permission answer")
    return _apply_background_decision(runtime, principal, actions, row, action_id=action_id,
                                      action_hash=action_hash, choice=choice, decision_id=decision_id)


def is_background_action(runtime: Any, principal: Any, action_id: str) -> bool:
    """An owner-scope action that is not an in-turn owner approval (a coordinator proposal or an action
    of background work), so it is decided through BackgroundActions rather than OwnerApprovals."""
    actions = _actions_service(runtime)
    if actions is None:
        return False
    with actions._repo._connect() as connection, connection.cursor() as cursor:
        cursor.execute("""SELECT kind FROM vault_private.vault_background_actions
                          WHERE user_id=%s AND workspace_id=%s AND action_id=%s""",
                       (principal.user_id, principal.workspace_id, action_id))
        row = cursor.fetchone()
    return row is not None and row["kind"] != "owner_approval"


def decide_background_action(runtime: Any, principal: Any, *, action_id: str, choice: str, decision_id: str) -> str:
    """The owner's answer from the phone outside a chat run (a voice call): same effects as the run route."""
    if choice not in {"allow_once", "deny"}:
        raise ChatRejected("invalid permission answer")
    actions = _actions_service(runtime)
    if actions is None:
        raise ChatRejected("approvals unavailable")
    with actions._repo._connect() as connection, connection.cursor() as cursor:
        cursor.execute("""SELECT a.action_id, a.action_hash, a.kind, a.arguments_json, a.origin_turn_id, a.work_id
                          FROM vault_private.vault_background_actions a
                          WHERE a.user_id=%s AND a.workspace_id=%s AND a.action_id=%s AND a.kind<>'owner_approval'""",
                       (principal.user_id, principal.workspace_id, action_id))
        row = cursor.fetchone()
    if row is None:
        raise ChatRejected("invalid permission answer")
    return _apply_background_decision(runtime, principal, actions, row, action_id=action_id,
                                      action_hash=None, choice=choice, decision_id=decision_id)


def _apply_background_decision(runtime: Any, principal: Any, actions: Any, row: Any, *, action_id: str,
                               action_hash: str | None, choice: str, decision_id: str) -> str:
    from app.vault_runtime.background_agent.coordination_contracts import ApprovalDecision
    from app.vault_runtime.background_agent.errors import (
        BackgroundRunAuthorizationError,
        BackgroundRunConflictError,
    )
    repo = actions._repo
    effective_hash = action_hash if action_hash is not None else str(row["action_hash"])
    decision = ApprovalDecision(
        action_id=action_id,
        action_hash=effective_hash,
        choice=choice,
        actor_user_id=principal.user_id,
        workspace_id=principal.workspace_id,
        channel="link",
        channel_generation=principal.session_id,
        decision_id=decision_id,
    )
    try:
        actions.decide(principal, decision)
        coordinator = getattr(runtime, "background_coordinator", None)
        if choice == "allow_once":
            if row["kind"] == "worker_create":
                from app.vault_runtime.background_agent.worker_repository import WorkerRepository
                WorkerRepository(database_url=repo._database_url).create_from_approval(decision)
                role_key = (row["arguments_json"] or {}).get("role_key") if isinstance(row["arguments_json"], dict) else None
                if coordinator is not None and role_key:
                    with repo._connect() as connection, connection.cursor() as cursor:
                        cursor.execute(
                            """SELECT work_id FROM vault_private.vault_background_work
                               WHERE user_id = %s AND workspace_id = %s AND state = 'waiting_approval'
                                 AND worker_id IS NULL AND (request_json->'destination'->>'role_key') = %s""",
                            (principal.user_id, principal.workspace_id, role_key),
                        )
                        waiting_work = [r["work_id"] for r in cursor.fetchall()]
                    for waiting_id in waiting_work:
                        try:
                            coordinator.plan_dispatch(waiting_id)
                        except Exception as exc:
                            _LOG.warning("link_approval_dispatch_failed work_id=%s error=%s", waiting_id, type(exc).__name__)
            elif row["kind"] == "execution_grant":
                from app.vault_runtime.background_agent.authority import BackgroundAuthority
                BackgroundAuthority(database_url=repo._database_url).grant(
                    principal, row["arguments_json"], decision,
                )
            elif row["kind"] == "routine_create":
                from app.vault_runtime.background_agent.routines import BackgroundRoutines
                BackgroundRoutines(database_url=repo._database_url).create_from_approval(principal, decision)
        elif choice == "deny" and row["kind"] == "worker_create":
            from app.vault_runtime.background_agent.coordination_contracts import WorkState
            role_key = (row["arguments_json"] or {}).get("role_key") if isinstance(row["arguments_json"], dict) else None
            if role_key:
                with repo._connect() as connection, connection.cursor() as cursor:
                    cursor.execute(
                        """SELECT work_id FROM vault_private.vault_background_work
                           WHERE user_id = %s AND workspace_id = %s AND state = 'waiting_approval'
                             AND worker_id IS NULL AND (request_json->'destination'->>'role_key') = %s""",
                        (principal.user_id, principal.workspace_id, role_key),
                    )
                    waiting_work = [r["work_id"] for r in cursor.fetchall()]
                for waiting_id in waiting_work:
                    try:
                        repo.transition(
                            repo.resolve_work_scope(waiting_id),
                            WorkState.WAITING_APPROVAL,
                            WorkState.FAILED,
                            {"denied_action_id": action_id, "role_key": role_key},
                        )
                    except Exception as exc:
                        _LOG.warning("link_denial_fail_work_failed work_id=%s error=%s", waiting_id, type(exc).__name__)
        if coordinator is not None and row.get("work_id") and coordinator.jobs.health().get("state") == "running":
            try:
                coordinator.jobs.resume_decided()
            except Exception as exc:
                _LOG.warning("link_decision_resume_failed action_id=%s work_id=%s error=%s", action_id, row.get("work_id"), type(exc).__name__)
    except (ValueError, BackgroundRunAuthorizationError, BackgroundRunConflictError):
        raise ChatRejected("invalid permission answer") from None
    _wake_after_decision(runtime, principal, action_id)
    return "approved" if choice == "allow_once" else "denied"


def _wake_after_decision(runtime: Any, principal: Any, action_id: str) -> None:
    """The chat that asked continues on its own once the owner has decided (no second prompt)."""
    coordinator = getattr(runtime, "background_coordinator", None)
    if coordinator is None:
        return
    from app.vault_runtime.background_agent.coordination_contracts import OwnerScope
    try:
        coordinator.after_owner_decision(OwnerScope(principal.user_id, principal.workspace_id), action_id)
    except Exception:
        pass  # The decision stands; the next chat turn still sees it in its updates.
