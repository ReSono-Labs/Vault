from app.vault_runtime.extensions.mcp_client import MCP_PROTOCOL_VERSION, McpClient
from app.vault_runtime.extensions.mcp_lifecycle import McpLifecycle
from app.vault_runtime.extensions.models import ExtensionKind, ExtensionState
from app.vault_runtime.extensions.repository import ExtensionRecord
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)

    def request(self, method, *, params=None):
        return self.responses.pop(0)


def _client(*responses):
    return McpClient(Transport([
        {"protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {"tools": {}}},
        *responses,
    ]))


class Repository:
    def __init__(self):
        self.tools = ()
        self.granted = ()

    def replace_mcp_tools(self, *, tools, **_):
        self.tools = tools

    def granted_mcp_tools(self, **_):
        return self.granted


def _connection():
    return ExtensionRecord(
        "connection-id", ExtensionKind.MCP, "demo", "demo", None,
        "MCP connection", "hash", ExtensionState.ENABLED, "owner", "workspace",
        None, {"endpoint": "https://example.test/mcp"},
    )


def test_discovery_persists_but_does_not_project_until_exact_grant() -> None:
    repository = Repository()
    catalog = ToolCatalog(authorizer=lambda _definition, _context: True)
    lifecycle = McpLifecycle(repository=repository, catalog=catalog, client_factory=lambda _connection, _context: _client())
    names = lifecycle.discover(
        actor_user_id="owner", workspace_id="workspace", connection=_connection(),
        client=_client({"tools": [{
            "name": "weather.read", "description": "Read weather",
            "inputSchema": {"type": "object", "additionalProperties": False},
        }]}),
    )
    assert names == ("weather.read",) and len(repository.tools) == 1
    assert lifecycle.project_scope(
        user_id="user", workspace_id="workspace", agent=AgentKind.VOICE,
        connection=_connection(),
    ) == ()
    assert catalog.definitions_for(AgentKind.VOICE, user_id="user", workspace_id="workspace") == ()


def test_projection_is_scope_private_and_invocation_rechecks_revocation() -> None:
    repository = Repository()
    repository.granted = ((
        "weather.read", "Read weather", {"type": "object", "additionalProperties": False},
        {"type": "object", "properties": {"temperature": {"type": "number"}}, "required": ["temperature"]}, "read",
    ),)
    catalog = ToolCatalog(authorizer=lambda _definition, _context: True)
    lifecycle = McpLifecycle(
        repository=repository, catalog=catalog,
        client_factory=lambda _connection, _context: _client({
            "content": [{"type": "text", "text": "72"}],
            "structuredContent": {"temperature": 72}, "isError": False,
        }),
    )
    names = lifecycle.project_scope(
        user_id="user", workspace_id="workspace", agent=AgentKind.VOICE,
        connection=_connection(),
    )
    assert len(names) == 1
    assert catalog.definitions_for(AgentKind.VOICE, user_id="other", workspace_id="workspace") == ()
    context = ToolInvocationContext(
        agent=AgentKind.VOICE, user_id="user", workspace_id="workspace",
        tool_call_id="call", local_session_id="session",
    )
    result = catalog.invoke(names[0], {}, context=context)
    assert not result.is_error and result.structured_content == {"temperature": 72}
    repository.granted = ()
    revoked = catalog.invoke(names[0], {}, context=context)
    assert revoked.is_error and "revoked" in revoked.text
    lifecycle.revoke_scope(user_id="user", workspace_id="workspace", agent=AgentKind.VOICE, extension_id="connection-id")
    assert catalog.definitions_for(AgentKind.VOICE, user_id="user", workspace_id="workspace") == ()
