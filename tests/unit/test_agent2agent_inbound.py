from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.core.security.tokens import token_equals

from app.vault_runtime.agent_network.inbound import (
    A2AInboundApp,
    A2AInboundHttpServer,
    CARD_PATH,
    listen_host_from_env,
    listen_port_from_env,
)
from app.vault_runtime.agent_network.tools import OPTION_OFF_MESSAGE, agent2agent_option_on
from app.vault_runtime.background_agent.contracts import BackgroundRunRequest, BackgroundRunState
from app.vault_runtime.local_api.app import VaultLocalApiApp
from app.vault_runtime.system_agents.inventory import AgentKind


class Option:
    def __init__(self, on: bool) -> None:
        self.on = on

    def enabled(self, *, account_id: str, workspace_id: str, plugin_key: str) -> bool:
        return self.on and plugin_key == "agent2agent"


class MemoryRepository:
    def __init__(self) -> None:
        self.inbound = {"user-1": {"workspace-1": ("session-a2a", "inbound-secret")}}
        self.outbound = {"user-1": {"workspace-1": ("outbound-secret",)}}
        self.tasks: dict[str, tuple[str, str, str, str, str]] = {}

    def resolve_inbound(self, token: str):
        matched = None
        for user_id, workspaces in self.inbound.items():
            for workspace_id, (session_id, stored) in workspaces.items():
                if token_equals(stored, token):
                    matched = (user_id, workspace_id, session_id)
        return matched

    def inbound_token_equals(self, *, user_id: str, workspace_id: str, token: str) -> bool:
        inbound = self.inbound_row(user_id=user_id, workspace_id=workspace_id)
        return inbound is not None and token_equals(inbound[1], token)

    def outbound_tokens(self, *, user_id: str, workspace_id: str) -> tuple[str, ...]:
        return self.outbound.get(user_id, {}).get(workspace_id, ())

    def inbound_row(self, *, user_id: str, workspace_id: str):
        return self.inbound.get(user_id, {}).get(workspace_id)

    def save_inbound(self, *, user_id: str, workspace_id: str, session_id: str, token: str) -> None:
        self.inbound.setdefault(user_id, {})[workspace_id] = (session_id, token)

    def save_inbound_task(self, *, task_id: str, user_id: str, workspace_id: str,
                          local_session_id: str, run_id: str, context_id: str) -> None:
        self.tasks[task_id] = (user_id, workspace_id, local_session_id, run_id, context_id)

    def inbound_task(self, *, task_id: str):
        return self.tasks.get(task_id)


class Background:
    def __init__(self) -> None:
        self.submitted = None

    def submit(self, **kwargs):
        self.submitted = kwargs
        assert kwargs["request"].__class__ is BackgroundRunRequest
        return SimpleNamespace(request=kwargs["request"])


class Runs:
    def __init__(self, state=BackgroundRunState.QUEUED, summary="done") -> None:
        self.state = state
        self.summary = summary

    def get(self, **kwargs):
        output = {"summary": self.summary} if self.state is BackgroundRunState.COMPLETED else None
        return SimpleNamespace(state=self.state, output=output, failure_message=None)


class Sessions:
    def create_session(self, **_kwargs) -> str:
        return "session-a2a"


class Voice:
    def start(self, **_kwargs):
        raise AssertionError("inbound A2A must not start Voice")


class Health:
    def health(self) -> dict[str, object]:
        return {"schemaReady": True, "backend": "test"}


class Principal:
    user_id = "user-1"
    workspace_id = "workspace-1"


class Identity:
    def authenticate(self, session_token: str) -> Principal:
        assert session_token == "session"
        return Principal()

    def require_csrf(self, **_kwargs) -> None:
        return None


def app(**kwargs) -> A2AInboundApp:
    return A2AInboundApp(
        repository=kwargs.get("repository", MemoryRepository()),
        builtin_plugins=kwargs.get("plugins", Option(True)),
        background=kwargs.get("background", Background()),
        runs=kwargs.get("runs", Runs()),
        sessions=Sessions(),
        public_origin="http://127.0.0.1:8768",
    )


def send_body(text: str = "hello from Hermes") -> bytes:
    return json.dumps({
        "jsonrpc": "2.0", "id": "1", "method": "SendMessage",
        "params": {"message": {"messageId": "m1", "role": "ROLE_USER", "parts": [{"text": text, "mediaType": "text/plain"}]}},
    }).encode()


def test_listen_port_rejects_dashboard_ports(monkeypatch) -> None:
    monkeypatch.setenv("RESONO_VAULT_A2A_LISTEN_PORT", "8766")
    with pytest.raises(ValueError):
        listen_port_from_env()


