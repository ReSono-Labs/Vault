from app.vault_runtime.agent_network.tools import OPTION_OFF_MESSAGE, agent2agent_option_on, register_a2a_tools
from app.vault_runtime.builtin_plugins import BUILTIN_PLUGINS, BuiltinPluginRepository, HIDDEN_BUILTIN_KEYS, USER_VISIBLE_BUILTINS
from app.vault_runtime.local_api.app import VaultLocalApiApp
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext


class Option:
    def __init__(self, on: bool) -> None:
        self.on = on

    def enabled(self, *, account_id: str, workspace_id: str, plugin_key: str) -> bool:
        assert (account_id, workspace_id) == ("user-1", "workspace-1")
        return self.on and plugin_key == "agent2agent"


class FakeRepository:
    def list(self, **_kwargs):
        return ()


class FakeService:
    def __init__(self) -> None:
        self.repository = FakeRepository()
        self.sent = False

    def send(self, **_kwargs):
        self.sent = True
        return {"agentName": "Hermes", "state": "completed", "summary": "ok", "issue": None}


class Principal:
    user_id = "user-1"
    workspace_id = "workspace-1"


class Identity:
    def authenticate(self, session_token: str) -> Principal:
        assert session_token == "session"
        return Principal()

    def require_csrf(self, *, principal: Principal, csrf_token: str) -> None:
        assert csrf_token == "csrf"


class Health:
    def health(self) -> dict[str, object]:
        return {"schemaReady": True, "backend": "test"}


def context() -> ToolInvocationContext:
    return ToolInvocationContext(
        agent=AgentKind.VOICE, user_id="user-1", workspace_id="workspace-1",
        tool_call_id="call-1", local_session_id="session-1", voice_session_id="voice-1",
    )


def _headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer session",
        "Cookie": "resono_csrf=csrf",
        "X-Resono-Csrf": "csrf",
    }


def test_agent2agent_is_a_builtin_option() -> None:
    spec = next(item for item in BUILTIN_PLUGINS if item.key == "agent2agent")
    assert spec.defaults == {}
    assert spec.name == "Agent2Agent"
    spec = next(item for item in BUILTIN_PLUGINS if item.key == "agent2agent_collab")
    assert spec.key in HIDDEN_BUILTIN_KEYS
    assert spec not in USER_VISIBLE_BUILTINS
    payload = BuiltinPluginRepository._payload(spec, None)
    assert payload["builtIn"] is True
    assert payload["canDelete"] is False
    assert payload["enabled"] is False


def test_agent2agent_tools_are_hidden_and_refused_when_the_option_is_off() -> None:
    option = Option(False)
    catalog = ToolCatalog(authorizer=lambda *_: True)
    register_a2a_tools(catalog, FakeService(), builtin_plugins=option)
    names = {item.name for item in catalog.definitions_for(AgentKind.VOICE, user_id="user-1", workspace_id="workspace-1")}
    assert "agent2agent_list" not in names
    assert "agent2agent_send" not in names
    blocked = catalog.invoke("agent2agent_list", {}, context=context())
    assert blocked.is_error
    assert blocked.text == "Tool is not granted."


def test_agent2agent_send_runs_only_when_the_option_is_on() -> None:
    option = Option(True)
    service = FakeService()
    catalog = ToolCatalog(authorizer=lambda *_: True)
    register_a2a_tools(catalog, service, builtin_plugins=option)
    names = {item.name for item in catalog.definitions_for(AgentKind.VOICE, user_id="user-1", workspace_id="workspace-1")}
    assert {"agent2agent_list", "agent2agent_send"} <= names
    list_tool = next(
        item
        for item in catalog.definitions_for(
            AgentKind.VOICE, user_id="user-1", workspace_id="workspace-1"
        )
        if item.name == "agent2agent_list"
    )
    assert list_tool.input_schema["properties"] == {}
    result = catalog.invoke("agent2agent_send", {"connectionId": "c1", "message": "hello"}, context=context())
    assert not result.is_error
    assert service.sent
    option.on = False
    blocked = catalog.invoke("agent2agent_send", {"connectionId": "c1", "message": "hello"}, context=context())
    assert blocked.is_error
    assert blocked.text in {OPTION_OFF_MESSAGE, "Tool is not granted."}


def test_connect_api_refuses_when_the_option_is_off() -> None:
    class Service:
        def connect(self, **_kwargs):
            raise AssertionError("connect must not run while Agent2Agent is off")

    app = VaultLocalApiApp(
        store=Health(), token="secret", identity_service=Identity(),
        builtin_plugins=Option(False), a2a_service=Service(),
    )
    response = app.handle(
        method="POST", target="/agent2agent/connections",
        headers=_headers(),
        body=b'{"displayName":"Hermes","cardUrl":"https://example/.well-known/agent-card.json"}',
    )
    assert response.status_code == 400
    assert response.payload["error"]["message"] == "Agent2Agent is turned off."
    assert agent2agent_option_on(Option(False), "user-1", "workspace-1") is False


def test_connect_api_runs_when_the_option_is_on() -> None:
    class Item:
        connection_id = "c1"
        display_name = "Hermes"
        card_url = "https://example/.well-known/agent-card.json"
        enabled = True
        agent_card = {"name": "Hermes"}

    class Service:
        connected = False

        def connect(self, **_kwargs):
            self.connected = True
            return Item()

    service = Service()
    app = VaultLocalApiApp(
        store=Health(), token="secret", identity_service=Identity(),
        builtin_plugins=Option(True), a2a_service=service,
    )
    response = app.handle(
        method="POST", target="/agent2agent/connections",
        headers=_headers(),
        body=b'{"displayName":"Hermes","cardUrl":"https://example/.well-known/agent-card.json"}',
    )
    assert response.status_code == 201
    assert service.connected
    assert response.payload["connectionId"] == "c1"
