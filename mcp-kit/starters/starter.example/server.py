#!/usr/bin/env python3
"""Minimal Streamable HTTP MCP server for Vault-hosted packages (stdlib only)."""

from __future__ import annotations

import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


MCP_PROTOCOL_VERSION = "2025-11-25"


def _greeting(name: str, prefix: str) -> dict[str, Any]:
    clean_name = (name or "there").strip()[:80] or "there"
    clean_prefix = (prefix or "Hello").strip()[:40] or "Hello"
    message = f"{clean_prefix}, {clean_name}!"
    return {
        "content": [{"type": "text", "text": message}],
        "structuredContent": {"message": message},
    }


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
        if method == "initialize":
            result = {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "starter.example", "version": "0.1.0"},
            }
        elif method == "tools/list":
            result = {
                "tools": [{
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
                }],
            }
        elif method == "tools/call":
            if params.get("name") != "starter_greeting":
                self._send_json(200, {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Unknown tool"}})
                return
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            prefix = os.environ.get("VAULT_MCP_SETTING_GREETING", "Hello")
            result = _greeting(str(arguments.get("name", "there")), prefix)
        else:
            self._send_json(200, {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Unknown method"}})
            return
        self._send_json(200, {"jsonrpc": "2.0", "id": request_id, "result": result})


def main() -> None:
    host = os.environ.get("VAULT_MCP_BIND", "127.0.0.1")
    port = int(os.environ.get("VAULT_MCP_PORT", "8788"))
    server = ThreadingHTTPServer((host, port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