def test_http_server_rejects_non_loopback(monkeypatch) -> None:
    monkeypatch.setenv("RESONO_VAULT_RUNTIME_PUBLISH_PORTS", "0")
    with pytest.raises(ValueError):
        A2AInboundHttpServer(app(), host="0.0.0.0", port=0)
    assert listen_host_from_env() == "127.0.0.1"


def test_docker_package_binds_all_interfaces_and_advertises_loopback(monkeypatch) -> None:
    monkeypatch.setenv("RESONO_VAULT_RUNTIME_PUBLISH_PORTS", "1")
    assert listen_host_from_env() == "0.0.0.0"
    inbound = app()
    server = A2AInboundHttpServer(inbound, host="0.0.0.0", port=0)
    host, port = server.start()
    try:
        assert host == "0.0.0.0"
        assert inbound.public_origin == f"http://127.0.0.1:{port}"
        response = httpx.get(
            f"http://127.0.0.1:{port}{CARD_PATH}",
            timeout=5,
        )
        assert response.status_code == 200
        assert response.json()["supportedInterfaces"][0]["url"] == f"http://127.0.0.1:{port}/"
    finally:
        server.stop()


def test_docker_compose_publishes_a2a_port() -> None:
    root = Path(__file__).resolve().parents[2]
    for relative in ("compose.yml", "packaging/docker-release/compose.yml"):
        text = (root / relative).read_text(encoding="utf-8")
        assert "VAULT_A2A_PORT" in text
        assert "RESONO_VAULT_A2A_LISTEN_PORT" in text
        assert "RESONO_VAULT_RUNTIME_PUBLISH_PORTS" in text
        assert "host.docker.internal:host-gateway" in text


def test_missing_bearer_is_401_even_with_cookie() -> None:
    status, _headers, body = app().handle(
        method="POST", path="/",
        headers={"Cookie": "resono_session=browser"}, body=send_body(),
    )
    assert status == 401
    assert b"bearer" in body.lower()


def test_agent_card_is_public() -> None:
    status, headers, body = app().handle(
        method="GET", path=CARD_PATH,
        headers={"Cookie": "resono_session=browser"}, body=b"",
    )
    assert status == 200
    assert headers.get("WWW-Authenticate") is None
    card = json.loads(body)
    assert card["name"] == "Vault Background Agent"
    assert card["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"


def test_outbound_token_is_not_accepted_inbound() -> None:
    status, _headers, body = app().handle(
        method="POST", path="/",
        headers={"Authorization": "Bearer outbound-secret"}, body=send_body(),
    )
    assert status == 401


def test_option_off_refuses_valid_inbound_token() -> None:
    status, _headers, _body = app(plugins=Option(False)).handle(
        method="POST", path="/",
        headers={"Authorization": "Bearer inbound-secret"}, body=send_body(),
    )
    assert status == 401


def test_basic_auth_and_malformed_bearer_are_rejected() -> None:
    inbound = app()
    status, headers, _body = inbound.handle(
        method="POST", path="/", headers={"Authorization": "Basic dXNlcjpwYXNz"}, body=send_body(),
    )
    assert status == 401
    assert headers.get("WWW-Authenticate") == "Bearer"
    status, _headers, _body = inbound.handle(
        method="POST", path="/", headers={"Authorization": "Bearer"}, body=send_body(),
    )
    assert status == 401
    status, _headers, _body = inbound.handle(
        method="POST", path="/", headers={"Authorization": "Bearer inbound-secret extra"}, body=send_body(),
    )
    assert status == 401


def test_card_advertises_bearer() -> None:
    _status, _headers, body = app().handle(
        method="GET", path=CARD_PATH,
        headers={}, body=b"",
    )
    card = json.loads(body)
    assert card["securitySchemes"]["bearer"]["scheme"] == "bearer"
    assert card["security"] == [{"bearer": []}]


def test_connect_refuses_reusing_inbound_token() -> None:
    from app.vault_runtime.agent_network.service import A2AService

    class Client:
        def discover(self, *_args, **_kwargs):
            raise AssertionError("must not discover when inbound token is reused")

    service = A2AService(repository=MemoryRepository(), client=Client())
    with pytest.raises(ValueError, match="inbound"):
        service.connect(
            user_id="user-1", workspace_id="workspace-1",
            display_name="Hermes", card_url="http://127.0.0.1:9900/.well-known/agent-card.json",
            token="inbound-secret",
        )


def test_card_is_discoverable_by_existing_client_shape() -> None:
    status, _headers, body = app().handle(
        method="GET", path=CARD_PATH,
        headers={"Authorization": "Bearer inbound-secret", "Cookie": "resono_session=browser"},
        body=b"",
    )
    assert status == 200
    card = json.loads(body)
    assert card["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"
    assert card["supportedInterfaces"][0]["protocolVersion"] == "1.0"
    assert "agent2agent_collab" not in json.dumps(card)


def test_send_message_submits_background_not_voice() -> None:
    background = Background()
    inbound = app(background=background)
    inbound.voice_coordinator = None
    status, _headers, body = inbound.handle(
        method="POST", path="/",
        headers={"Authorization": "Bearer inbound-secret"},
        body=send_body(),
    )
    assert status == 200
    payload = json.loads(body)
    assert payload["result"]["task"]["id"]
    assert background.submitted is not None
    assert background.submitted["local_session_id"] == "session-a2a"
    assert background.submitted["request"].objective == "hello from Hermes"
    assert "voice" not in background.submitted


def test_openclaw_collab_path_is_accepted() -> None:
    background = Background()
    inbound = app(background=background)
    status, _headers, body = inbound.handle(
        method="POST", path="/a2a/v1",
        headers={"Authorization": "Bearer inbound-secret"},
        body=send_body(),
    )
    assert status == 200
    assert json.loads(body)["result"]["task"]["id"]
    assert background.submitted is not None


def test_send_does_not_call_voice_coordinator() -> None:
    inbound = app()
    inbound.voice_coordinator = Voice()
    with pytest.raises(RuntimeError):
        inbound._send(user_id="user-1", workspace_id="workspace-1", session_id="session-a2a", params={
            "message": {"parts": [{"text": "hi"}]},
        })


def test_collab_rpc_is_method_not_found() -> None:
    status, _headers, body = app().handle(
        method="POST", path="/",
        headers={"Authorization": "Bearer inbound-secret"},
        body=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "a2a_collab_turn", "params": {}}).encode(),
    )
    assert status == 200
    error = json.loads(body)["error"]
    assert error["code"] == -32601


