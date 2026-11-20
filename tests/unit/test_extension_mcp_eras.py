"""MCP client against in-process fake servers of both protocol eras (2026-07-28 and 2025-11-25)."""
import ast
import base64
import json
from pathlib import Path

import httpx
import pytest

from app.vault_runtime.extensions import mcp_client, mcp_legacy, mcp_modern
from app.vault_runtime.extensions.mcp_client import (
    HttpMcpTransport, McpClient, McpProtocolError, McpTimeoutError,
)
from app.vault_runtime.extensions.mcp_lifecycle import _tool_result
from app.vault_runtime.extensions.mcp_modern import InvalidHeaderAnnotation, encode_header_value, header_paths

ENDPOINT = "https://mcp.test/mcp"
_REAL_CLIENT = httpx.Client
_REAL_GETADDRINFO = __import__("socket").getaddrinfo
REGION_TOOL = {
    "name": "sql.run", "description": "Run SQL",
    "inputSchema": {"type": "object", "properties": {
        "region": {"type": "string", "x-mcp-header": "Region"},
        "options": {"type": "object", "properties": {"dry": {"type": "boolean", "x-mcp-header": "Dry"}}},
        "query": {"type": "string"},
    }},
}
BAD_TOOL = {"name": "bad", "description": "Bad", "inputSchema": {"type": "object", "properties": {
    "n": {"type": "number", "x-mcp-header": "N"}}}}


@pytest.fixture(autouse=True)
def network(monkeypatch):
    mcp_client._ERAS.clear()
    mcp_legacy._SESSIONS.clear()
    monkeypatch.setattr("app.vault_runtime.extensions.mcp_http.validate_extension_host", lambda host, *, target: host)
    monkeypatch.setattr("app.vault_runtime.extensions.mcp_http.socket.getaddrinfo",
                        lambda *_a, **_k: [(2, 1, 6, "", ("203.0.113.9", 443))])
    yield
    mcp_client._ERAS.clear()
    mcp_legacy._SESSIONS.clear()


def _serve(monkeypatch, handler):
    seen = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append((request.headers, body))
        return handler(request.headers, body)

    monkeypatch.setattr(httpx, "Client", lambda **kw: _REAL_CLIENT(transport=httpx.MockTransport(wrapped), **kw))
    return seen


def _ok(body, result):
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})


def _error(status, body, code, message="no", data=None):
    error = {"code": code, "message": message, **({"data": data} if data is not None else {})}
    return httpx.Response(status, json={"jsonrpc": "2.0", "id": body.get("id"), "error": error})


