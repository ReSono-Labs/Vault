from __future__ import annotations

from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import secrets
import threading
from typing import Any, Mapping, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from app.core.security.tokens import hash_token, token_equals
from app.vault_runtime.agent_network.repository import A2ARepository
from app.vault_runtime.agent_network.tools import agent2agent_option_on
from app.vault_runtime.extensions.runtime_port_forwarder import runtime_port_publish_enabled
from app.vault_runtime.background_agent.contracts import (
    AutonomyProfile,
    BackgroundRunRequest,
    BackgroundRunState,
    ExecutionRecipe,
)
from app.vault_runtime.background_agent.output_contract import background_output_schema


DEFAULT_A2A_LISTEN_PORT = 8768
ADVERTISED_A2A_HOST = "127.0.0.1"
DOCKER_PUBLISH_HOST = "0.0.0.0"
LOOPBACK_HOSTS = {"127.0.0.1", "::1"}
SEND_METHODS = frozenset({"SendMessage", "message/send"})
GET_METHODS = frozenset({"GetTask", "tasks/get"})
CARD_PATH = "/.well-known/agent-card.json"


class SessionFactory(Protocol):
    def create_session(
        self, *, user_id: str, token_hash: str, csrf_token_hash: str,
        workspace_id: str, issued_at: datetime, expires_at: datetime,
    ) -> str: ...


class BackgroundSubmitter(Protocol):
    def submit(self, *, user_id: str, workspace_id: str, local_session_id: str, request: BackgroundRunRequest) -> Any: ...


class BackgroundRuns(Protocol):
    def get(self, *, user_id: str, workspace_id: str, local_session_id: str, run_id: str) -> Any: ...


