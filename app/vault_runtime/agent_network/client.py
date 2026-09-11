from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any, Mapping
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx


class A2AError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


@dataclass(frozen=True, slots=True)
class ValidatedAgentCard:
    name: str
    card_url: str
    rpc_url: str
    card: dict[str, object]


def validate_card_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise A2AError("a2a_url_invalid", "The Agent Card address is invalid.")
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
    try:
        local = local or ip_address(parsed.hostname).is_loopback
    except ValueError:
        pass
    if parsed.scheme != "https" and not local:
        raise A2AError("a2a_tls_required", "Remote Agent Cards require HTTPS.")
    return value.strip()


class A2AClient:
    def __init__(self, *, timeout: float = 120.0) -> None:
        self._timeout = timeout

    def discover(self, card_url: str, token: str = "") -> ValidatedAgentCard:
        card_url = validate_card_url(card_url)
        try:
            response = httpx.get(card_url, headers=_headers(token), timeout=15, follow_redirects=False)
            response.raise_for_status()
            card = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise A2AError("a2a_card_unavailable", "The Agent Card could not be loaded.", retryable=True) from exc
        if not isinstance(card, dict):
            raise A2AError("a2a_card_invalid", "The Agent Card is invalid.")
        origin = urlsplit(card_url)
        rpc_url = ""
        for interface in card.get("supportedInterfaces", []):
            if not isinstance(interface, Mapping) or str(interface.get("protocolBinding", "")).upper() != "JSONRPC" or str(interface.get("protocolVersion", "")) != "1.0":
                continue
            candidate = urljoin(card_url, str(interface.get("url", "")))
            parsed = urlsplit(candidate)
            if parsed.scheme == origin.scheme and parsed.hostname == origin.hostname and parsed.port == origin.port and not parsed.username and not parsed.password and not parsed.fragment:
                rpc_url = candidate
                break
        if not rpc_url:
            raise A2AError("a2a_protocol_unsupported", "The agent does not advertise A2A JSON-RPC 1.0.")
        name = str(card.get("name") or "External agent").strip()[:120]
        return ValidatedAgentCard(name or "External agent", card_url, rpc_url, card)

    def send(self, *, rpc_url: str, token: str, message: str, context_id: str,
             return_immediately: bool = True) -> dict[str, object]:
        params: dict[str, object] = {"message": {
            "messageId": uuid4().hex, "role": "ROLE_USER", "contextId": context_id,
            "parts": [{"text": message, "mediaType": "text/plain"}],
        }}
        if return_immediately:
            params["configuration"] = {"returnImmediately": True}
        return self._rpc(rpc_url, token, "SendMessage", params)

    def get_task(self, *, rpc_url: str, token: str, task_id: str) -> dict[str, object]:
        return self._rpc(rpc_url, token, "GetTask", {"id": task_id})

    def _rpc(self, url: str, token: str, method: str, params: dict[str, object]) -> dict[str, object]:
        request_id = uuid4().hex
        try:
            response = httpx.post(url, headers=_headers(token), json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}, timeout=self._timeout, follow_redirects=False)
            response.raise_for_status()
            value = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise A2AError("a2a_peer_unavailable", "The external agent is unavailable.", retryable=True) from exc
        if not isinstance(value, dict) or value.get("jsonrpc") != "2.0" or value.get("id") != request_id:
            raise A2AError("a2a_response_invalid", "The external agent returned an invalid response.")
        if isinstance(value.get("error"), Mapping):
            raise A2AError("a2a_peer_error", "The external agent rejected the task.")
        result = value.get("result")
        if isinstance(result, Mapping):
            task = result.get("task") or result.get("message") or result
            if isinstance(task, Mapping):
                return dict(task)
        raise A2AError("a2a_response_invalid", "The external agent returned an invalid task.")


def task_result(task: Mapping[str, Any]) -> tuple[str, str, str | None]:
    status = task.get("status") if isinstance(task.get("status"), Mapping) else {}
    state = str(status.get("state") or "TASK_STATE_COMPLETED").removeprefix("TASK_STATE_").lower()
    texts: list[str] = []
    for artifact in task.get("artifacts", []) if isinstance(task.get("artifacts"), list) else []:
        if isinstance(artifact, Mapping):
            texts.extend(_texts(artifact))
    if not texts and isinstance(status.get("message"), Mapping):
        texts.extend(_texts(status["message"]))
    if not texts:
        texts.extend(_texts(task))
    summary = "\n".join(texts).strip()[:16000]
    issue = None if state in {"completed", "working", "submitted"} else (summary or f"External task ended as {state}.")
    return state, summary, issue


def _texts(value: Mapping[str, Any]) -> list[str]:
    return [str(part["text"]).strip() for part in value.get("parts", []) if isinstance(part, Mapping) and isinstance(part.get("text"), str) and str(part["text"]).strip()] if isinstance(value.get("parts"), list) else []


def _headers(token: str) -> dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json", "A2A-Version": "1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers
