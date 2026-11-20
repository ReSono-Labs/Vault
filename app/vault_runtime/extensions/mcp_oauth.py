"""MCP authorization (2026-07-28 "Authorization"): OAuth 2.1 sign-in for protected MCP servers.

Implements the client side of the spec:
- discovery: the server's 401 ``WWW-Authenticate`` challenge (RFC 6750 / RFC 9728), protected
  resource metadata (header URL, then path and root well-known URIs), and authorization server
  metadata (RFC 8414 and OpenID Connect discovery in the spec's order), with the ``issuer``
  check of RFC 8414 section 3.3;
- PKCE ``S256`` required, refused when the server does not advertise it;
- client registration in the spec's priority: pre-registered, Client ID Metadata Document (when
  Vault has one configured and the server supports it), then Dynamic Client Registration;
- the ``resource`` indicator (RFC 8707) on authorization, token and refresh requests;
- ``iss`` validation of the authorization response (RFC 9207) before the code is redeemed;
- refresh with rotation, revocation (RFC 7009) on disconnect, scope union for step-up.

Every request goes through ``mcp_http.fetch``: Vault's destination check, DNS pinning, no
redirects, a byte limit, and HTTPS except to this machine. Tokens and client secrets never
appear in errors or logs.
"""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import re
import secrets
import time
from typing import Any, Callable
from urllib.parse import urlencode, urlsplit, urlunsplit

from app.vault_runtime.extensions import mcp_http

_PARAM = re.compile(r'([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^\s,]+))')
_ERROR_CODE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class McpSignInError(RuntimeError):
    """Sign-in cannot proceed. ``code`` is a stable reason the UI can act on."""

    def __init__(self, message: str, *, code: str = "sign_in_failed") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class AuthServer:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str | None = None
    revocation_endpoint: str | None = None
    scopes_supported: tuple[str, ...] | None = None
    token_auth_methods: tuple[str, ...] = ()
    cimd_supported: bool = False
    iss_parameter_supported: bool = False


@dataclass(frozen=True, slots=True)
class SignInPlan:
    resource: str
    server: AuthServer
    scope: str | None


@dataclass(frozen=True, slots=True)
class ClientRegistration:
    issuer: str
    client_id: str
    client_secret: str | None = None
    token_endpoint_auth_method: str = "none"
    source: str = "dynamic"           # "manual", "metadata_document" or "dynamic"


@dataclass(slots=True)
class TokenSet:
    access_token: str
    token_type: str
    resource: str
    issuer: str
    client_id: str
    token_endpoint: str
    revocation_endpoint: str | None = None
    refresh_token: str | None = None
    expires_at: float | None = None
    scope: str | None = None
    obtained_at: float = field(default_factory=time.time)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "TokenSet":
        return cls(**{key: value.get(key) for key in cls.__dataclass_fields__ if key in value})

    def expires_soon(self, now: float, margin: float = 60.0) -> bool:
        return self.expires_at is not None and self.expires_at - margin <= now


Fetcher = Callable[..., mcp_http.FetchedDocument]


def parse_challenge(header: str | None) -> dict[str, str]:
    """Parameters of the ``Bearer`` challenge in a ``WWW-Authenticate`` header."""
    if not header:
        return {}
    match = re.search(r"(?:^|,\s*|\s)Bearer\b", header, flags=re.IGNORECASE)
    if match is None:
        return {}
    rest = header[match.end():]
    # Stop at the next auth scheme ("Basic realm=..." etc.): a token followed by a space then a param.
    following = re.search(r",\s*[A-Za-z][A-Za-z0-9!#$%&'*+.^_`|~-]*\s+[A-Za-z_][A-Za-z0-9_-]*\s*=", rest)
    if following is not None:
        rest = rest[:following.start()]
    values: dict[str, str] = {}
    for name, quoted, bare in _PARAM.findall(rest):
        values.setdefault(name.lower(), re.sub(r"\\(.)", r"\1", quoted) if quoted else bare)
    return values


