"""MCP 2026-07-28 client adapter over Streamable HTTP (per-request metadata, no sessions).

Every request carries ``params._meta`` with the protocol version, client capabilities and
client identity, and mirrors ``method`` / ``params.name`` and any ``x-mcp-header``
annotated tool arguments into HTTP headers. Discovery uses ``server/discover``. This
module imports nothing from the legacy (2025-11-25) adapter.
"""
from __future__ import annotations

import base64
import logging
import re
from collections.abc import Callable
from typing import Any

from app.vault_runtime.extensions import mcp_http
from app.vault_runtime.extensions.mcp_http import McpProtocolError

PROTOCOL_VERSION = "2026-07-28"
HEADER_MISMATCH = -32020
MISSING_REQUIRED_CLIENT_CAPABILITY = -32021
UNSUPPORTED_PROTOCOL_VERSION = -32022
MODERN_ERROR_CODES = frozenset({HEADER_MISMATCH, MISSING_REQUIRED_CLIENT_CAPABILITY, UNSUPPORTED_PROTOCOL_VERSION})
_NAMED_METHODS = {"tools/call": "name", "prompts/get": "name", "resources/read": "uri"}
_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_SAFE_VALUE = re.compile(r"^[\x21-\x7e]([\x20-\x7e\t]*[\x21-\x7e])?$")
_MAX_SAFE_INTEGER = 2**53 - 1
_VALUE_KEYWORDS = frozenset({"x-mcp-header", "default", "const", "enum", "examples"})  # data, not schemas
_LOG = logging.getLogger(__name__)


class InvalidHeaderAnnotation(ValueError):
    """A tool's ``x-mcp-header`` annotations break the spec; the tool is not offered."""


def encode_header_value(value: str) -> str:
    """Plain when header-safe ASCII; otherwise (or when it looks like the sentinel) Base64."""
    if _SAFE_VALUE.fullmatch(value) and not (value.startswith("=?base64?") and value.endswith("?=")):
        return value
    return "=?base64?" + base64.b64encode(value.encode()).decode() + "?="


def header_paths(input_schema: dict[str, Any]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """(header name, property path) for each ``x-mcp-header`` annotation.

    Raises ``InvalidHeaderAnnotation`` when any annotation is malformed, duplicated, on a
    non-primitive (or ``number``) property, or not reachable through ``properties`` alone.
    """
    found: list[tuple[str, tuple[str, ...]]] = []

    def walk(node: Any, path: tuple[str, ...], reachable: bool) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, path, False)
            return
        if not isinstance(node, dict):
            return
        if "x-mcp-header" in node:
            name = node["x-mcp-header"]
            if not reachable or not path:
                raise InvalidHeaderAnnotation("x-mcp-header is not reachable through properties")
            if not isinstance(name, str) or not _TOKEN.fullmatch(name):
                raise InvalidHeaderAnnotation("x-mcp-header is not a valid header token")
            if node.get("type") not in {"string", "integer", "boolean"}:
                raise InvalidHeaderAnnotation("x-mcp-header must annotate a string, integer or boolean")
            found.append((name, path))
        for key, child in node.items():
            if key == "properties" and isinstance(child, dict):
                for prop, schema in child.items():
                    walk(schema, path + (prop,), reachable)
            elif key not in _VALUE_KEYWORDS:
                walk(child, path, False)

    walk(input_schema, (), True)
    lowered = [name.lower() for name, _ in found]
    if len(lowered) != len(set(lowered)):
        raise InvalidHeaderAnnotation("x-mcp-header values must be unique")
    return tuple(found)


def param_headers(input_schema: dict[str, Any] | None, arguments: dict[str, Any]) -> dict[str, str]:
    if not input_schema:
        return {}
    headers: dict[str, str] = {}
    for name, path in header_paths(input_schema):
        value: Any = arguments
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
            if value is None:
                break
        if value is None:
            continue
        if isinstance(value, bool):
            text = "true" if value else "false"
        elif isinstance(value, int):
            if abs(value) > _MAX_SAFE_INTEGER:
                raise McpProtocolError("MCP header argument is outside the safe integer range")
            text = str(value)
        elif isinstance(value, str):
            text = value
        else:
            continue
        headers[f"Mcp-Param-{name}"] = encode_header_value(text)
    return headers