class A2AInboundApp:
    def __init__(
        self, *, repository: A2ARepository, builtin_plugins: Any,
        background: BackgroundSubmitter, runs: BackgroundRuns,
        sessions: SessionFactory, public_origin: str = "http://127.0.0.1:8768",
    ) -> None:
        self.repository = repository
        self._plugins = builtin_plugins
        self._background = background
        self._runs = runs
        self._sessions = sessions
        self.public_origin = public_origin.rstrip("/")
        self.voice_coordinator = None

    def set_public_origin(self, origin: str) -> None:
        self.public_origin = origin.rstrip("/")

    def listen_info(self, *, user_id: str, workspace_id: str) -> dict[str, str]:
        token, _session_id = self._ensure_inbound(user_id=user_id, workspace_id=workspace_id)
        card_url = f"{self.public_origin}{CARD_PATH}"
        return {"cardUrl": card_url, "rpcUrl": f"{self.public_origin}/", "token": token}

    def handle(self, *, method: str, path: str, headers: Mapping[str, str], body: bytes) -> tuple[int, dict[str, str], bytes]:
        path = urlsplit(path).path or "/"
        if method == "GET" and path == CARD_PATH:
            return _http(200, self._card())
        token = _bearer(headers)
        if not token:
            return _http(401, {"error": "unauthorized", "message": "A2A bearer token is required."}, authenticate=True)
        scope = self.repository.resolve_inbound(token)
        if scope is None:
            return _http(401, {"error": "unauthorized", "message": "A2A bearer token is invalid."}, authenticate=True)
        user_id, workspace_id, session_id = scope
        if not agent2agent_option_on(self._plugins, user_id, workspace_id):
            return _http(401, {"error": "unauthorized", "message": "Agent2Agent is turned off."}, authenticate=True)
        if method == "POST" and path in {"/", "", "/a2a/v1"}:
            return self._rpc(user_id=user_id, workspace_id=workspace_id, session_id=session_id, body=body)
        return _http(404, {"error": "not_found", "message": "Not found."})

    def _ensure_inbound(self, *, user_id: str, workspace_id: str) -> tuple[str, str]:
        current = self.repository.inbound_row(user_id=user_id, workspace_id=workspace_id)
        if current is not None:
            session_id, token = current
            outbound = self.repository.outbound_tokens(user_id=user_id, workspace_id=workspace_id)
            if not any(token_equals(item, token) for item in outbound):
                return token, session_id
        token = secrets.token_urlsafe(32)
        outbound = self.repository.outbound_tokens(user_id=user_id, workspace_id=workspace_id)
        while any(token_equals(item, token) for item in outbound):
            token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        session_id = self._sessions.create_session(
            user_id=user_id, workspace_id=workspace_id,
            token_hash=hash_token(secrets.token_urlsafe(32)),
            csrf_token_hash=hash_token(secrets.token_urlsafe(32)),
            issued_at=now, expires_at=now + timedelta(days=3650),
        )
        self.repository.save_inbound(user_id=user_id, workspace_id=workspace_id, session_id=session_id, token=token)
        return token, session_id

    def _card(self) -> dict[str, object]:
        return {
            "name": "Vault Background Agent",
            "description": "Inbound A2A tasks run as this Vault's Background text agent.",
            "supportedInterfaces": [{
                "protocolBinding": "JSONRPC", "protocolVersion": "1.0",
                "url": f"{self.public_origin}/",
            }],
            "securitySchemes": {
                "bearer": {"type": "http", "scheme": "bearer"},
            },
            "security": [{"bearer": []}],
            "capabilities": {"streaming": False, "pushNotifications": False},
        }

    def _rpc(self, *, user_id: str, workspace_id: str, session_id: str, body: bytes) -> tuple[int, dict[str, str], bytes]:
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _rpc_error(None, -32700, "Parse error")
        if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
            return _rpc_error(payload.get("id") if isinstance(payload, dict) else None, -32600, "Invalid request")
        request_id = payload.get("id")
        rpc_method = str(payload.get("method") or "")
        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
        if rpc_method in SEND_METHODS:
            try:
                return _rpc_ok(request_id, self._send(user_id=user_id, workspace_id=workspace_id, session_id=session_id, params=params))
            except ValueError as exc:
                return _rpc_error(request_id, -32602, str(exc))
        if rpc_method in GET_METHODS:
            try:
                return _rpc_ok(request_id, self._get(user_id=user_id, workspace_id=workspace_id, params=params))
            except ValueError as exc:
                return _rpc_error(request_id, -32602, str(exc))
        return _rpc_error(request_id, -32601, "Method not found")

    def _send(self, *, user_id: str, workspace_id: str, session_id: str, params: Mapping[str, Any]) -> dict[str, object]:
        if self.voice_coordinator is not None:
            raise RuntimeError("Inbound A2A must not use Voice.")
        text = _message_text(params.get("message"))
        if not text or len(text) > 16000:
            raise ValueError("The inbound A2A message is invalid.")
        context_id = str((params.get("message") or {}).get("contextId") or f"ctx-{uuid4().hex}")
        run_id = str(uuid4())
        request = BackgroundRunRequest(
            run_id=run_id, objective=text, instruction_profile="inbound-a2a",
            success_criteria=("Produce a text reply for the calling A2A peer.",),
            result_schema=background_output_schema(),
            recipe=ExecutionRecipe.DIRECT, autonomy=AutonomyProfile.LIMITED,
            original_request=text, verification_method="Background Agent text result is returned through A2A GetTask.",
            completion_conditions=("A text summary is available for the peer.",),
        )
        submitted = self._background.submit(
            user_id=user_id, workspace_id=workspace_id, local_session_id=session_id, request=request,
        )
        if getattr(submitted.request, "run_id", run_id) != run_id:
            run_id = submitted.request.run_id
        task_id = str(uuid4())
        self.repository.save_inbound_task(
            task_id=task_id, user_id=user_id, workspace_id=workspace_id,
            local_session_id=session_id, run_id=run_id, context_id=context_id,
        )
        return {"task": _task_payload(task_id, context_id, "TASK_STATE_SUBMITTED", text[:500])}

    def _get(self, *, user_id: str, workspace_id: str, params: Mapping[str, Any]) -> dict[str, object]:
        task_id = str(params.get("id") or "")
        record = self.repository.inbound_task(task_id=task_id)
        if record is None or record[0] != user_id or record[1] != workspace_id:
            raise ValueError("A2A task is unavailable.")
        _uid, _ws, session_id, run_id, context_id = record
        run = self._runs.get(user_id=user_id, workspace_id=workspace_id, local_session_id=session_id, run_id=run_id)
        state, summary = _run_task_state(run)
        # A2A GetTask returns the Task itself. SendMessage wraps a newly
        # submitted task under `task`, but polling must expose status directly.
        return _task_payload(task_id, context_id, state, summary)


