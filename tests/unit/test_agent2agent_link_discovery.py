from app.vault_runtime.agent_network.client import ValidatedAgentCard
from app.vault_runtime.agent_network.repository import A2AConnection
from app.vault_runtime.agent_network.service import A2AService
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.definitions import ToolInvocationContext


class Repository:
    def __init__(self) -> None:
        self.connection = A2AConnection(
            "grant-1", "user-1", "workspace-1", "Peer",
            "https://agent.example/.well-known/agent-card.json",
            "https://agent.example/", {}, True, "grant-1",
        )
        self.refreshed = None

    def get(self, **_kwargs):
        return self.connection

    def token(self, _connection):
        return "grant-token"

    def refresh_link_card(self, *, connection, rpc_url, card):
        self.refreshed = (rpc_url, card)
        self.connection = A2AConnection(
            connection.connection_id, connection.user_id, connection.workspace_id,
            connection.display_name, connection.card_url, rpc_url, card,
            connection.enabled, connection.link_grant_id,
        )
        return self.connection

    def context(self, **_kwargs):
        return None

    def save_task(self, **_kwargs):
        return None


class Client:
    def __init__(self) -> None:
        self.sent_url = None

    def discover(self, card_url, token):
        assert card_url.endswith("/.well-known/agent-card.json")
        assert token == "grant-token"
        card = {
            "name": "Peer",
            "supportedInterfaces": [{
                "protocolBinding": "JSONRPC",
                "protocolVersion": "1.0",
                "url": "https://agent.example/custom/rpc",
            }],
        }
        return ValidatedAgentCard("Peer", card_url, "https://agent.example/custom/rpc", card)

    def send(self, *, rpc_url, **_kwargs):
        self.sent_url = rpc_url
        return {
            "id": "remote-1", "contextId": "ctx-1",
            "status": {"state": "TASK_STATE_COMPLETED"},
            "artifacts": [{"parts": [{"text": "ok"}]}],
        }


def test_link_managed_peer_uses_exact_rpc_url_from_authenticated_card() -> None:
    repository = Repository()
    client = Client()
    service = A2AService(repository=repository, client=client)
    result = service.send(
        context=ToolInvocationContext(
            agent=AgentKind.VOICE, user_id="user-1", workspace_id="workspace-1",
            tool_call_id="call-1", local_session_id="local-1", voice_session_id="voice-1",
        ),
        connection_id="grant-1", message="hello",
    )
    assert client.sent_url == "https://agent.example/custom/rpc"
    assert repository.refreshed[0] == "https://agent.example/custom/rpc"
    assert result["summary"] == "ok"
