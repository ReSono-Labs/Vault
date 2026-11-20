"""Portable MCP configuration rules shared by Vault's import and the Plugin Kit.

Standard library only: the kit loads this same file (bundled as cli/vault_mcp_rules.py)
to validate mcp.json without a running Vault. Network policy (which hosts Vault may
reach) stays in app/core/security/outbound.py and is applied by the runtime only.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import re
from urllib.parse import urlparse


SUPPORTED_TRANSPORT = "streamable-http"
UNSUPPORTED_TRANSPORTS = frozenset({"stdio", "sse"})
MAX_SERVER_NAME_LENGTH = 128
# RFC 9110 field-name token.
_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
# Headers Vault generates for HTTP and MCP itself. A package or a stored credential may not set them.
_RESERVED_NAMES = frozenset({"accept", "content-type"})
_RESERVED_PREFIXES = ("mcp-", "x-vault-")
CREDENTIAL_HEADERS = frozenset({"authorization", "cookie", "proxy-authorization", "x-api-key"})


class McpRuleError(ValueError):
    pass


def server_name_problem(name: object) -> str | None:
    """A server name becomes one storage path segment and one connection identity."""
    if not isinstance(name, str) or not name or len(name) > MAX_SERVER_NAME_LENGTH:
        return f"server name must be 1-{MAX_SERVER_NAME_LENGTH} characters"
    if name in {".", ".."} or name != name.strip():
        return "server name must be one safe path segment"
    if any(char in "/\\" or ord(char) < 32 or ord(char) == 127 for char in name):
        return "server name must be one safe path segment"
    return None


def transport_problem(configuration: object) -> str | None:
    """Vault connects only to Streamable HTTP; stdio and the 2024-11-05 HTTP+SSE are skipped."""
    transport = configuration.get("type") if isinstance(configuration, dict) else None
    if transport in UNSUPPORTED_TRANSPORTS:
        return f"unsupported transport {transport}; Vault connects only to {SUPPORTED_TRANSPORT} servers"
    return None


def url_problem(value: object) -> str | None:
    if not isinstance(value, str):
        return "MCP URL is required"
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"} or not parsed.netloc
        or parsed.username or parsed.password or parsed.fragment
    ):
        return "MCP URL must be absolute and contain no credentials or fragment"
    if not parsed.hostname:
        return "MCP URL host is required"
    return None


def is_reserved_header(name: str) -> bool:
    folded = name.casefold()
    return folded in _RESERVED_NAMES or folded.startswith(_RESERVED_PREFIXES)


def validate_headers(headers: object, *, allow_credentials: bool, label: str = "MCP header") -> dict[str, str]:
    """Valid HTTP fields, no Vault-generated names, no two names that differ only by case."""
    if not isinstance(headers, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in headers.items()
    ):
        raise McpRuleError(f"{label}s must map strings to strings")
    seen: set[str] = set()
    for name, value in headers.items():
        if not _TOKEN.fullmatch(name):
            raise McpRuleError(f"{label} name '{name}' is not a valid HTTP field name")
        if any(char in value for char in "\r\n\0"):
            raise McpRuleError(f"{label} '{name}' has a value with a line break or NUL")
        folded = name.casefold()
        if folded in seen:
            raise McpRuleError(f"{label} names collide by case: {name}")
        seen.add(folded)
        if is_reserved_header(name):
            raise McpRuleError(f"{label} '{name}' is set by Vault and cannot be configured")
        if not allow_credentials and folded in CREDENTIAL_HEADERS:
            raise McpRuleError("credentials require separate secret storage")
    return dict(headers)


def merge_headers(*layers: Mapping[str, str] | Iterable[tuple[str, str]]) -> dict[str, str]:
    """Merge header layers ignoring case; a later layer wins and keeps its spelling."""
    merged: dict[str, tuple[str, str]] = {}
    for layer in layers:
        items = layer.items() if isinstance(layer, Mapping) else layer
        for name, value in items:
            merged[str(name).casefold()] = (str(name), str(value))
    return dict(merged.values())


def connection_executable(configuration: Mapping[str, object]) -> bool:
    """Whether a stored MCP connection may send requests: Streamable HTTP only.

    Records written before the transport was stored are Streamable HTTP (the only
    transport Vault ever connected to).
    """
    return (
        configuration.get("transport", SUPPORTED_TRANSPORT) == SUPPORTED_TRANSPORT
        and configuration.get("executable", True) is True
    )