def canonical_resource(endpoint: str) -> str:
    """The MCP server's canonical URI (RFC 8707): lowercase scheme and host, no fragment,
    no trailing slash on a bare origin."""
    parts = urlsplit(endpoint)
    if parts.scheme.lower() not in ("https", "http") or not parts.hostname:
        raise McpSignInError("MCP endpoint is not an absolute HTTP URL", code="invalid_endpoint")
    netloc = parts.hostname.lower()
    if ":" in netloc:
        netloc = f"[{netloc}]"
    if parts.port is not None:
        netloc += f":{parts.port}"
    path = "" if parts.path in ("", "/") else parts.path
    return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))


def _resource_covers(prm_resource: str, resource: str) -> bool:
    """A metadata ``resource`` is acceptable when it names this server or a parent path of it
    on the same origin (the rule the reference SDK applies)."""
    try:
        wanted, offered = urlsplit(canonical_resource(resource)), urlsplit(canonical_resource(prm_resource))
    except McpSignInError:
        return False
    if (wanted.scheme, wanted.netloc) != (offered.scheme, offered.netloc):
        return False
    return (wanted.path.rstrip("/") + "/").startswith(offered.path.rstrip("/") + "/")


def _json(document: mcp_http.FetchedDocument) -> dict[str, Any] | None:
    if document.status != 200:
        return None
    try:
        value = json.loads(document.body)
    except (ValueError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _https_url(value: Any, label: str, *, allow_loopback_http: bool = True) -> str:
    if not isinstance(value, str) or not value:
        raise McpSignInError(f"Sign-in server metadata has no {label}", code="invalid_metadata")
    parts = urlsplit(value)
    local = (parts.hostname or "") in {"localhost", "127.0.0.1", "::1"}
    if parts.scheme != "https" and not (allow_loopback_http and parts.scheme == "http" and local):
        raise McpSignInError(f"Sign-in server {label} must use HTTPS", code="invalid_metadata")
    if parts.fragment:
        raise McpSignInError(f"Sign-in server {label} is invalid", code="invalid_metadata")
    return value


def protected_resource_metadata_urls(endpoint: str, header_url: str | None) -> list[str]:
    parts = urlsplit(endpoint)
    origin = f"{parts.scheme}://{parts.netloc}"
    urls = [header_url] if header_url else []
    if parts.path and parts.path != "/":
        urls.append(f"{origin}/.well-known/oauth-protected-resource{parts.path}")
    urls.append(f"{origin}/.well-known/oauth-protected-resource")
    return urls


def authorization_server_metadata_urls(issuer: str) -> list[str]:
    parts = urlsplit(issuer)
    origin = f"{parts.scheme}://{parts.netloc}"
    path = parts.path.rstrip("/")
    if path:
        return [f"{origin}/.well-known/oauth-authorization-server{path}",
                f"{origin}/.well-known/openid-configuration{path}",
                f"{origin}{path}/.well-known/openid-configuration"]
    return [f"{origin}/.well-known/oauth-authorization-server", f"{origin}/.well-known/openid-configuration"]


def _issuers_match(a: str, b: str) -> bool:
    """Simple string comparison (RFC 8414 3.3); a bare origin with or without "/" is one issuer."""
    if a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    parts = urlsplit(shorter)
    return longer == shorter + "/" and shorter == f"{parts.scheme}://{parts.netloc}"


def discover(endpoint: str, challenge: str | None, *, fetch: Fetcher = mcp_http.fetch,
             previous_scope: str | None = None) -> SignInPlan:
    """Find the server's authorization server and the scopes to ask for."""
    resource = canonical_resource(endpoint)
    params = parse_challenge(challenge)
    metadata: dict[str, Any] | None = None
    for url in protected_resource_metadata_urls(endpoint, params.get("resource_metadata")):
        try:
            metadata = _json(fetch(url, headers={"Accept": "application/json",
                                                 "MCP-Protocol-Version": "2026-07-28"}))
        except mcp_http.McpTransportError:
            metadata = None
        if metadata is not None:
            break
    if metadata is None:
        raise McpSignInError("This MCP server asks for sign-in but publishes no sign-in details "
                             "(protected resource metadata)", code="no_resource_metadata")
    prm_resource = metadata.get("resource")
    if isinstance(prm_resource, str):
        if not _resource_covers(prm_resource, resource):
            raise McpSignInError("The server's sign-in details name a different server", code="resource_mismatch")
        resource = canonical_resource(prm_resource)
    servers = metadata.get("authorization_servers")
    if not isinstance(servers, list) or not servers or not all(isinstance(item, str) for item in servers):
        raise McpSignInError("The server's sign-in details list no authorization server", code="invalid_metadata")
    # RFC 9728 7.6 leaves the choice to the client; Vault uses the first one listed.
    server = authorization_server(servers[0], fetch=fetch)
    if params.get("scope"):
        scope: str | None = params["scope"]
    elif isinstance(metadata.get("scopes_supported"), list):
        scope = " ".join(str(item) for item in metadata["scopes_supported"]) or None
    else:
        scope = None
    scope = union_scopes(previous_scope, scope)
    if scope and server.scopes_supported and "offline_access" in server.scopes_supported \
            and "offline_access" not in scope.split():
        scope += " offline_access"
    return SignInPlan(resource=resource, server=server, scope=scope)


def authorization_server(issuer: str, *, fetch: Fetcher = mcp_http.fetch) -> AuthServer:
    _https_url(issuer, "issuer")
    for url in authorization_server_metadata_urls(issuer):
        try:
            document = fetch(url, headers={"Accept": "application/json"})
        except mcp_http.McpTransportError:
            continue
        value = _json(document)
        if value is None:
            if document.status >= 500:
                break
            continue
        if not isinstance(value.get("issuer"), str) or not _issuers_match(value["issuer"], issuer):
            raise McpSignInError("Sign-in server metadata names a different issuer", code="issuer_mismatch")
        methods = value.get("code_challenge_methods_supported")
        if not isinstance(methods, list) or "S256" not in methods:
            raise McpSignInError("Sign-in server does not support PKCE (S256); Vault will not continue",
                                 code="pkce_unsupported")
        response_types = value.get("response_types_supported")
        if isinstance(response_types, list) and "code" not in response_types:
            raise McpSignInError("Sign-in server does not offer the authorization code flow", code="invalid_metadata")
        scopes = value.get("scopes_supported")
        auth_methods = value.get("token_endpoint_auth_methods_supported")
        return AuthServer(
            issuer=value["issuer"],
            authorization_endpoint=_https_url(value.get("authorization_endpoint"), "authorization endpoint"),
            token_endpoint=_https_url(value.get("token_endpoint"), "token endpoint"),
            registration_endpoint=(_https_url(value["registration_endpoint"], "registration endpoint")
                                   if value.get("registration_endpoint") else None),
            revocation_endpoint=(_https_url(value["revocation_endpoint"], "revocation endpoint")
                                 if value.get("revocation_endpoint") else None),
            scopes_supported=tuple(str(item) for item in scopes) if isinstance(scopes, list) else None,
            token_auth_methods=tuple(str(item) for item in auth_methods) if isinstance(auth_methods, list)
            else ("client_secret_basic",),
            cimd_supported=value.get("client_id_metadata_document_supported") is True,
            iss_parameter_supported=value.get("authorization_response_iss_parameter_supported") is True,
        )
    raise McpSignInError("Sign-in server publishes no metadata", code="no_server_metadata")


def union_scopes(previous: str | None, new: str | None) -> str | None:
    if not previous:
        return new
    if not new:
        return previous
    merged = previous.split()
    for item in new.split():
        if item not in merged:
            merged.append(item)
    return " ".join(merged)


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def register_client(server: AuthServer, *, redirect_uri: str, client_name: str,
                    fetch: Fetcher = mcp_http.fetch) -> ClientRegistration:
    """Dynamic Client Registration (RFC 7591), kept for servers without metadata documents."""
    if not server.registration_endpoint:
        raise McpSignInError("This sign-in server needs a client ID from its provider. "
                             "The device owner can enter one for this connection.",
                             code="client_registration_required")
    host = urlsplit(redirect_uri).hostname or ""
    native = host in {"localhost", "127.0.0.1", "::1"}
    method = "none"
    document = fetch(server.registration_endpoint, method="POST", headers={"Accept": "application/json"},
                     json_body={
                         "client_name": client_name,
                         "redirect_uris": [redirect_uri],
                         "grant_types": ["authorization_code", "refresh_token"],
                         "response_types": ["code"],
                         "token_endpoint_auth_method": method,
                         "application_type": "native" if native else "web",
                     })
    if document.status not in (200, 201):
        raise McpSignInError(f"Sign-in server refused client registration (HTTP {document.status})",
                             code="registration_refused")
    value = _json(mcp_http.FetchedDocument(200, document.headers, document.body))
    if value is None or not isinstance(value.get("client_id"), str) or not value["client_id"]:
        raise McpSignInError("Sign-in server returned an invalid client registration", code="registration_refused")
    secret = value.get("client_secret") if isinstance(value.get("client_secret"), str) else None
    granted = value.get("token_endpoint_auth_method")
    granted = granted if isinstance(granted, str) else ("client_secret_basic" if secret else "none")
    if granted not in ("none", "client_secret_basic", "client_secret_post"):
        raise McpSignInError("Sign-in server registered an unsupported client type", code="registration_refused")
    return ClientRegistration(server.issuer, value["client_id"], secret, granted, "dynamic")


def manual_client(server: AuthServer, *, client_id: str, client_secret: str | None) -> ClientRegistration:
    """A client the owner registered with the provider; bound to that issuer."""
    if not client_id.strip():
        raise McpSignInError("Client ID is required", code="invalid_client")
    if not client_secret:
        return ClientRegistration(server.issuer, client_id.strip(), None, "none", "manual")
    method = "client_secret_post" if "client_secret_basic" not in server.token_auth_methods \
        and "client_secret_post" in server.token_auth_methods else "client_secret_basic"
    return ClientRegistration(server.issuer, client_id.strip(), client_secret, method, "manual")


def metadata_document_client(server: AuthServer, metadata_url: str | None) -> ClientRegistration | None:
    """A Client ID Metadata Document client, when Vault has one and the server accepts them."""
    if not metadata_url or not server.cimd_supported:
        return None
    parts = urlsplit(metadata_url)
    if parts.scheme != "https" or parts.path in ("", "/"):
        return None
    return ClientRegistration(server.issuer, metadata_url, None, "none", "metadata_document")


def authorization_url(plan: SignInPlan, client: ClientRegistration, *, redirect_uri: str,
                      state: str, code_challenge: str) -> str:
    query = {
        "response_type": "code", "client_id": client.client_id, "redirect_uri": redirect_uri,
        "state": state, "code_challenge": code_challenge, "code_challenge_method": "S256",
        "resource": plan.resource,
    }
    if plan.scope:
        query["scope"] = plan.scope
    endpoint = plan.server.authorization_endpoint
    return endpoint + ("&" if urlsplit(endpoint).query else "?") + urlencode(query)


def check_response_issuer(server: AuthServer, iss: str | None) -> None:
    """RFC 9207 2.4 as the MCP spec tabulates it: compare when present, reject when the server
    promised ``iss`` and it is missing. Plain string comparison, no normalisation."""
    if iss is not None:
        if iss != server.issuer:
            raise McpSignInError("The sign-in response came from a different server", code="issuer_mismatch")
    elif server.iss_parameter_supported:
        raise McpSignInError("The sign-in response is missing its issuer", code="issuer_missing")


def _client_auth(client: ClientRegistration, form: dict[str, str]) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if client.token_endpoint_auth_method == "client_secret_basic" and client.client_secret:
        from urllib.parse import quote
        pair = f"{quote(client.client_id, safe='')}:{quote(client.client_secret, safe='')}"
        headers["Authorization"] = "Basic " + base64.b64encode(pair.encode()).decode()
    elif client.token_endpoint_auth_method == "client_secret_post" and client.client_secret:
        form["client_id"] = client.client_id
        form["client_secret"] = client.client_secret
    else:
        form["client_id"] = client.client_id
    return headers


def _token_request(server: AuthServer, client: ClientRegistration, form: dict[str, str], *, resource: str,
                   fetch: Fetcher, clock: Callable[[], float], previous: TokenSet | None = None) -> TokenSet:
    headers = _client_auth(client, form)
    document = fetch(server.token_endpoint, method="POST", headers=headers, form=form)
    value = None
    try:
        value = json.loads(document.body) if document.body else None
    except (ValueError, UnicodeDecodeError):
        value = None
    if document.status != 200 or not isinstance(value, dict):
        error = value.get("error") if isinstance(value, dict) else None
        reason = error if isinstance(error, str) and _ERROR_CODE.fullmatch(error) else f"HTTP {document.status}"
        raise McpSignInError(f"Sign-in server refused the token request ({reason})",
                             code="invalid_grant" if reason == "invalid_grant" else "token_refused")
    token = value.get("access_token")
    kind = value.get("token_type")
    if not isinstance(token, str) or not token or not isinstance(kind, str) or kind.lower() != "bearer":
        raise McpSignInError("Sign-in server returned an unusable token", code="token_refused")
    expires_in = value.get("expires_in")
    try:
        expires_at = clock() + float(expires_in) if expires_in is not None else None
    except (TypeError, ValueError):
        expires_at = None
    refresh = value.get("refresh_token")
    scope = value.get("scope")
    return TokenSet(
        access_token=token, token_type="Bearer", resource=resource, issuer=server.issuer,
        client_id=client.client_id, token_endpoint=server.token_endpoint,
        revocation_endpoint=server.revocation_endpoint,
        # A server that does not rotate keeps the previous refresh token valid.
        refresh_token=refresh if isinstance(refresh, str) and refresh else (previous.refresh_token if previous else None),
        expires_at=expires_at,
        scope=scope if isinstance(scope, str) else (previous.scope if previous else form.get("scope")),
        obtained_at=clock(),
    )


def exchange_code(plan: SignInPlan, client: ClientRegistration, *, code: str, code_verifier: str,
                  redirect_uri: str, fetch: Fetcher = mcp_http.fetch,
                  clock: Callable[[], float] = time.time) -> TokenSet:
    form = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
            "code_verifier": code_verifier, "resource": plan.resource}
    if plan.scope:
        form["scope"] = plan.scope
    return _token_request(plan.server, client, form, resource=plan.resource, fetch=fetch, clock=clock)


