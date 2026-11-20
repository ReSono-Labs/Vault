from pathlib import Path

from app.vault_runtime.agent_network.collab.store import TurnStore
from app.vault_runtime.agent_network.collab.coordinator import TurnCoordinator
from app.vault_runtime.agent_network.collab.tools import (
    UNKNOWN_PEER_MESSAGE,
    register_collab_tools,
)
from app.vault_runtime.agent_network.tools import OPTION_OFF_MESSAGE, register_a2a_tools
from app.vault_runtime.builtin_plugins import BUILTIN_PLUGINS, HIDDEN_BUILTIN_KEYS, USER_VISIBLE_BUILTINS
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext


class Option:
    def __init__(self, *, a2a: bool, collab: bool) -> None:
        self.a2a = a2a
        self.collab = collab

    def enabled(self, *, account_id: str, workspace_id: str, plugin_key: str) -> bool:
        assert (account_id, workspace_id) == ("user-1", "workspace-1")
        if plugin_key == "agent2agent":
            return self.a2a
        if plugin_key == "agent2agent_collab":
            return self.collab
        return False


class Connection:
    def __init__(self) -> None:
        self.connection_id = "conn-hermes"
        self.display_name = "Hermes"
        self.rpc_url = "http://127.0.0.1:18789/"
        self.enabled = True


class FakeRepository:
    def list(self, **_kwargs):
        return (Connection(),)

    def token(self, connection):
        assert connection.connection_id == "conn-hermes"
        return "outbound-token"


class FakeService:
    def __init__(self) -> None:
        self.repository = FakeRepository()
        self.sent = False

    def send(self, **_kwargs):
        self.sent = True
        return {"agentName": "Hermes", "state": "completed", "summary": "ok", "issue": None}


def context() -> ToolInvocationContext:
    return ToolInvocationContext(
        agent=AgentKind.VOICE, user_id="user-1", workspace_id="workspace-1",
        tool_call_id="call-1", local_session_id="session-1", voice_session_id="voice-1",
    )


def _catalog(option: Option, tmp_path: Path, monkeypatch) -> tuple[ToolCatalog, FakeService]:
    monkeypatch.setattr(
        "app.vault_runtime.agent_network.collab.coordinator.send_message",
        lambda url, token, message, context_id=None: {
            "id": "task-1",
            "contextId": "ctx-1",
            "status": {"state": "completed"},
            "artifacts": [{"parts": [{"type": "text", "text": f"heard:{message}"}]}],
        },
    )
    service = FakeService()
    catalog = ToolCatalog(authorizer=lambda *_: True)
    register_a2a_tools(catalog, service, builtin_plugins=option)
    register_collab_tools(
        catalog, service, builtin_plugins=option,
        coordinator=TurnCoordinator(store=TurnStore(tmp_path / "turns.sqlite3")),
    )
    return catalog, service


def test_collab_follows_agent2agent_and_is_not_user_facing() -> None:
    spec = next(item for item in BUILTIN_PLUGINS if item.key == "agent2agent_collab")
    assert spec.key in HIDDEN_BUILTIN_KEYS
    assert all(item.key != "agent2agent_collab" for item in USER_VISIBLE_BUILTINS)
    assert spec.defaults == {}


def test_collab_tools_follow_agent2agent_only(tmp_path, monkeypatch) -> None:
    catalog, _service = _catalog(Option(a2a=True, collab=False), tmp_path, monkeypatch)
    names = {item.name for item in catalog.definitions_for(AgentKind.VOICE, user_id="user-1", workspace_id="workspace-1")}
    assert "agent2agent_send" in names
    assert "a2a_collab_turn" in names

    catalog, _service = _catalog(Option(a2a=False, collab=True), tmp_path, monkeypatch)
    names = {item.name for item in catalog.definitions_for(AgentKind.VOICE, user_id="user-1", workspace_id="workspace-1")}
    assert "agent2agent_send" not in names
    assert "a2a_collab_turn" not in names
    blocked = catalog.invoke("a2a_collab_turn", {"peer": "Hermes", "message": "hi"}, context=context())
    assert blocked.is_error
    assert blocked.text in {OPTION_OFF_MESSAGE, "Tool is not granted."}


def test_collab_turn_waits_and_list_records(tmp_path, monkeypatch) -> None:
    catalog, service = _catalog(Option(a2a=True, collab=True), tmp_path, monkeypatch)
    names = {item.name for item in catalog.definitions_for(AgentKind.BACKGROUND, user_id="user-1", workspace_id="workspace-1")}
    assert {"a2a_collab_turn", "a2a_collab_list", "agent2agent_send"} <= names
    result = catalog.invoke("a2a_collab_turn", {"peer": "Hermes", "message": "hello"}, context=context())
    assert not result.is_error
    assert "heard:hello" in result.text
    assert result.structured_content["status"] == "completed"
    listed = catalog.invoke("a2a_collab_list", {}, context=context())
    assert not listed.is_error
    assert listed.structured_content["turns"][0]["request_text"] == "hello"
    assert not service.sent


def test_collab_unknown_peer_is_error(tmp_path, monkeypatch) -> None:
    catalog, _service = _catalog(Option(a2a=True, collab=True), tmp_path, monkeypatch)
    result = catalog.invoke("a2a_collab_turn", {"peer": "missing", "message": "hello"}, context=context())
    assert result.is_error
    assert result.text == UNKNOWN_PEER_MESSAGE