class ModernHttpTransport:
    era = "modern"

    def __init__(self, endpoint: str, *, headers: dict[str, str], timeout_seconds: float,
                 client_info: dict[str, str], post: Callable[..., mcp_http.HttpAnswer] = mcp_http.post) -> None:
        self._endpoint, self._headers, self._timeout = endpoint, headers, timeout_seconds
        self._client_info, self._post, self._next_id = client_info, post, 0

    def open(self) -> dict[str, Any]:
        """``server/discover``; the capabilities when this server speaks 2026-07-28."""
        result = self._send("server/discover", {})
        versions = result.get("supportedVersions")
        if not isinstance(versions, list) or PROTOCOL_VERSION not in versions:
            raise McpProtocolError("MCP server does not support protocol 2026-07-28",
                                   code=UNSUPPORTED_PROTOCOL_VERSION, data={"supported": versions})
        capabilities = result.get("capabilities")
        if not isinstance(capabilities, dict):
            raise McpProtocolError("MCP server/discover result is invalid")
        return capabilities

    def request(self, method: str, *, params: dict[str, Any] | None = None,
                input_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(params or {})
        if method == "tools/list":
            result = self._send(method, params)
            if isinstance(result.get("tools"), list):
                result = {**result, "tools": [tool for tool in result["tools"] if self._offerable(tool)]}
            return result
        if method != "tools/call":
            return self._send(method, params)
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        try:
            return self._send(method, params, param_headers(input_schema, arguments))
        except McpProtocolError as exc:
            if exc.code != HEADER_MISMATCH or isinstance(exc, mcp_http.McpTransportError):
                raise
        # The server rejected the headers before running the tool: re-list and retry once.
        fresh = self._listed_schema(str(params.get("name")))
        return self._send(method, params, param_headers(fresh, arguments))

    def _send(self, method: str, params: dict[str, Any], extra: dict[str, str] | None = None) -> dict[str, Any]:
        self._next_id += 1
        meta = dict(params.get("_meta") or {})
        meta.update({
            "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
            "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/clientInfo": self._client_info,
        })
        body = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": {**params, "_meta": meta}}
        headers = mcp_http.merge_headers(self._headers, extra or {}, {
            "MCP-Protocol-Version": PROTOCOL_VERSION, "Mcp-Method": method,
        })
        if method in _NAMED_METHODS:
            headers["Mcp-Name"] = encode_header_value(str(params.get(_NAMED_METHODS[method], "")))
        answer = self._post(self._endpoint, headers=headers, payload=body, request_id=self._next_id,
                            timeout_seconds=self._timeout)
        result = mcp_http.result_of(answer)
        kind = result.get("resultType", "complete")
        if kind == "input_required":
            raise McpProtocolError("MCP server asked for more input, which Vault does not support yet")
        if kind != "complete":
            raise McpProtocolError("MCP result type is not supported")
        return result

    def _offerable(self, tool: Any) -> bool:
        schema = tool.get("inputSchema") if isinstance(tool, dict) else None
        if not isinstance(schema, dict):
            return True        # shape errors are reported by the client's own checks
        try:
            header_paths(schema)
        except InvalidHeaderAnnotation as exc:
            _LOG.warning("MCP tool %r not offered: %s", str(tool.get("name"))[:128], exc)
            return False
        return True

    def _listed_schema(self, name: str) -> dict[str, Any]:
        cursor: str | None = None
        for _ in range(16):
            result = self.request("tools/list", params={"cursor": cursor} if cursor is not None else None)
            for tool in result.get("tools") or ():
                if isinstance(tool, dict) and tool.get("name") == name and isinstance(tool.get("inputSchema"), dict):
                    return tool["inputSchema"]
            cursor = result.get("nextCursor")
            if not isinstance(cursor, str):
                break
        raise McpProtocolError("MCP tool is no longer offered by the server")
