"""Bounded MCP client: one interface over the current (2026-07-28) and legacy (2025-11-25) eras.

``HttpMcpTransport`` picks the era per endpoint: it tries the current protocol first and
falls back to the legacy ``initialize`` handshake only when the server's answer is not a
recognized current-protocol error (the spec's backward-compatibility rule). The choice is
remembered in this process. The two eras live in ``mcp_modern`` and ``mcp_legacy``.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version as package_version
import json
import re
from threading import Lock
from typing import Any, Protocol

from app.core.security.json_schema import SchemaReferenceError, check_schema
from app.vault_runtime.extensions import mcp_legacy, mcp_modern
from app.vault_runtime.extensions.mcp_http import (
    McpAuthError, McpProtocolError, McpTimeoutError, McpTransportError, connection_headers,
)

__all__ = [
    "MCP_PROTOCOL_VERSION", "LEGACY_PROTOCOL_VERSION", "DiscoveredMcpTool", "HttpMcpTransport",
    "McpAuthError", "McpClient", "McpProtocolError", "McpTimeoutError", "McpTransportError",
]

MCP_PROTOCOL_VERSION = mcp_modern.PROTOCOL_VERSION
LEGACY_PROTOCOL_VERSION = mcp_legacy.PROTOCOL_VERSION
try:  # pyproject.toml is the one version source; the installed metadata carries it.
    VAULT_VERSION = package_version("resono-labs-vault")
except PackageNotFoundError:  # running from a source tree that was never installed
    VAULT_VERSION = "0+unknown"
MAX_DISCOVERY_PAGES = 16
MAX_DISCOVERED_TOOLS = 256
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_TOOL_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_CLIENT_INFO = {"name": "resono-vault", "version": VAULT_VERSION}
_ERAS: dict[str, str] = {}      # endpoint -> "modern" | "legacy", for this process
_ERAS_LOCK = Lock()


class McpTransport(Protocol):
    def open(self) -> dict[str, Any]: ...
    def request(self, method: str, *, params: dict[str, Any] | None = None,
                input_schema: dict[str, Any] | None = None) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class DiscoveredMcpTool:
    name: str
    title: str | None
    description: str
    input_schema: dict[str, object]
    output_schema: dict[str, object] | None


def _speaks_legacy(exc: McpProtocolError) -> bool:
    """Whether a failed current-protocol request means the server is a legacy one."""
    if isinstance(exc, (McpTransportError, McpAuthError)):
        return False
    if exc.code == -32601:          # current servers MUST implement server/discover
        return True
    if exc.code == mcp_modern.UNSUPPORTED_PROTOCOL_VERSION:
        supported = exc.data.get("supported") if isinstance(exc.data, dict) else None
        return isinstance(supported, list) and LEGACY_PROTOCOL_VERSION in supported
    return exc.status in (400, 404, 405) and exc.code not in mcp_modern.MODERN_ERROR_CODES


class HttpMcpTransport:
    """One connection. Secret headers are supplied at use time only and never stored."""

    def __init__(
        self, endpoint: str, *, public_headers: tuple[tuple[str, str], ...] = (),
        credential_headers: tuple[tuple[str, str], ...] = (),
        vault_headers: tuple[tuple[str, str], ...] = (), timeout_seconds: float = 15.0,
        post: Any = None,
    ) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("MCP timeout must be within 60 seconds")
        self._endpoint = endpoint
        headers = connection_headers(public=public_headers, credential=credential_headers, vault=vault_headers)
        session_key = connection_headers(public=public_headers, credential=credential_headers, vault=())
        extra = {} if post is None else {"post": post}
        self._modern = mcp_modern.ModernHttpTransport(
            endpoint, headers=headers, timeout_seconds=timeout_seconds, client_info=_CLIENT_INFO, **extra)
        self._legacy = mcp_legacy.LegacyHttpTransport(
            endpoint, headers=headers, session_key_headers=session_key, timeout_seconds=timeout_seconds,
            client_info=_CLIENT_INFO, **extra)
        self._active: Any = None

    @property
    def era(self) -> str | None:
        return None if self._active is None else self._active.era

    def open(self) -> dict[str, Any]:
        with _ERAS_LOCK:
            known = _ERAS.get(self._endpoint)
        if known == "legacy":
            try:
                return self._use(self._legacy)
            except McpProtocolError as exc:
                if isinstance(exc, (McpTransportError, McpAuthError)):
                    raise
                with _ERAS_LOCK:          # the server may have been upgraded
                    _ERAS.pop(self._endpoint, None)
        try:
            return self._use(self._modern)
        except McpProtocolError as exc:
            if not _speaks_legacy(exc):
                raise
        return self._use(self._legacy)

    def _use(self, transport: Any) -> dict[str, Any]:
        capabilities = transport.open()
        self._active = transport
        with _ERAS_LOCK:
            _ERAS[self._endpoint] = transport.era
        return capabilities

    def request(self, method: str, *, params: dict[str, Any] | None = None,
                input_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._active is None:
            raise McpProtocolError("MCP client is not initialized")
        return self._active.request(method, params=params, input_schema=input_schema)


class McpClient:
    def __init__(self, transport: McpTransport) -> None:
        self._transport = transport
        self._initialized = False

    def initialize(self) -> None:
        capabilities = self._transport.open()
        if not isinstance(capabilities, dict) or not isinstance(capabilities.get("tools"), dict):
            raise McpProtocolError("MCP server does not declare tools capability")
        self._initialized = True

    def discover_tools(self) -> tuple[DiscoveredMcpTool, ...]:
        self._require_initialized()
        tools: list[DiscoveredMcpTool] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        for _ in range(MAX_DISCOVERY_PAGES):
            params = {"cursor": cursor} if cursor is not None else None
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
            # An empty string is a valid cursor; only a repeat means a loop.
            if not isinstance(next_cursor, str) or next_cursor in seen_cursors:
                raise McpProtocolError("MCP discovery cursor is invalid")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        else:
            raise McpProtocolError("MCP discovery exceeds the page limit")
        names = [item.name for item in tools]
        if len(names) != len(set(names)):
            raise McpProtocolError("MCP tool names must be unique")
        return tuple(tools)

    def call_tool(self, name: str, arguments: dict[str, object], *,
                  input_schema: dict[str, object] | None = None) -> dict[str, object]:
        """One call; never retried here after a timeout (the tool may already have run)."""
        self._require_initialized()
        if not _TOOL_NAME.fullmatch(name):
            raise McpProtocolError("MCP tool name is invalid")
        result = self._transport.request("tools/call", params={"name": name, "arguments": arguments},
                                         input_schema=input_schema)
        content = result.get("content")
        if not isinstance(content, list) or any(not isinstance(item, dict) for item in content):
            raise McpProtocolError("MCP tool result content is invalid")
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
        check_schema(input_schema)
        if output_schema is not None:
            check_schema(output_schema)
    except SchemaReferenceError as exc:
        raise McpProtocolError(f"MCP tool {name} schema is refused: {exc}") from exc
    except Exception as exc:
        raise McpProtocolError("MCP tool schema is invalid") from exc
    # Annotations are deliberately ignored: server-provided effects are untrusted.
    return DiscoveredMcpTool(name, title.strip() if isinstance(title, str) else None, description.strip(), input_schema, output_schema)
