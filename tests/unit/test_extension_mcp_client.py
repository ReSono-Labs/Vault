import pytest

from app.core.exceptions import BadRequestError
from app.vault_runtime.extensions.mcp_client import (
    MCP_PROTOCOL_VERSION, HttpMcpTransport, McpClient, McpProtocolError,
)


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, *, params=None):
        self.calls.append((method, params))
        return self.responses.pop(0)


def _initialized(*responses):
    return Transport([{"protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {"tools": {}}}, *responses])


def test_initialize_and_paginated_discovery_ignore_untrusted_annotations() -> None:
    transport = _initialized(
        {"tools": [{"name": "read.one", "description": "Read one", "inputSchema": {"type": "object"}, "annotations": {"readOnlyHint": True}}], "nextCursor": "page2"},
        {"tools": [{"name": "write-two", "description": "Write two", "inputSchema": {"type": "object", "additionalProperties": False}}]},
    )
    client = McpClient(transport)
    client.initialize()
    tools = client.discover_tools()
    assert [item.name for item in tools] == ["read.one", "write-two"]
    assert transport.calls[-1] == ("tools/list", {"cursor": "page2"})
    assert not hasattr(tools[0], "effect")


def test_discovery_rejects_duplicates_invalid_schema_and_cursor_cycle() -> None:
    duplicate = _initialized({"tools": [
        {"name": "same", "description": "one", "inputSchema": {"type": "object"}},
        {"name": "same", "description": "two", "inputSchema": {"type": "object"}},
    ]})
    client = McpClient(duplicate); client.initialize()
    with pytest.raises(McpProtocolError, match="unique"):
        client.discover_tools()
    invalid = _initialized({"tools": [{"name": "bad", "description": "bad", "inputSchema": {"type": "not-a-type"}}]})
    client = McpClient(invalid); client.initialize()
    with pytest.raises(McpProtocolError, match="schema"):
        client.discover_tools()
    cycle = _initialized({"tools": [], "nextCursor": "x"}, {"tools": [], "nextCursor": "x"})
    client = McpClient(cycle); client.initialize()
    with pytest.raises(McpProtocolError, match="cursor"):
        client.discover_tools()


def test_call_requires_initialization_and_validates_result_shape() -> None:
    client = McpClient(Transport([]))
    with pytest.raises(McpProtocolError, match="not initialized"):
        client.call_tool("x", {})
    transport = _initialized({"content": [{"type": "text", "text": "ok"}], "structuredContent": {"ok": True}, "isError": False})
    client = McpClient(transport); client.initialize()
    assert client.call_tool("x", {})["structuredContent"] == {"ok": True}


def test_http_transport_revalidates_dns_before_io(monkeypatch) -> None:
    def denied(_host: str, *, target: str):
        raise BadRequestError("Host must not resolve to a local or private network.", target=target)

    monkeypatch.setattr("app.vault_runtime.extensions.mcp_client.validate_extension_host", denied)
    transport = HttpMcpTransport("https://rebound.example/mcp")
    with pytest.raises(McpProtocolError, match="denied network"):
        transport.request("initialize")


def test_http_transport_merges_headers_ignoring_case_and_vault_headers_win(monkeypatch) -> None:
    import httpx

    monkeypatch.setattr("app.vault_runtime.extensions.mcp_client.validate_extension_host", lambda host, *, target: host)
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    transport = HttpMcpTransport(
        "https://example.test/mcp",
        # Stored before the header checks existed: Vault-generated names are dropped here too.
        public_headers=(("x-vault-capability", "forged"), ("content-type", "text/plain"), ("X-Tenant", "t")),
        credential_headers=(("authorization", "Bearer secret"),),
        vault_headers=(("X-Vault-Capability", "issued"),),
    )
    transport.request("initialize")
    headers = sent[0].headers
    assert headers.get_list("x-vault-capability") == ["issued"]
    assert headers.get_list("content-type") == ["application/json"]
    assert headers.get_list("accept") == ["application/json, text/event-stream"]
    assert headers.get_list("authorization") == ["Bearer secret"] and headers["x-tenant"] == "t"


def test_unsupported_transport_connections_send_no_request() -> None:
    from app.vault_runtime.extensions.mcp_lifecycle import McpLifecycle
    from app.vault_runtime.extensions.models import ExtensionKind, ExtensionState
    from app.vault_runtime.extensions.repository import ExtensionRecord
    from app.vault_runtime.system_agents.inventory import AgentKind
    from app.vault_runtime.tools.catalog import ToolCatalog

    class Repository:
        def granted_mcp_tools(self, **_):
            return (("read", "Read", {"type": "object"}, None, "read"),)

        def replace_mcp_tools(self, **_):
            raise AssertionError("nothing is discovered")

    for transport in ("sse", "stdio"):
        counting = Transport([])
        connection = ExtensionRecord(
            "c1", ExtensionKind.MCP, "legacy", "legacy", None, None, "h", ExtensionState.ENABLED,
            "owner", "w", None, {"transport": transport, "endpoint": "https://example.test/sse", "executable": False},
        )
        catalog = ToolCatalog(authorizer=lambda _d, _c: True)
        lifecycle = McpLifecycle(repository=Repository(), catalog=catalog,
                                 client_factory=lambda _c, _x: McpClient(counting))
        with pytest.raises(McpProtocolError, match="unsupported transport"):
            lifecycle.discover(actor_user_id="owner", workspace_id="w", connection=connection, client=McpClient(counting))
        assert lifecycle.project_scope(user_id="u", workspace_id="w", agent=AgentKind.VOICE, connection=connection) == ()
        assert catalog.definitions_for(AgentKind.VOICE, user_id="u", workspace_id="w") == ()
        assert counting.calls == []
