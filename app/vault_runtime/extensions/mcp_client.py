"""Bounded MCP 2025-11-25 client adapted from R1 mcp/client.py and tool_adapter.py."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Protocol
from urllib.parse import urlparse

from jsonschema import Draft202012Validator

from app.core.exceptions import BadRequestError
from app.core.security.outbound import validate_extension_host


MCP_PROTOCOL_VERSION = "2025-11-25"
MAX_DISCOVERY_PAGES = 16
MAX_DISCOVERED_TOOLS = 256
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_TOOL_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class McpProtocolError(RuntimeError):
    pass


class McpTransport(Protocol):
    def request(self, method: str, *, params: dict[str, object] | None = None) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class DiscoveredMcpTool:
    name: str
    title: str | None
    description: str
    input_schema: dict[str, object]
    output_schema: dict[str, object] | None


class HttpMcpTransport:
    """One connection transport. Secret headers are supplied at use time only."""

    def __init__(
        self, endpoint: str, *, public_headers: tuple[tuple[str, str], ...] = (),
        credential_headers: tuple[tuple[str, str], ...] = (), timeout_seconds: float = 15.0,
    ) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("MCP timeout must be within 60 seconds")
        self._endpoint = endpoint
        self._headers = dict(public_headers) | dict(credential_headers)
        self._timeout = timeout_seconds
        self._next_id = 0

    def request(self, method: str, *, params: dict[str, object] | None = None) -> dict[str, object]:
        import httpx
        host = urlparse(self._endpoint).hostname
        if not host:
            raise McpProtocolError("MCP endpoint host is invalid")
        try:
            validate_extension_host(host, target="MCP host")
        except BadRequestError as exc:
            raise McpProtocolError("MCP endpoint resolved to a denied network") from exc
        self._next_id += 1
        payload: dict[str, object] = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            payload["params"] = params
        with httpx.Client(timeout=self._timeout, follow_redirects=False) as client:
            response = client.post(
                self._endpoint, headers={**self._headers, "Accept": "application/json, text/event-stream"},
                json=payload,
            )
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise McpProtocolError("MCP response exceeds the size limit")
        response.raise_for_status()
        try:
            value = response.json()
        except (ValueError, UnicodeDecodeError) as exc:
            raise McpProtocolError("MCP response is not valid JSON") from exc
        if not isinstance(value, dict) or value.get("jsonrpc") != "2.0" or value.get("id") != self._next_id:
            raise McpProtocolError("MCP response envelope is invalid")
        if "error" in value:
            raise McpProtocolError("MCP server returned a protocol error")
        result = value.get("result")
        if not isinstance(result, dict):
            raise McpProtocolError("MCP result must be an object")
        return result


class McpClient:
    def __init__(self, transport: McpTransport) -> None:
        self._transport = transport
        self._initialized = False

    def initialize(self) -> None:
        result = self._transport.request("initialize", params={
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "resono-vault", "version": "0.1.0"},
        })
        if result.get("protocolVersion") != MCP_PROTOCOL_VERSION:
            raise McpProtocolError("MCP server did not negotiate the required protocol revision")
        capabilities = result.get("capabilities")
        if not isinstance(capabilities, dict) or not isinstance(capabilities.get("tools"), dict):
            raise McpProtocolError("MCP server does not declare tools capability")
        self._initialized = True

    def discover_tools(self) -> tuple[DiscoveredMcpTool, ...]:
        self._require_initialized()
        tools: list[DiscoveredMcpTool] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        for _ in range(MAX_DISCOVERY_PAGES):
            params = {"cursor": cursor} if cursor else None
            result = self._transport.request("tools/list", params=params)
            raw_tools = result.get("tools")
            if not isinstance(raw_tools, list):
                raise McpProtocolError("MCP tools/list result is invalid")
            for raw in raw_tools:
                tools.append(_tool(raw))
                if len(tools) > MAX_DISCOVERED_TOOLS:
                    raise McpProtocolError("MCP server exposes too many tools")
            next_cursor = result.get("nextCursor")
            if next_cursor is None:
                break
            if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen_cursors:
                raise McpProtocolError("MCP discovery cursor is invalid")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        else:
            raise McpProtocolError("MCP discovery exceeds the page limit")
        names = [item.name for item in tools]
        if len(names) != len(set(names)):
            raise McpProtocolError("MCP tool names must be unique")
        return tuple(tools)

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self._require_initialized()
        if not _TOOL_NAME.fullmatch(name):
            raise McpProtocolError("MCP tool name is invalid")
        result = self._transport.request("tools/call", params={"name": name, "arguments": arguments})
        content = result.get("content")
        if not isinstance(content, list) or any(not isinstance(item, dict) for item in content):
            raise McpProtocolError("MCP tool result content is invalid")
        if "structuredContent" in result and not isinstance(result["structuredContent"], dict):
            raise McpProtocolError("MCP structuredContent must be an object")
        if "isError" in result and not isinstance(result["isError"], bool):
            raise McpProtocolError("MCP isError must be boolean")
        # Bound post-decoding data even for injected transports.
        if len(json.dumps(result, separators=(",", ":")).encode()) > MAX_RESPONSE_BYTES:
            raise McpProtocolError("MCP tool result exceeds the size limit")
        return result

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise McpProtocolError("MCP client is not initialized")


def _tool(value: object) -> DiscoveredMcpTool:
    if not isinstance(value, dict):
        raise McpProtocolError("MCP tool definition must be an object")
    name, description = value.get("name"), value.get("description")
    if not isinstance(name, str) or not _TOOL_NAME.fullmatch(name):
        raise McpProtocolError("MCP tool name is invalid")
    if not isinstance(description, str) or not description.strip() or len(description) > 8192:
        raise McpProtocolError("MCP tool description is invalid")
    title = value.get("title")
    if title is not None and (not isinstance(title, str) or not title.strip() or len(title) > 512):
        raise McpProtocolError("MCP tool title is invalid")
    input_schema = value.get("inputSchema")
    output_schema = value.get("outputSchema")
    if not isinstance(input_schema, dict) or (output_schema is not None and not isinstance(output_schema, dict)):
        raise McpProtocolError("MCP tool schemas must be objects")
    try:
        Draft202012Validator.check_schema(input_schema)
        if output_schema is not None:
            Draft202012Validator.check_schema(output_schema)
    except Exception as exc:
        raise McpProtocolError("MCP tool schema is invalid") from exc
    # Annotations are deliberately ignored: server-provided effects are untrusted.
    return DiscoveredMcpTool(name, title.strip() if isinstance(title, str) else None, description.strip(), input_schema, output_schema)
