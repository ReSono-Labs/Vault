"""An in-process protected MCP server with its own OAuth 2.1 authorization server, for tests.

One HTTP server plays both roles on 127.0.0.1 (loopback HTTP is allowed by OAuth 2.1):
- ``/mcp``: a 2026-07-28 MCP endpoint that answers 401 with a ``WWW-Authenticate`` challenge
  unless the bearer token was issued for this resource; ``whoami`` returns the token's user;
- ``/.well-known/oauth-protected-resource/mcp``: protected resource metadata (RFC 9728);
- ``/.well-known/oauth-authorization-server``: authorization server metadata (RFC 8414);
- ``/register`` (RFC 7591), ``/authorize`` (consents at once for ``login_hint``),
  ``/token`` (PKCE S256, resource and redirect checks, rotating refresh tokens), ``/revoke``.

The test drives ``/authorize`` itself in place of a browser.
"""
from __future__ import annotations

import base64
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit


class OAuthMcpServer:
    def __init__(self, *, iss_in_response: bool = True, wrong_issuer: bool = False) -> None:
        self.clients: dict[str, dict[str, Any]] = {}
        self.codes: dict[str, dict[str, Any]] = {}
        self.access: dict[str, dict[str, Any]] = {}
        self.refresh: dict[str, dict[str, Any]] = {}
        self.revoked: list[str] = []
        self.token_requests: list[dict[str, str]] = []
        self.calls: list[str] = []
        self.iss_in_response = iss_in_response
        self.wrong_issuer = wrong_issuer
        self.required_scope = "tools:read"
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    @property
    def endpoint(self) -> str:
        return self.origin + "/mcp"

    def __enter__(self) -> "OAuthMcpServer":
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()

    def authorize(self, url: str, *, user: str) -> dict[str, str]:
        """Play the browser: consent as ``user`` and return the redirect's query values."""
        import urllib.request

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args: Any, **kwargs: Any) -> None:
                return None

        opener = urllib.request.build_opener(NoRedirect)
        try:
            opener.open(url + "&" + urlencode({"login_hint": user}), timeout=5)
        except urllib.error.HTTPError as redirect:
            location = redirect.headers["Location"]
            return {key: values[0] for key, values in parse_qs(urlsplit(location).query).items()}
        raise AssertionError("authorization did not redirect")

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                return

            def _send(self, status: int, payload: Any = None, headers: dict[str, str] | None = None) -> None:
                body = b"" if payload is None else json.dumps(payload).encode()
                self.send_response(status)
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                if payload is not None:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _body(self) -> bytes:
                return self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))

            def _metadata(self) -> dict[str, Any]:
                origin = server.origin
                return {
                    "issuer": "https://evil.example" if server.wrong_issuer else origin,
                    "authorization_endpoint": origin + "/authorize",
                    "token_endpoint": origin + "/token",
                    "registration_endpoint": origin + "/register",
                    "revocation_endpoint": origin + "/revoke",
                    "response_types_supported": ["code"],
                    "code_challenge_methods_supported": ["S256"],
                    "scopes_supported": ["tools:read", "tools:write", "offline_access"],
                    "authorization_response_iss_parameter_supported": server.iss_in_response,
                }

            def do_GET(self) -> None:
                parts = urlsplit(self.path)
                if parts.path == "/.well-known/oauth-protected-resource/mcp":
                    return self._send(200, {"resource": server.endpoint, "authorization_servers": [server.origin],
                                            "scopes_supported": ["tools:read"]})
                if parts.path == "/.well-known/oauth-authorization-server":
                    return self._send(200, self._metadata())
                if parts.path == "/authorize":
                    query = {key: values[0] for key, values in parse_qs(parts.query).items()}
                    client = server.clients.get(query.get("client_id", ""))
                    if client is None or query.get("redirect_uri") not in client["redirect_uris"] \
                            or query.get("code_challenge_method") != "S256" or "resource" not in query:
                        return self._send(400, {"error": "invalid_request"})
                    code = secrets.token_urlsafe(16)
                    server.codes[code] = {**query, "user": query.get("login_hint", "anonymous")}
                    values = {"code": code, "state": query["state"]}
                    if server.iss_in_response:
                        values["iss"] = server.origin
                    return self._send(302, None, {"Location": query["redirect_uri"] + "?" + urlencode(values)})
                return self._send(404, {"error": "not_found"})

            def do_POST(self) -> None:
                parts = urlsplit(self.path)
                raw = self._body()
                if parts.path == "/register":
                    value = json.loads(raw)
                    client_id = "client-" + secrets.token_hex(4)
                    server.clients[client_id] = value
                    return self._send(201, {"client_id": client_id, **value})
                if parts.path in ("/token", "/revoke"):
                    form = {key: values[0] for key, values in parse_qs(raw.decode()).items()}
                    if parts.path == "/revoke":
                        server.revoked.append(form.get("token", ""))
                        server.access.pop(form.get("token", ""), None)
                        server.refresh.pop(form.get("token", ""), None)
                        return self._send(200, {})
                    server.token_requests.append(form)
                    return self._token(form)
                if parts.path == "/mcp":
                    return self._mcp(json.loads(raw))
                return self._send(404, {"error": "not_found"})

            def _token(self, form: dict[str, str]) -> None:
                if form.get("grant_type") == "authorization_code":
                    grant = server.codes.pop(form.get("code", ""), None)
                    if grant is None or form.get("client_id") != grant["client_id"] \
                            or form.get("redirect_uri") != grant["redirect_uri"] \
                            or form.get("resource") != grant["resource"]:
                        return self._send(400, {"error": "invalid_grant"})
                    verifier = form.get("code_verifier", "")
                    challenge = base64.urlsafe_b64encode(sha256(verifier.encode()).digest()).rstrip(b"=").decode()
                    if challenge != grant["code_challenge"]:
                        return self._send(400, {"error": "invalid_grant"})
                    user, resource, scope = grant["user"], grant["resource"], grant.get("scope", "")
                elif form.get("grant_type") == "refresh_token":
                    grant = server.refresh.pop(form.get("refresh_token", ""), None)
                    if grant is None or form.get("resource") != grant["resource"]:
                        return self._send(400, {"error": "invalid_grant"})
                    user, resource, scope = grant["user"], grant["resource"], grant["scope"]
                else:
                    return self._send(400, {"error": "unsupported_grant_type"})
                access, refresh = "at-" + secrets.token_hex(8), "rt-" + secrets.token_hex(8)
                server.access[access] = {"user": user, "resource": resource, "scope": scope}
                server.refresh[refresh] = {"user": user, "resource": resource, "scope": scope}
                self._send(200, {"access_token": access, "token_type": "Bearer", "expires_in": 3600,
                                 "refresh_token": refresh, "scope": scope})

            def _mcp(self, request: dict[str, Any]) -> None:
                challenge = (f'Bearer resource_metadata="{server.origin}/.well-known/oauth-protected-resource/mcp", '
                             f'scope="{server.required_scope}"')
                auth = self.headers.get("Authorization", "")
                grant = server.access.get(auth.removeprefix("Bearer ").strip()) if auth.startswith("Bearer ") else None
                if grant is None or grant["resource"] != server.endpoint:
                    return self._send(401, {"error": "invalid_token"}, {"WWW-Authenticate": challenge})
                if server.required_scope not in grant["scope"].split():
                    return self._send(403, {"error": "insufficient_scope"}, {
                        "WWW-Authenticate": challenge.replace("Bearer ", 'Bearer error="insufficient_scope", ')})
                method, request_id = request.get("method"), request.get("id")
                if method == "server/discover":
                    result: dict[str, Any] = {"supportedVersions": ["2026-07-28"], "capabilities": {"tools": {}}}
                elif method == "tools/list":
                    result = {"tools": [{"name": "whoami", "description": "Who is signed in.",
                                         "inputSchema": {"type": "object"}}]}
                elif method == "tools/call":
                    server.calls.append(grant["user"])
                    result = {"content": [{"type": "text", "text": f"signed in as {grant['user']}"}]}
                else:
                    return self._send(404, {"jsonrpc": "2.0", "id": request_id,
                                            "error": {"code": -32601, "message": "Method not found"}})
                self._send(200, {"jsonrpc": "2.0", "id": request_id, "result": {"resultType": "complete", **result}})

        return Handler