def test_get_task_maps_background_run() -> None:
    repository = MemoryRepository()
    background = Background()
    inbound = app(repository=repository, background=background, runs=Runs(BackgroundRunState.COMPLETED, "reviewed"))
    inbound.handle(method="POST", path="/", headers={"Authorization": "Bearer inbound-secret"}, body=send_body())
    task_id = next(iter(repository.tasks))
    status, _headers, body = inbound.handle(
        method="POST", path="/",
        headers={"Authorization": "Bearer inbound-secret"},
        body=json.dumps({"jsonrpc": "2.0", "id": "3", "method": "GetTask", "params": {"id": task_id}}).encode(),
    )
    task = json.loads(body)["result"]
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    assert "reviewed" in json.dumps(task)


def test_loopback_http_server_serves_card() -> None:
    inbound = app()
    server = A2AInboundHttpServer(inbound, host="127.0.0.1", port=0)
    host, port = server.start()
    try:
        assert host == "127.0.0.1"
        assert port not in {8765, 8766, 8767}
        response = httpx.get(
            f"http://127.0.0.1:{port}{CARD_PATH}",
            timeout=5,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Vault Background Agent"
        assert response.headers.get("www-authenticate") is None
        denied = httpx.post(f"http://127.0.0.1:{port}/", timeout=5, content=b"{}")
        assert denied.status_code == 401
        assert denied.headers.get("www-authenticate", "").lower().startswith("bearer")
    finally:
        server.stop()


def test_listen_api_requires_option() -> None:
    class Service:
        def listen_info(self, **_kwargs):
            raise AssertionError("listen must not run while Agent2Agent is off")
        repository = MemoryRepository()

    local = VaultLocalApiApp(
        store=Health(), token="secret", identity_service=Identity(),
        builtin_plugins=Option(False), a2a_service=Service(),
    )
    response = local.handle(
        method="GET", target="/agent2agent/listen",
        headers={"Authorization": "Bearer session", "Cookie": "resono_csrf=csrf", "X-Resono-Csrf": "csrf"},
        body=b"",
    )
    assert response.status_code == 400
    assert response.payload["error"]["message"] == "Agent2Agent is turned off."
    assert agent2agent_option_on(Option(False), "user-1", "workspace-1") is False
    assert OPTION_OFF_MESSAGE


def test_listen_api_returns_card_when_on() -> None:
    class Service:
        def listen_info(self, **_kwargs):
            return {"cardUrl": "http://127.0.0.1:8768/.well-known/agent-card.json", "rpcUrl": "http://127.0.0.1:8768/", "token": "inbound-secret"}
        repository = MemoryRepository()

    local = VaultLocalApiApp(
        store=Health(), token="secret", identity_service=Identity(),
        builtin_plugins=Option(True), a2a_service=Service(),
    )
    response = local.handle(
        method="GET", target="/agent2agent/listen",
        headers={"Authorization": "Bearer session"},
        body=b"",
    )
    assert response.status_code == 200
    assert "8768" in response.payload["cardUrl"]
    assert "inbound-secret" in response.payload["token"]
    assert AgentKind.BACKGROUND.value == "background"
