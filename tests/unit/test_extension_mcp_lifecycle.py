from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import urllib.request

import pytest

from app.core.security.json_schema import SchemaReferenceError
from app.vault_runtime.extensions.mcp_client import MCP_PROTOCOL_VERSION, McpClient, McpProtocolError
from app.vault_runtime.extensions.mcp_lifecycle import McpLifecycle
from app.vault_runtime.extensions.models import ExtensionKind, ExtensionState
from app.vault_runtime.extensions.repository import ExtensionRecord
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog, _schema_problem
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)

    def open(self):
        return self.responses.pop(0)["capabilities"]

    def request(self, method, *, params=None, **_):
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


class _CountingListener(ThreadingHTTPServer):
    """Counts every accepted connection, including TLS hellos sent to plain HTTP."""

    connections = 0

    def verify_request(self, request, client_address) -> bool:
        self.connections += 1
        return True


class _SchemaHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"false"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        pass


@pytest.fixture
def external_references(tmp_path, monkeypatch):
    """http, https and file $ref targets; the probe returns (listener connections, urlopen calls)."""
    server = _CountingListener(("127.0.0.1", 0), _SchemaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    opened: list[object] = []
    real_urlopen = urllib.request.urlopen

    def counting_urlopen(target, *args, **kwargs):
        opened.append(target)
        return real_urlopen(target, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", counting_urlopen)
    local_file = tmp_path / "schema.json"
    local_file.write_text("false", encoding="utf-8")
    port = server.server_address[1]
    references = (
        f"http://127.0.0.1:{port}/schema.json",
        f"https://127.0.0.1:{port}/schema.json",
        local_file.as_uri(),
    )
    try:
        yield references, lambda: (server.connections, len(opened))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _context() -> ToolInvocationContext:
    return ToolInvocationContext(
        agent=AgentKind.VOICE, user_id="user", workspace_id="workspace",
        tool_call_id="call", local_session_id="session",
    )


def test_discovery_refuses_external_schema_references_without_fetching(external_references) -> None:
    references, probe = external_references
    for reference in references:
        nested = {"type": "object", "properties": {"city": {"$ref": reference}}}
        for field, schema in (("inputSchema", {"$ref": reference}), ("inputSchema", nested), ("outputSchema", nested)):
            tool = {"name": "weather.read", "description": "Read weather", "inputSchema": {"type": "object"}}
            tool[field] = schema
            repository = Repository()
            lifecycle = McpLifecycle(
                repository=repository, catalog=ToolCatalog(authorizer=lambda _d, _c: True),
                client_factory=lambda _connection, _context: _client(),
            )
            with pytest.raises(McpProtocolError, match=r"weather\.read schema is refused: .*same schema"):
                lifecycle.discover(
                    actor_user_id="owner", workspace_id="workspace", connection=_connection(),
                    client=_client({"tools": [tool]}),
                )
            assert repository.tools == ()
    assert probe() == (0, 0)


def test_invocation_and_output_validation_never_fetch_references(external_references) -> None:
    references, probe = external_references
    for reference in references:
        external = {"type": "object", "properties": {"city": {"$ref": reference}}}
        catalog = ToolCatalog(authorizer=lambda _d, _c: True)
        # Registration refuses the schema with a clear error.
        with pytest.raises(SchemaReferenceError, match="same schema"):
            catalog.register(ToolDefinition(
                tool_id="t", name="t", description="t", input_schema=external,
                handler=lambda _context, _arguments: ToolInvocationResult("ok"),
            ))
        # A schema persisted before this check fails closed at argument validation.
        assert _schema_problem({"city": "Oslo"}, external) is not None
        # A previously persisted grant with an external input schema is not projected.
        repository = Repository()
        repository.granted = (("weather.read", "Read weather", external, None, "read"),)
        lifecycle = McpLifecycle(
            repository=repository, catalog=catalog,
            client_factory=lambda _connection, _context: _client({"content": [], "structuredContent": {"city": "Oslo"}}),
        )
        with pytest.raises(SchemaReferenceError):
            lifecycle.project_scope(user_id="user", workspace_id="workspace", agent=AgentKind.VOICE, connection=_connection())
        # A previously persisted external output schema fails the call without a request.
        repository.granted = (("weather.read", "Read weather", {"type": "object"}, external, "read"),)
        names = lifecycle.project_scope(user_id="user", workspace_id="workspace", agent=AgentKind.VOICE, connection=_connection())
        result = catalog.invoke(names[0], {}, context=_context())
        assert result.is_error and result.text == "MCP tool output schema is refused."
    assert probe() == (0, 0)


def test_in_document_schema_references_keep_working() -> None:
    city = {"type": "string", "minLength": 2}
    input_schema = {
        "type": "object", "$defs": {"city": city},
        "properties": {"city": {"$ref": "#/$defs/city"}}, "required": ["city"], "additionalProperties": False,
    }
    output_schema = {
        "type": "object", "$defs": {"reading": {"type": "number"}},
        "properties": {"temperature": {"$ref": "#/$defs/reading"}}, "required": ["temperature"],
    }
    repository = Repository()
    catalog = ToolCatalog(authorizer=lambda _d, _c: True)
    outputs = [{"temperature": 72}, {"temperature": "warm"}]
    lifecycle = McpLifecycle(
        repository=repository, catalog=catalog,
        client_factory=lambda _connection, _context: _client({
            "content": [{"type": "text", "text": "ok"}], "structuredContent": outputs.pop(0),
        }),
    )
    assert lifecycle.discover(
        actor_user_id="owner", workspace_id="workspace", connection=_connection(),
        client=_client({"tools": [{
            "name": "weather.read", "description": "Read weather",
            "inputSchema": input_schema, "outputSchema": output_schema,
        }]}),
    ) == ("weather.read",)
    repository.granted = (("weather.read", "Read weather", input_schema, output_schema, "read"),)
    names = lifecycle.project_scope(user_id="user", workspace_id="workspace", agent=AgentKind.VOICE, connection=_connection())
    bad = catalog.invoke(names[0], {"city": "X"}, context=_context())
    assert bad.is_error and "city breaks minLength" in bad.text
    good = catalog.invoke(names[0], {"city": "Oslo"}, context=_context())
    assert not good.is_error and good.structured_content == {"temperature": 72}
    mismatched = catalog.invoke(names[0], {"city": "Oslo"}, context=_context())
    assert mismatched.is_error and mismatched.text == "MCP tool output did not match its declared schema."
