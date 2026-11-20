"""MCP 2025-11-25 client adapter over Streamable HTTP (``initialize`` handshake, sessions).

Kept separate from the current-protocol adapter. A session the server assigns
(``Mcp-Session-Id``) is reused for the same endpoint and credentials within this process,
and a fresh handshake is made when the server answers 404 for it. HTTP+SSE (2024-11-05)
is not supported.
"""
from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from threading import Lock
from typing import Any

from app.vault_runtime.extensions import mcp_http
from app.vault_runtime.extensions.mcp_http import McpProtocolError

PROTOCOL_VERSION = "2025-11-25"
_SESSIONS: dict[str, tuple[str, dict[str, Any]]] = {}   # key -> (session id, capabilities)
_SESSIONS_LOCK = Lock()


class LegacyHttpTransport:
    era = "legacy"

    def __init__(self, endpoint: str, *, headers: dict[str, str], session_key_headers: dict[str, str],
                 timeout_seconds: float, client_info: dict[str, str],
                 post: Callable[..., mcp_http.HttpAnswer] = mcp_http.post) -> None:
        self._endpoint, self._headers, self._timeout = endpoint, headers, timeout_seconds
        self._client_info, self._post, self._next_id = client_info, post, 0
        material = endpoint + "\n" + "\n".join(f"{k.lower()}:{v}" for k, v in sorted(session_key_headers.items()))
        self._key = sha256(material.encode()).hexdigest()
        self._session: str | None = None

    def open(self) -> dict[str, Any]:
        with _SESSIONS_LOCK:
            cached = _SESSIONS.get(self._key)
        if cached is not None:
            self._session = cached[0]
            return dict(cached[1])
        return self._handshake()

    def _handshake(self) -> dict[str, Any]:
        result, answer = self._call("initialize", {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": self._client_info,
        }, session=None)
        if result.get("protocolVersion") != PROTOCOL_VERSION:
            raise McpProtocolError("MCP server did not negotiate the required protocol revision")
        capabilities = result.get("capabilities")
        if not isinstance(capabilities, dict):
            raise McpProtocolError("MCP initialize result is invalid")
        self._session = answer.headers.get("mcp-session-id") or None
        self._notify("notifications/initialized")
        if self._session:
            with _SESSIONS_LOCK:
                _SESSIONS[self._key] = (self._session, dict(capabilities))
        return capabilities

    def request(self, method: str, *, params: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        try:
            result, _answer = self._call(method, params, session=self._session)
        except McpProtocolError as exc:
            # 404 on a session means it expired before the request ran: new handshake, once.
            if exc.status != 404 or self._session is None or isinstance(exc, mcp_http.McpTransportError):
                raise
            with _SESSIONS_LOCK:
                _SESSIONS.pop(self._key, None)
            self._handshake()
            result, _answer = self._call(method, params, session=self._session)
        return result

    def _call(self, method: str, params: dict[str, Any] | None, *, session: str | None):
        self._next_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            payload["params"] = params
        answer = self._post(self._endpoint, headers=self._request_headers(session, method), payload=payload,
                            request_id=self._next_id, timeout_seconds=self._timeout)
        if method == "initialize" and answer.status in (404, 405) and answer.message is None:
            raise McpProtocolError("MCP server does not speak Streamable HTTP (HTTP+SSE is not supported)",
                                   status=answer.status)
        return mcp_http.result_of(answer), answer

    def _notify(self, method: str) -> None:
        answer = self._post(self._endpoint, headers=self._request_headers(self._session, method),
                            payload={"jsonrpc": "2.0", "method": method}, request_id=None,
                            timeout_seconds=self._timeout)
        if not 200 <= answer.status < 300:
            raise McpProtocolError(f"MCP server refused {method}", status=answer.status)

    def _request_headers(self, session: str | None, method: str) -> dict[str, str]:
        extra = {} if method == "initialize" else {"MCP-Protocol-Version": PROTOCOL_VERSION}
        if session:
            extra["Mcp-Session-Id"] = session
        return mcp_http.merge_headers(self._headers, extra)
