"""Shared HTTP layer for Vault's MCP client adapters (current and legacy protocol eras).

One place for what both eras must do the same way: the destination check (and connecting
to the address that was checked), header merging where Vault's own headers win, a body
limit enforced while reading, JSON and SSE response parsing with id correlation, and
mapping HTTP and JSON-RPC failures to distinct errors. Nothing here knows a protocol
version; ``mcp_modern`` and ``mcp_legacy`` build the requests.
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import socket
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.core.exceptions import BadRequestError
from app.core.security.outbound import _is_extension_local_name, validate_extension_host
from app.vault_runtime.extensions.mcp_rules import is_reserved_header, merge_headers

MAX_RESPONSE_BYTES = 4 * 1024 * 1024
ACCEPT = "application/json, text/event-stream"


class McpProtocolError(RuntimeError):
    """The server answered, but not with a usable result. ``code`` is the JSON-RPC code if any."""

    def __init__(self, message: str, *, code: int | None = None, status: int | None = None,
                 data: Any = None) -> None:
        super().__init__(message)
        self.code, self.status, self.data = code, status, data


class McpTransportError(McpProtocolError):
    """The request could not be delivered or the answer was cut off; it may have run."""


class McpTimeoutError(McpTransportError):
    """No complete answer within the deadline; a side-effecting call may have run."""


class McpAuthError(McpProtocolError):
    """The server refused the credentials (HTTP 401 or 403). ``challenge`` is its
    ``WWW-Authenticate`` header, if any (sign-in discovery and scope step-up use it)."""

    def __init__(self, message: str, *, status: int | None = None, challenge: str | None = None) -> None:
        super().__init__(message, status=status)
        self.challenge = challenge


@dataclass(frozen=True, slots=True)
class HttpAnswer:
    status: int
    headers: dict[str, str]
    message: dict[str, Any] | None   # the JSON-RPC response for the request id, if any


def connection_headers(*, public: tuple[tuple[str, str], ...], credential: tuple[tuple[str, str], ...],
                       vault: tuple[tuple[str, str], ...]) -> dict[str, str]:
    """Package, then credential, then Vault headers, merged ignoring case; later layers win.
    Names Vault generates are dropped from the package and credential layers."""
    return merge_headers(
        ((name, value) for name, value in public if not is_reserved_header(name)),
        ((name, value) for name, value in credential if not is_reserved_header(name)),
        vault,
    )


def _pinned_target(endpoint: str) -> tuple[str, str | None, str | None]:
    """(url to connect to, Host header, TLS server name) for a checked destination.

    Public hosts are resolved and checked here, and the request goes to that checked
    address, so a second DNS answer cannot redirect it (DNS rebinding). Loopback and
    Vault's own local names are not pinned.
    """
    parts = urlsplit(endpoint)
    host = parts.hostname
    if not host:
        raise McpTransportError("MCP endpoint host is invalid")
    try:
        validated = validate_extension_host(host, target="MCP host")
    except BadRequestError as exc:
        raise McpTransportError("MCP endpoint resolved to a denied network") from exc
    try:
        ipaddress.ip_address(validated)
        return endpoint, None, None
    except ValueError:
        pass
    if _is_extension_local_name(validated):
        return endpoint, None, None
    try:
        infos = socket.getaddrinfo(validated, parts.port or (443 if parts.scheme == "https" else 80),
                                   type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise McpTransportError("MCP host could not be resolved") from exc
    address = None
    for info in infos:
        candidate = info[4][0]
        try:
            validate_extension_host(candidate, target="MCP host")
        except BadRequestError as exc:
            raise McpTransportError("MCP endpoint resolved to a denied network") from exc
        address = address or candidate
    if address is None:
        raise McpTransportError("MCP host could not be resolved")
    literal = f"[{address}]" if ":" in address else address
    netloc = literal + (f":{parts.port}" if parts.port else "")
    host_header = parts.hostname + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, "")), host_header, validated


def post(endpoint: str, *, headers: dict[str, str], payload: dict[str, Any], request_id: Any,
         timeout_seconds: float, max_bytes: int = MAX_RESPONSE_BYTES, client: Any = None) -> HttpAnswer:
    """POST one JSON-RPC message and read the answer within ``max_bytes`` as it streams.

    A JSON body is one message; an SSE body is read event by event until the response
    for ``request_id`` arrives (request-scoped notifications before it are skipped).
    """
    import httpx

    url, host_header, server_name = _pinned_target(endpoint)
    send = merge_headers(headers, {"Accept": ACCEPT, "Content-Type": "application/json"})
    if host_header is not None:
        send = merge_headers(send, {"Host": host_header})
    extensions = {"sni_hostname": server_name} if server_name and url.startswith("https://") else {}
    body = json.dumps(payload, separators=(",", ":")).encode()
    owned = client is None
    client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=False)
    try:
        request = client.build_request("POST", url, headers=send, content=body, extensions=extensions)
        response = client.send(request, stream=True)
        try:
            kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
            answer_headers = {key.lower(): value for key, value in response.headers.items()}
            if kind == "text/event-stream" and 200 <= response.status_code < 300:
                message = _read_sse(response, request_id, max_bytes)
            else:
                raw = _read_bounded(response, max_bytes)
                # A refusal (401/403) is about credentials whatever its body says.
                message = _decode_message(raw, request_id) if raw.strip() and response.status_code not in (401, 403) else None
        finally:
            response.close()
    except httpx.TimeoutException as exc:
        raise McpTimeoutError("MCP server did not answer in time") from exc
    except httpx.HTTPError as exc:
        raise McpTransportError("MCP server is unreachable") from exc
    finally:
        if owned:
            client.close()
    return HttpAnswer(response.status_code, answer_headers, message)


@dataclass(frozen=True, slots=True)
class FetchedDocument:
    status: int
    headers: dict[str, str]
    body: bytes


def fetch(url: str, *, method: str = "GET", headers: dict[str, str] | None = None,
          form: dict[str, str] | None = None, json_body: Any = None, timeout_seconds: float = 15.0,
          max_bytes: int = 1024 * 1024, require_https: bool = True, allow_local: bool = True) -> FetchedDocument:
    """One request through the same destination check, DNS pinning, no-redirect rule and
    byte limit as MCP traffic (used for sign-in discovery, registration and tokens).

    ``require_https`` refuses plain HTTP except to this machine (OAuth 2.1 allows loopback).
    ``allow_local=False`` also refuses this machine: addresses a remote server chose (its
    sign-in server, say) must not reach Vault's own local services.
    """
    import httpx

    parts = urlsplit(url)
    if parts.scheme not in ("https", "http") or parts.fragment:
        raise McpTransportError("URL is invalid")
    if not allow_local and _is_extension_local_name(parts.hostname or ""):
        raise McpTransportError("A remote server may not send Vault to this machine")
    if require_https and parts.scheme != "https" and not _is_extension_local_name(parts.hostname or ""):
        raise McpTransportError("Sign-in servers must use HTTPS")
    target, host_header, server_name = _pinned_target(url)
    send = dict(headers or {})
    if host_header is not None:
        send = merge_headers(send, {"Host": host_header})
    extensions = {"sni_hostname": server_name} if server_name and target.startswith("https://") else {}
    content: bytes | None = None
    if form is not None:
        from urllib.parse import urlencode
        content = urlencode(form).encode()
        send = merge_headers(send, {"Content-Type": "application/x-www-form-urlencoded"})
    elif json_body is not None:
        content = json.dumps(json_body, separators=(",", ":")).encode()
        send = merge_headers(send, {"Content-Type": "application/json"})
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=False) as client:
            request = client.build_request(method, target, headers=send, content=content, extensions=extensions)
            response = client.send(request, stream=True)
            try:
                body = _read_bounded(response, max_bytes)
            finally:
                response.close()
    except httpx.TimeoutException as exc:
        raise McpTimeoutError("Server did not answer in time") from exc
    except httpx.HTTPError as exc:
        raise McpTransportError("Server is unreachable") from exc
    return FetchedDocument(response.status_code, {k.lower(): v for k, v in response.headers.items()}, body)


def result_of(answer: HttpAnswer) -> dict[str, Any]:
    """The JSON-RPC result, or the matching error: auth, protocol (with code) or HTTP."""
    message = answer.message
    if answer.status in (401, 403):
        raise McpAuthError("MCP server refused the credentials", status=answer.status,
                           challenge=answer.headers.get("www-authenticate"))
    if isinstance(message, dict) and isinstance(message.get("error"), dict):
        error = message["error"]
        code = error.get("code") if isinstance(error.get("code"), int) else None
        text = error.get("message") if isinstance(error.get("message"), str) else "MCP server returned an error"
        raise McpProtocolError(text[:300], code=code, status=answer.status, data=error.get("data"))
    if not 200 <= answer.status < 300:
        raise McpProtocolError(f"MCP server answered HTTP {answer.status}", status=answer.status)
    if not isinstance(message, dict):
        raise McpProtocolError("MCP response is missing")
    result = message.get("result")
    if not isinstance(result, dict):
        raise McpProtocolError("MCP result must be an object")
    return result


def _read_bounded(response: Any, max_bytes: int) -> bytes:
    chunks, size = [], 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > max_bytes:
            raise McpProtocolError("MCP response exceeds the size limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _decode_message(raw: bytes, request_id: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise McpProtocolError("MCP response is not valid JSON") from exc
    if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
        raise McpProtocolError("MCP response envelope is invalid")
    if "id" in value and value.get("id") != request_id and value.get("id") is not None:
        raise McpProtocolError("MCP response envelope is invalid")
    return value


def _read_sse(response: Any, request_id: Any, max_bytes: int) -> dict[str, Any]:
    size, data_lines = 0, []
    for line in response.iter_lines():
        size += len(line) + 1
        if size > max_bytes:
            raise McpProtocolError("MCP response exceeds the size limit")
        if line.startswith(":"):
            continue          # comment / keep-alive
        if line == "":
            if data_lines:
                message = _decode_event("\n".join(data_lines), request_id)
                data_lines = []
                if message is not None:
                    return message
            continue
        field, _, value = line.partition(":")
        if field == "data":
            data_lines.append(value[1:] if value.startswith(" ") else value)
    if data_lines:
        message = _decode_event("\n".join(data_lines), request_id)
        if message is not None:
            return message
    raise McpTransportError("MCP event stream ended before the response")


def _decode_event(data: str, request_id: Any) -> dict[str, Any] | None:
    """The response for ``request_id``; notifications and other ids are skipped."""
    try:
        value = json.loads(data)
    except ValueError as exc:
        raise McpProtocolError("MCP event is not valid JSON") from exc
    if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
        raise McpProtocolError("MCP event envelope is invalid")
    if "method" in value and "id" not in value:
        return None           # request-scoped notification (progress, log)
    if "method" in value:
        raise McpProtocolError("MCP server sent a request on the response stream")
    if value.get("id") != request_id:
        return None
    return value