def refresh(token: TokenSet, client: ClientRegistration, *, fetch: Fetcher = mcp_http.fetch,
            clock: Callable[[], float] = time.time) -> TokenSet:
    if not token.refresh_token:
        raise McpSignInError("This sign-in cannot be renewed; sign in again", code="reconnect_required")
    server = AuthServer(token.issuer, "", token.token_endpoint, revocation_endpoint=token.revocation_endpoint)
    form = {"grant_type": "refresh_token", "refresh_token": token.refresh_token, "resource": token.resource}
    if token.scope:
        form["scope"] = token.scope
    return _token_request(server, client, form, resource=token.resource, fetch=fetch, clock=clock, previous=token)


def revoke(token: TokenSet, client: ClientRegistration, *, fetch: Fetcher = mcp_http.fetch) -> bool:
    """Best effort (RFC 7009): the refresh token first, since revoking it ends the grant."""
    if not token.revocation_endpoint:
        return False
    done = False
    for value, hint in ((token.refresh_token, "refresh_token"), (token.access_token, "access_token")):
        if not value:
            continue
        form = {"token": value, "token_type_hint": hint}
        try:
            document = fetch(token.revocation_endpoint, method="POST", headers=_client_auth(client, form), form=form)
            done = done or document.status == 200
        except mcp_http.McpTransportError:
            pass
    return done
