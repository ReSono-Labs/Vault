#!/usr/bin/env python3
"""Runnable starter MCP server for this plugin (stdlib only): ``python3 server.py``.

Listens on 127.0.0.1:8788 (the URL in ``mcp.json``). Replace ``greeting`` with your
tool's logic, or swap this file for your preferred MCP library.

Speaks MCP 2026-07-28 (every request carries ``params._meta`` with the protocol version;
``server/discover``; no sessions) and, for older clients, 2025-11-25 (``initialize``
handshake). Vault tries the current protocol first.
"""

from __future__ import annotations

import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


MCP_PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSION = "2025-11-25"
SERVER_INFO = {"name": "starter.example", "version": "0.2.0"}
TOOLS = [{
    "name": "starter_greeting",
    "description": "Return a short greeting using the configured prefix.",
    "inputSchema": {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    },
}]


def greeting(name: str = "there", *, configured_greeting: str = "Hello") -> dict[str, object]:
    """Return the structured value the MCP `starter_greeting` tool exposes."""
    clean_name = name.strip()[:80] or "there"
    clean_greeting = configured_greeting.strip()[:40] or "Hello"
    message = f"{clean_greeting}, {clean_name}!"
    return {"content": [{"type": "text", "text": message}], "structuredContent": {"message": message}}


class Handler(BaseHTTPRequestHandler):
    server_version = "VaultMcpStarter/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _authorized(self) -> bool:
        token = os.environ.get("MCP_AUTH_TOKEN", "").strip()
        if not token:
            return True
        auth = self.headers.get("Authorization", "")
        return auth.startswith("Bearer ") and secrets.compare_digest(auth, f"Bearer {token}")

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"ok": True, "name": "starter.example"})
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/mcp":
            self._send_json(404, {"error": "not_found"})
            return
        if not self._authorized():
            self._send_json(401, {"error": "unauthorized"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1_048_576:
            self._send_json(400, {"error": "invalid_body"})
            return
        try:
            request = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {"error": "invalid_json"})
            return
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            self._send_json(400, {"error": "invalid_envelope"})
            return
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") if isinstance(request.get("params"), dict) else {}
        if "id" not in request:          # a notification (e.g. notifications/initialized)
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        version = meta.get("io.modelcontextprotocol/protocolVersion")
        if version is not None:
            self._modern(request_id, method, params, version)
        else:
            self._legacy(request_id, method, params)

    def _modern(self, request_id: Any, method: Any, params: dict[str, Any], version: Any) -> None:
        if version != MCP_PROTOCOL_VERSION:
            self._error(400, request_id, -32022, "Unsupported protocol version",
                        {"supported": [MCP_PROTOCOL_VERSION, LEGACY_PROTOCOL_VERSION]})
            return
        named = params.get("name") if method == "tools/call" else None
        if (self.headers.get("MCP-Protocol-Version") != version or self.headers.get("Mcp-Method") != method
                or (named is not None and self.headers.get("Mcp-Name") != named)):
            self._error(400, request_id, -32020, "Header does not match the request body")
            return
        if method == "server/discover":
            self._result(request_id, {
                "supportedVersions": [MCP_PROTOCOL_VERSION, LEGACY_PROTOCOL_VERSION],
                "capabilities": {"tools": {}}, "_meta": {"io.modelcontextprotocol/serverInfo": SERVER_INFO},
            })
        elif method in ("tools/list", "tools/call"):
            self._tools(request_id, method, params)
        else:
            self._error(404, request_id, -32601, "Method not found")

    def _legacy(self, request_id: Any, method: Any, params: dict[str, Any]) -> None:
        if method == "initialize":
            self._result(request_id, {
                "protocolVersion": LEGACY_PROTOCOL_VERSION,
                "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO,
            })
        elif method in ("tools/list", "tools/call"):
            self._tools(request_id, method, params)
        else:
            self._error(200, request_id, -32601, "Method not found")

    def _tools(self, request_id: Any, method: str, params: dict[str, Any]) -> None:
        if method == "tools/list":
            self._result(request_id, {"tools": TOOLS})
            return
        if params.get("name") != "starter_greeting":
            self._error(200, request_id, -32602, "Unknown tool")
            return
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        prefix = os.environ.get("VAULT_MCP_SETTING_GREETING", "Hello")
        self._result(request_id, greeting(str(arguments.get("name", "there")), configured_greeting=prefix))

    def _result(self, request_id: Any, result: dict[str, Any]) -> None:
        self._send_json(200, {"jsonrpc": "2.0", "id": request_id, "result": result})

    def _error(self, status: int, request_id: Any, code: int, message: str, data: Any = None) -> None:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        self._send_json(status, {"jsonrpc": "2.0", "id": request_id, "error": error})


def main() -> None:
    host = os.environ.get("VAULT_MCP_BIND", "127.0.0.1")
    port = int(os.environ.get("VAULT_MCP_PORT", "8788"))
    server = ThreadingHTTPServer((host, port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