def _modern_server(calls_seen=None, *, mismatch_once=False, sse=False):
    state = {"mismatch": mismatch_once}

    def handler(headers, body):
        method = body["method"]
        meta = body["params"]["_meta"]
        assert meta["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
        assert meta["io.modelcontextprotocol/clientCapabilities"] == {}
        assert meta["io.modelcontextprotocol/clientInfo"]["name"] == "resono-vault"
        assert headers["mcp-protocol-version"] == "2026-07-28" and headers["mcp-method"] == method
        if method == "server/discover":
            return _ok(body, {"supportedVersions": ["2026-07-28"], "capabilities": {"tools": {}}})
        if method == "tools/list":
            return _ok(body, {"tools": [REGION_TOOL, BAD_TOOL]})
        if method == "tools/call":
            if state["mismatch"]:
                state["mismatch"] = False
                return _error(400, body, -32020, "header mismatch")
            if sse:
                note = {"jsonrpc": "2.0", "method": "notifications/progress", "params": {"progress": 1}}
                done = {"jsonrpc": "2.0", "id": body["id"], "result": {"content": [{"type": "text", "text": "done"}]}}
                stream = f": keep-alive\n\ndata: {json.dumps(note)}\n\ndata: {json.dumps(done)}\n\n"
                return httpx.Response(200, content=stream.encode(), headers={"content-type": "text/event-stream"})
            return _ok(body, {"content": [{"type": "text", "text": "ran"}], "structuredContent": [1, 2]})
        return _error(404, body, -32601, "method not found")

    return handler


def test_modern_server_gets_metadata_headers_and_param_headers(monkeypatch) -> None:
    seen = _serve(monkeypatch, _modern_server())
    client = McpClient(HttpMcpTransport(ENDPOINT))
    client.initialize()
    assert [tool.name for tool in client.discover_tools()] == ["sql.run"]   # invalid x-mcp-header dropped
    result = client.call_tool("sql.run", {"region": "øst-1", "options": {"dry": True}, "query": "x"},
                              input_schema=REGION_TOOL["inputSchema"])
    assert result["structuredContent"] == [1, 2]                              # any JSON value
    headers = seen[-1][0]
    assert headers["mcp-name"] == "sql.run"
    assert headers["mcp-param-region"] == "=?base64?" + base64.b64encode("øst-1".encode()).decode() + "?="
    assert headers["mcp-param-dry"] == "true"
    assert headers["host"] == "mcp.test" and seen[-1][1]["params"]["arguments"]["region"] == "øst-1"
    assert "mcp-session-id" not in headers
    assert mcp_client._ERAS[ENDPOINT] == "modern"


def test_modern_sse_answer_skips_notifications(monkeypatch) -> None:
    _serve(monkeypatch, _modern_server(sse=True))
    client = McpClient(HttpMcpTransport(ENDPOINT))
    client.initialize()
    assert client.call_tool("sql.run", {"region": "a"})["content"] == [{"type": "text", "text": "done"}]


def test_header_mismatch_relists_and_retries_once(monkeypatch) -> None:
    seen = _serve(monkeypatch, _modern_server(mismatch_once=True))
    client = McpClient(HttpMcpTransport(ENDPOINT))
    client.initialize()
    client.call_tool("sql.run", {"region": "a"}, input_schema={"type": "object"})
    methods = [body["method"] for _h, body in seen]
    assert methods == ["server/discover", "tools/call", "tools/list", "tools/call"]
    assert seen[-1][0]["mcp-param-region"] == "a"


def test_input_required_and_unsupported_version_do_not_fall_back(monkeypatch) -> None:
    def handler(headers, body):
        if body["method"] == "server/discover":
            return _ok(body, {"supportedVersions": ["2026-07-28"], "capabilities": {"tools": {}}})
        return _ok(body, {"resultType": "input_required", "inputRequests": {}})

    _serve(monkeypatch, handler)
    client = McpClient(HttpMcpTransport(ENDPOINT))
    client.initialize()
    with pytest.raises(McpProtocolError, match="more input"):
        client.call_tool("sql.run", {})

    mcp_client._ERAS.clear()
    seen = _serve(monkeypatch, lambda h, b: _error(400, b, -32022, "unsupported", {"supported": ["2027-01-01"]}))
    with pytest.raises(McpProtocolError, match="unsupported"):
        McpClient(HttpMcpTransport(ENDPOINT)).initialize()
    assert [body["method"] for _h, body in seen] == ["server/discover"]


def _legacy_server(state):
    def handler(headers, body):
        method = body.get("method")
        if "_meta" in (body.get("params") or {}) and method == "server/discover":
            return _error(400, body, -32000, "Bad Request: No valid session ID provided")
        if method == "initialize":
            state["inits"] += 1
            assert body["params"]["protocolVersion"] == "2025-11-25"
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {
                "protocolVersion": "2025-11-25", "capabilities": {"tools": {}}}},
                headers={"mcp-session-id": f"s{state['inits']}"})
        assert headers["mcp-protocol-version"] == "2025-11-25"
        if headers.get("mcp-session-id") != f"s{state['inits']}" or state.pop("expire", False):
            return httpx.Response(404)
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/call":
            return _ok(body, {"content": [{"type": "text", "text": "legacy"}]})
        return _ok(body, {"tools": [REGION_TOOL]})
    return handler


def test_legacy_server_falls_back_reuses_session_and_reinitializes_on_404(monkeypatch) -> None:
    state = {"inits": 0}
    seen = _serve(monkeypatch, _legacy_server(state))
    client = McpClient(HttpMcpTransport(ENDPOINT))
    client.initialize()
    assert [tool.name for tool in client.discover_tools()] == ["sql.run"]
    assert [body.get("method") for _h, body in seen] == [
        "server/discover", "initialize", "notifications/initialized", "tools/list"]
    assert mcp_client._ERAS[ENDPOINT] == "legacy"
    # A new client in the same process skips detection and reuses the session.
    seen.clear()
    again = McpClient(HttpMcpTransport(ENDPOINT))
    again.initialize()
    assert again.call_tool("sql.run", {})["content"][0]["text"] == "legacy"
    assert [body.get("method") for _h, body in seen] == ["tools/call"]
    # The session expires: one new handshake, then the call.
    seen.clear()
    state["expire"] = True
    again.call_tool("sql.run", {})
    assert [body.get("method") for _h, body in seen] == [
        "tools/call", "initialize", "notifications/initialized", "tools/call"]


def test_timeout_is_reported_and_never_replayed(monkeypatch) -> None:
    calls = []

    def handler(headers, body):
        if body["method"] == "server/discover":
            return _ok(body, {"supportedVersions": ["2026-07-28"], "capabilities": {"tools": {}}})
        calls.append(body["method"])
        raise httpx.ReadTimeout("slow")

    _serve(monkeypatch, handler)
    client = McpClient(HttpMcpTransport(ENDPOINT))
    client.initialize()
    with pytest.raises(McpTimeoutError):
        client.call_tool("sql.run", {})
    assert calls == ["tools/call"]


