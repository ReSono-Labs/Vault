from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

TERMINAL_STATES = {
    "completed",
    "failed",
    "canceled",
    "cancelled",
    "rejected",
    "task_state_completed",
    "task_state_failed",
    "task_state_canceled",
    "task_state_cancelled",
    "task_state_rejected",
}


class A2aRpcError(RuntimeError):
    pass


def _json_rpc(url: str, method: str, params: dict[str, Any], token: str) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
        "params": params,
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise A2aRpcError(f"A2A HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise A2aRpcError(f"A2A transport error: {exc}") from exc

    if "error" in raw:
        raise A2aRpcError(json.dumps(raw["error"]))
    result = raw.get("result")
    if not isinstance(result, dict):
        raise A2aRpcError(f"unexpected A2A result: {raw!r}")
    return result


def send_message(url: str, token: str, text: str, context_id: str | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": "user",
        "parts": [{"type": "text", "text": text}],
    }
    if context_id:
        message["contextId"] = context_id
    return _json_rpc(url, "SendMessage", {"message": message}, token)


def get_task(url: str, token: str, task_id: str) -> dict[str, Any]:
    return _json_rpc(url, "GetTask", {"id": task_id}, token)


def extract_task_id(send_result: dict[str, Any]) -> str | None:
    task = send_result.get("task")
    if isinstance(task, dict):
        nested = task.get("id") or task.get("taskId")
        if isinstance(nested, str) and nested:
            return nested
    for key in ("taskId", "id"):
        value = send_result.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def task_from_send_result(send_result: dict[str, Any]) -> dict[str, Any] | None:
    task = send_result.get("task")
    if isinstance(task, dict):
        return task
    if isinstance(send_result.get("id"), str):
        return send_result
    return None


def extract_context_id(send_result: dict[str, Any]) -> str | None:
    for container in (send_result, send_result.get("task") if isinstance(send_result.get("task"), dict) else {}):
        if not isinstance(container, dict):
            continue
        value = container.get("contextId")
        if isinstance(value, str) and value:
            return value
    return None


def extract_task_state(task: dict[str, Any]) -> str:
    status = task.get("status")
    if isinstance(status, dict):
        state = status.get("state") or status.get("status")
        if isinstance(state, str):
            return state.lower()
    if isinstance(status, str):
        return status.lower()
    state = task.get("state")
    if isinstance(state, str):
        return state.lower()
    return "unknown"


def _part_text(part: dict[str, Any]) -> str | None:
    if not isinstance(part, dict):
        return None
    text = part.get("text")
    if isinstance(text, str) and text.strip():
        return text
    if part.get("kind") == "text" and isinstance(part.get("text"), str):
        return part["text"]
    if part.get("type") == "text" and isinstance(part.get("text"), str):
        return part["text"]
    return None


def _message_text(message: dict[str, Any] | None) -> str | None:
    if not isinstance(message, dict):
        return None
    parts = message.get("parts")
    if not isinstance(parts, list):
        return None
    texts = [text for part in parts if (text := _part_text(part))]
    joined = "\n".join(texts)
    return joined if joined.strip() else None


def extract_response_text(task: dict[str, Any]) -> str | None:
    artifacts = task.get("artifacts")
    if isinstance(artifacts, list):
        texts: list[str] = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            parts = artifact.get("parts")
            if not isinstance(parts, list):
                continue
            for part in parts:
                text = _part_text(part)
                if text:
                    texts.append(text)
        if texts:
            return "\n".join(texts)

    status = task.get("status")
    if isinstance(status, dict):
        status_text = _message_text(status.get("message"))
        if status_text:
            return status_text

    for key in ("response", "result", "message"):
        value = task.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, dict):
            message_text = _message_text(value)
            if message_text:
                return message_text

    history = task.get("history")
    if isinstance(history, list):
        for item in reversed(history):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").lower().replace("role_", "")
            if role != "agent":
                continue
            message_text = _message_text(item)
            if message_text:
                return message_text
    return None


def wait_for_task(
    url: str,
    token: str,
    task_id: str,
    *,
    timeout: float = 120.0,
    poll_interval: float = 1.0,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    delay = poll_interval
    last: dict[str, Any] | None = None
    while time.time() < deadline:
        last = get_task(url, token, task_id)
        state = extract_task_state(last)
        if state in TERMINAL_STATES:
            return last
        time.sleep(delay)
        delay = min(delay * 1.25, 5.0)
    raise A2aRpcError(f"timed out waiting for task {task_id}")
