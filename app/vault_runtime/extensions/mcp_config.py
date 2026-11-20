"""MCP configuration validation adapted from R1 mcp/connections.py (SHA in Phase 5 inventory)."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from app.core.exceptions import BadRequestError
from app.core.security.outbound import validate_extension_url


class McpConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class McpConfiguration:
    transport: str
    endpoint: str | None = None
    command: str | None = None
    args: tuple[str, ...] = ()
    headers: tuple[tuple[str, str], ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    cwd: str | None = None
    executable: bool = False


def validate_mcp_configuration(value: object) -> McpConfiguration:
    if not isinstance(value, dict):
        raise McpConfigurationError("MCP configuration must be an object")
    transport = value.get("type")
    if transport in {"streamable-http", "sse"}:
        if set(value) - {"type", "url", "headers"}:
            raise McpConfigurationError("remote MCP configuration has unsupported fields")
        endpoint = _remote_url(value.get("url"))
        headers = _string_map(value.get("headers", {}), "headers")
        folded = [name.casefold() for name in headers]
        if len(folded) != len(set(folded)):
            raise McpConfigurationError("MCP header names collide by case")
        secret_headers = {"authorization", "cookie", "proxy-authorization", "x-api-key"}
        if any(name in secret_headers for name in folded):
            raise McpConfigurationError("credentials require separate secret storage")
        return McpConfiguration(
            transport=str(transport), endpoint=endpoint,
            headers=tuple(sorted(headers.items())), executable=transport == "streamable-http",
        )
    if transport == "stdio":
        if set(value) - {"type", "command", "args", "env", "cwd"}:
            raise McpConfigurationError("stdio MCP configuration has unsupported fields")
        command = value.get("command")
        if not isinstance(command, str) or not command or any(char.isspace() for char in command):
            raise McpConfigurationError("stdio command must be one executable token")
        args = value.get("args", [])
        if not isinstance(args, list) or any(not isinstance(item, str) for item in args):
            raise McpConfigurationError("stdio args must be strings")
        env = _string_map(value.get("env", {}), "environment")
        cwd = value.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            raise McpConfigurationError("stdio cwd must be a string")
        if {"PLUGIN_ROOT", "PLUGIN_DATA"} & set(env):
            raise McpConfigurationError("reserved Plugin environment variables are forbidden")
        return McpConfiguration(
            transport="stdio", command=command, args=tuple(args),
            env=tuple(sorted(env.items())), cwd=cwd, executable=False,
        )
    raise McpConfigurationError("MCP transport must be streamable-http, sse, or stdio")


def _remote_url(value: object) -> str:
    if not isinstance(value, str):
        raise McpConfigurationError("MCP URL is required")
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"} or not parsed.netloc
        or parsed.username or parsed.password or parsed.fragment
    ):
        raise McpConfigurationError("MCP URL must be absolute and contain no credentials or fragment")
    host = parsed.hostname
    if not host:
        raise McpConfigurationError("MCP URL host is required")
    try:
        validate_extension_url(value, target="MCP URL")
    except BadRequestError as exc:
        raise McpConfigurationError(str(exc)) from exc
    return value


def _string_map(value: object, field: str) -> dict[str, str]:
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not isinstance(item, str) for key, item in value.items()
    ):
        raise McpConfigurationError(f"MCP {field} must map strings to strings")
    return dict(value)