def test_response_size_is_bounded_while_reading(monkeypatch) -> None:
    def handler(headers, body):
        return httpx.Response(200, content=b"{" + b" " * (5 * 1024 * 1024) + b"}",
                              headers={"content-type": "application/json"})

    _serve(monkeypatch, handler)
    with pytest.raises(McpProtocolError, match="size limit"):
        McpClient(HttpMcpTransport(ENDPOINT)).initialize()


def test_header_annotation_rules() -> None:
    assert header_paths(REGION_TOOL["inputSchema"]) == (("Region", ("region",)), ("Dry", ("options", "dry")))
    for schema in (
        BAD_TOOL["inputSchema"],
        {"type": "object", "properties": {"a": {"type": "array", "items": {"type": "string", "x-mcp-header": "A"}}}},
        {"type": "object", "properties": {"a": {"type": "string", "x-mcp-header": "A"},
                                          "b": {"type": "string", "x-mcp-header": "a"}}},
        {"type": "object", "properties": {"a": {"type": "string", "x-mcp-header": "bad name"}}},
        {"type": "object", "anyOf": [{"properties": {"a": {"type": "string", "x-mcp-header": "A"}}}]},
    ):
        with pytest.raises(InvalidHeaderAnnotation):
            header_paths(schema)
    assert header_paths({"type": "object", "properties": {"a": {"type": "string", "default": {"x-mcp-header": "x"}}}}) == ()
    assert encode_header_value("us-west1") == "us-west1"
    assert encode_header_value(" padded").startswith("=?base64?")
    assert encode_header_value("=?base64?abc?=").startswith("=?base64?") and encode_header_value("=?base64?abc?=") != "=?base64?abc?="


def test_tool_errors_and_non_text_content_are_projected() -> None:
    schema = {"type": "object", "properties": {"t": {"type": "number"}}, "required": ["t"]}
    failed = _tool_result({"isError": True, "content": [{"type": "text", "text": "city unknown"}]}, schema)
    assert failed.is_error and failed.text == "city unknown"
    mixed = _tool_result({"content": [
        {"type": "image", "data": "...", "mimeType": "image/png"},
        {"type": "resource_link", "uri": "file:///a.txt", "name": "a.txt"},
        {"type": "resource", "resource": {"uri": "file:///b", "text": "inline"}},
    ]}, None)
    assert mixed.text == "[image content: image/png]\n[resource link: a.txt <file:///a.txt>]\ninline"


def test_the_current_adapter_never_imports_the_legacy_one() -> None:
    source = Path(mcp_modern.__file__).read_text()
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("mcp_legacy" in name for name in imported)


@pytest.mark.parametrize("starter", ["mcp-kit/starters/starter.example/server.py", "plugin-kit/starters/python/server.py"])
@pytest.mark.parametrize("era", ["modern", "legacy"])
def test_real_client_against_the_starters(starter, era, monkeypatch) -> None:
    import importlib.util
    import threading
    from http.server import ThreadingHTTPServer

    monkeypatch.setattr("app.vault_runtime.extensions.mcp_http.socket.getaddrinfo", _REAL_GETADDRINFO)
    spec = importlib.util.spec_from_file_location("starter_under_test", Path(__file__).parents[2] / starter)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_address[1]}/mcp"
        if era == "legacy":
            mcp_client._ERAS[endpoint] = "legacy"
        transport = HttpMcpTransport(endpoint)
        client = McpClient(transport)
        client.initialize()
        tools = client.discover_tools()
        result = client.call_tool("starter_greeting", {"name": "Ada"}, input_schema=tools[0].input_schema)
        assert transport.era == era
        assert result["structuredContent"] == {"message": "Hello, Ada!"}
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("starter", ["mcp-kit/starters/starter.example/server.py", "plugin-kit/starters/python/server.py"])
def test_starters_refuse_foreign_origins(starter, monkeypatch) -> None:
    import importlib.util
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    monkeypatch.setattr("app.vault_runtime.extensions.mcp_http.socket.getaddrinfo", _REAL_GETADDRINFO)
    spec = importlib.util.spec_from_file_location("starter_origin", Path(__file__).parents[2] / starter)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}).encode()
    url = f"http://127.0.0.1:{server.server_address[1]}/mcp"
    try:
        with pytest.raises(HTTPError) as refused:
            urlopen(Request(url, data=body, method="POST", headers={
                "Content-Type": "application/json", "Origin": "https://attacker.example"}), timeout=3)
        assert refused.value.code == 403
        with urlopen(Request(url, data=body, method="POST", headers={
                "Content-Type": "application/json", "Origin": "http://localhost:3000"}), timeout=3) as ok:
            assert ok.status == 200
    finally:
        server.shutdown()
        server.server_close()