class A2AInboundHttpServer:
    def __init__(self, app: A2AInboundApp, *, host: str = "127.0.0.1", port: int | None = None) -> None:
        if host == DOCKER_PUBLISH_HOST:
            if not runtime_port_publish_enabled():
                raise ValueError("A2A inbound may bind all interfaces only in the Docker package.")
        elif host not in LOOPBACK_HOSTS:
            raise ValueError("A2A inbound must bind loopback.")
        self._app = app
        self._host = host
        self._port = DEFAULT_A2A_LISTEN_PORT if port is None else port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        if self._server is None:
            raise RuntimeError("A2A inbound is not started.")
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    def start(self) -> tuple[str, int]:
        if self._server is not None:
            return self.address
        httpd = ThreadingHTTPServer((self._host, self._port), _handler_for(self._app))
        httpd.daemon_threads = True
        thread = threading.Thread(target=httpd.serve_forever, name="vault-a2a-inbound", daemon=True)
        self._server, self._thread = httpd, thread
        thread.start()
        host, port = self.address
        origin = f"http://{ADVERTISED_A2A_HOST}:{port}"
        self._app.set_public_origin(origin)
        logging.getLogger(__name__).info(
            "vault A2A inbound listening on %s (bind %s:%s)", origin, host, port,
        )
        return host, port

    def stop(self) -> None:
        server, thread = self._server, self._thread
        if server is None:
            return
        self._server = None
        self._thread = None
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=5)


def listen_port_from_env() -> int:
    raw = os.environ.get("RESONO_VAULT_A2A_LISTEN_PORT", str(DEFAULT_A2A_LISTEN_PORT))
    port = int(raw)
    if port in {8765, 8766, 8767}:
        raise ValueError("A2A inbound must not share the dashboard or media ports.")
    return port


def listen_host_from_env() -> str:
    if runtime_port_publish_enabled():
        return DOCKER_PUBLISH_HOST
    return ADVERTISED_A2A_HOST


def _handler_for(app: A2AInboundApp):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def _dispatch(self, method: str) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 1_048_576:
                self.send_response(413)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"payload_too_large"}')
                return
            body = self.rfile.read(length) if length else b""
            status, hdrs, payload = app.handle(method=method, path=self.path, headers={k: v for k, v in self.headers.items()}, body=body)
            self.send_response(status)
            self.send_header("Content-Type", hdrs.get("Content-Type", "application/json"))
            if "WWW-Authenticate" in hdrs:
                self.send_header("WWW-Authenticate", hdrs["WWW-Authenticate"])
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def _bearer(headers: Mapping[str, str]) -> str:
    raw = ""
    for key, value in headers.items():
        if key.lower() == "authorization":
            raw = value
            break
    scheme, _, remainder = raw.partition(" ")
    if scheme.lower() != "bearer" or not remainder or remainder != remainder.strip() or " " in remainder.strip():
        return ""
    return remainder.strip()


def _message_text(message: object) -> str:
    if not isinstance(message, Mapping):
        return ""
    parts = message.get("parts")
    if not isinstance(parts, list):
        return str(message.get("text") or "").strip()
    texts = [str(part.get("text")).strip() for part in parts if isinstance(part, Mapping) and str(part.get("text") or "").strip()]
    return "\n".join(texts).strip()


def _task_payload(task_id: str, context_id: str, state: str, text: str) -> dict[str, object]:
    return {
        "id": task_id, "contextId": context_id,
        "status": {"state": state, "message": {"parts": [{"text": text, "mediaType": "text/plain"}]}},
        "artifacts": [{"parts": [{"text": text, "mediaType": "text/plain"}]}] if text else [],
    }


def _run_task_state(run: Any) -> tuple[str, str]:
    state = run.state if isinstance(run.state, BackgroundRunState) else BackgroundRunState(str(run.state))
    output = run.output if isinstance(run.output, dict) else {}
    summary = str(output.get("summary") or run.failure_message or "")
    if state in {BackgroundRunState.COMPLETED}:
        return "TASK_STATE_COMPLETED", summary or "Completed."
    if state in {BackgroundRunState.FAILED, BackgroundRunState.CANCELLED}:
        return "TASK_STATE_FAILED", summary or str(state)
    return "TASK_STATE_WORKING", summary or "Working."


def _http(status: int, payload: dict[str, object], *, authenticate: bool = False) -> tuple[int, dict[str, str], bytes]:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if authenticate:
        headers["WWW-Authenticate"] = "Bearer"
    return status, headers, body


def _rpc_ok(request_id: object, result: dict[str, object]) -> tuple[int, dict[str, str], bytes]:
    return _http(200, {"jsonrpc": "2.0", "id": request_id, "result": result})


def _rpc_error(request_id: object, code: int, message: str) -> tuple[int, dict[str, str], bytes]:
    return _http(200, {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})
