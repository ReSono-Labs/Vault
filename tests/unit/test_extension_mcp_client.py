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
