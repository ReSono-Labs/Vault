"""Who signs in to an MCP connection: personal credentials by default, shared accounts on purpose.

Decision record 2026-11-20 ("Authorization and accounts"):
- every credential for a remote MCP connection belongs to one person (pasted headers or an
  OAuth sign-in) and is used only for that person's calls;
- the device owner can mark their own credential as the connection's shared account; it is
  labelled shared and is used only for people the owner granted it to;
- when a person has neither, the call is refused with "sign in"; Vault never falls back to
  another person's account;
- an OAuth token is sent only to the server it was issued for.

Hosted MCP packages keep their service secret in ``ExtensionSecretStore``: that token belongs
to the package's own local process, not to anyone's external account.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import secrets as token_bytes
from threading import Lock
import time
from typing import Any, Callable
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.security.outbound import _is_extension_local_name
from app.vault_runtime.extensions import mcp_http, mcp_oauth
from app.vault_runtime.extensions.mcp_rules import connection_executable, validate_headers
from app.vault_runtime.extensions.repository import ExtensionNotFoundError, ExtensionRepository
from app.vault_runtime.extensions.secrets import ExtensionSecretError, LocalMasterKey

CALLBACK_PATH = "/extensions/oauth/callback"
_PENDING_SECONDS = 600
_MAX_PENDING_PER_USER = 5


class McpSignInRequired(mcp_http.McpAuthError):
    """The person has no usable credential for this connection; their message says what to do."""


@dataclass(slots=True)
class _Pending:
    user_id: str
    workspace_id: str
    extension_id: str
    plan: mcp_oauth.SignInPlan
    client: mcp_oauth.ClientRegistration
    verifier: str
    redirect_uri: str
    expires_at: float


@dataclass(frozen=True, slots=True)
class _Credential:
    owner_user_id: str
    kind: str
    shared: bool
    value: dict[str, Any]


def _is_local(address: str) -> bool:
    return _is_extension_local_name(urlsplit(address).hostname or "")


def is_hosted(configuration: dict[str, object]) -> bool:
    return configuration.get("packageType") == "hosted"


def validate_redirect_uri(redirect_uri: str) -> str:
    parts = urlsplit(redirect_uri)
    local = (parts.hostname or "") in {"localhost", "127.0.0.1", "::1"}
    if parts.path != CALLBACK_PATH or parts.query or parts.fragment or not parts.hostname \
            or not (parts.scheme == "https" or (parts.scheme == "http" and local)):
        raise ValueError("Sign-in return address is invalid.")
    return redirect_uri


class McpAccounts:
    def __init__(
        self, *, repository: ExtensionRepository, master_key: LocalMasterKey,
        fetch: Callable[..., mcp_http.FetchedDocument] = mcp_http.fetch,
        clock: Callable[[], float] = time.time,
        client_metadata_url: str | None = None, client_name: str = "ReSono Labs Vault",
    ) -> None:
        self._repository, self._key = repository, master_key
        self._fetch, self._clock = fetch, clock
        self._metadata_url, self._client_name = client_metadata_url, client_name
        self._pending: dict[str, _Pending] = {}
        self._scope_hints: dict[tuple[str, str], str] = {}   # (extension, user) -> challenged scopes
        self._lock = Lock()
        self._refresh_locks: dict[tuple[str, str], Lock] = {}

    def _fetch_for(self, address: str) -> Callable[..., mcp_http.FetchedDocument]:
        """Requests for sign-in on behalf of a connection. When the MCP server is remote,
        every address it hands out (metadata, sign-in server) must be remote too."""
        local = _is_local(address)
        return lambda url, **kwargs: self._fetch(url, allow_local=local, **kwargs)

    # ---- sealing -------------------------------------------------------------------------
    def _seal(self, aad: str, value: dict[str, Any]) -> tuple[bytes, bytes]:
        nonce = os.urandom(12)
        plaintext = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        return nonce, AESGCM(self._key.load_or_create()).encrypt(nonce, plaintext, aad.encode())

    def _open(self, aad: str, nonce: Any, ciphertext: Any) -> dict[str, Any]:
        try:
            value = json.loads(AESGCM(self._key.load_or_create()).decrypt(bytes(nonce), bytes(ciphertext), aad.encode()))
        except Exception as exc:
            raise ExtensionSecretError("stored MCP credential cannot be decrypted") from exc
        if not isinstance(value, dict):
            raise ExtensionSecretError("stored MCP credential is invalid")
        return value

    @staticmethod
    def _aad(extension_id: str, user_id: str, kind: str) -> str:
        return f"mcp-credential:v2:{extension_id}:{user_id}:{kind}"

    # ---- scope -----------------------------------------------------------------------------
    def _connection(self, cursor: Any, *, user_id: str, workspace_id: str, extension_id: str,
                    owner: bool = False, enabled: bool = True) -> dict[str, Any]:
        self._repository._require_scope(cursor, user_id=user_id, workspace_id=workspace_id, owner=owner)
        cursor.execute(
            """SELECT configuration_json, state FROM vault_private.vault_extensions
               WHERE extension_id=%s AND installed_in_workspace_id=%s AND kind='mcp' AND state <> 'removed'""",
            (extension_id, workspace_id),
        )
        row = cursor.fetchone()
        if row is None or (enabled and row[1] != "enabled"):
            raise ExtensionNotFoundError("MCP connection is unavailable")
        configuration = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
        if is_hosted(configuration):
            raise ValueError("Hosted MCP packages are configured in their settings, not with personal sign-in.")
        return configuration

    def _store(self, cursor: Any, *, extension_id: str, user_id: str, kind: str, value: dict[str, Any]) -> None:
        nonce, ciphertext = self._seal(self._aad(extension_id, user_id, kind), value)
        cursor.execute(
            """INSERT INTO vault_private.vault_extension_credentials
                 (extension_id,user_id,credential_kind,nonce,ciphertext)
               VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (extension_id,user_id) DO UPDATE SET credential_kind=EXCLUDED.credential_kind,
                 nonce=EXCLUDED.nonce, ciphertext=EXCLUDED.ciphertext, updated_at=now()""",
            (extension_id, user_id, kind, nonce, ciphertext),
        )

    def _credential_for(self, cursor: Any, *, extension_id: str, user_id: str) -> _Credential | None:
        """The person's own credential, else the shared account if they were granted it."""
        cursor.execute(
            """SELECT user_id, credential_kind, shared, nonce, ciphertext
               FROM vault_private.vault_extension_credentials
               WHERE extension_id=%s AND (user_id=%s OR (shared AND EXISTS (
                 SELECT 1 FROM vault_private.vault_extension_credential_grants g
                 WHERE g.extension_id=%s AND g.user_id=%s)))
               ORDER BY (user_id=%s) DESC LIMIT 1""",
            (extension_id, user_id, extension_id, user_id, user_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return _Credential(row[0], row[1], bool(row[2]), self._open(self._aad(extension_id, row[0], row[1]), row[3], row[4]))

    # ---- personal headers ------------------------------------------------------------------
    def set_personal_headers(self, *, user_id: str, workspace_id: str, extension_id: str,
                             headers: dict[str, str]) -> None:
        if not headers or any(not value for value in headers.values()):
            raise ValueError("credential headers must map names to non-empty values")
        validate_headers(headers, allow_credentials=True, label="credential header")
        with self._repository._connect() as connection, connection.cursor() as cursor:
            self._connection(cursor, user_id=user_id, workspace_id=workspace_id, extension_id=extension_id,
                             enabled=False)
            existing = self._credential_for(cursor, extension_id=extension_id, user_id=user_id)
            merged = dict(existing.value) if existing and existing.kind == "headers" \
                and existing.owner_user_id == user_id else {}
            merged = mcp_http.merge_headers(merged, headers)
            self._store(cursor, extension_id=extension_id, user_id=user_id, kind="headers", value=merged)

    # ---- resolution at use -----------------------------------------------------------------
    def headers_for(self, *, user_id: str, workspace_id: str, extension_id: str,
                    endpoint: str) -> tuple[tuple[str, str], ...]:
        with self._repository._connect() as connection, connection.cursor() as cursor:
            self._connection(cursor, user_id=user_id, workspace_id=workspace_id, extension_id=extension_id)
            credential = self._credential_for(cursor, extension_id=extension_id, user_id=user_id)
        if credential is None:
            return ()
        if credential.kind == "headers":
            return tuple(sorted((str(k), str(v)) for k, v in credential.value.items()))
        token = mcp_oauth.TokenSet.from_json(credential.value)
        if not mcp_oauth._resource_covers(token.resource, endpoint):
            # The connection now points somewhere else: never send this token there.
            raise McpSignInRequired("This connection's address changed since you signed in. Sign in again.",
                                    status=401)
        if token.expires_soon(self._clock()):
            token = self._refresh(extension_id=extension_id, owner_user_id=credential.owner_user_id, token=token)
        return (("Authorization", f"Bearer {token.access_token}"),)

    def explain_rejection(self, *, user_id: str, workspace_id: str, extension_id: str, endpoint: str,
                          error: mcp_http.McpAuthError) -> str | None:
        """After the server refused a call: renew and return None (retry once), or a message."""
        if isinstance(error, McpSignInRequired):
            return str(error)
        params = mcp_oauth.parse_challenge(error.challenge)
        with self._repository._connect() as connection, connection.cursor() as cursor:
            self._connection(cursor, user_id=user_id, workspace_id=workspace_id, extension_id=extension_id)
            credential = self._credential_for(cursor, extension_id=extension_id, user_id=user_id)
        if error.status == 403 and params.get("error") == "insufficient_scope":
            if credential is not None and credential.shared and credential.owner_user_id != user_id:
                return "The shared account for this tool lacks a permission it needs. Ask the device owner to reconnect it."
            # Step-up: ask for what was granted before plus what this call needs.
            granted = mcp_oauth.TokenSet.from_json(credential.value).scope \
                if credential is not None and credential.kind == "oauth" else None
            with self._lock:
                key = (extension_id, user_id)
                self._scope_hints[key] = mcp_oauth.union_scopes(
                    mcp_oauth.union_scopes(self._scope_hints.get(key), granted), params.get("scope")) or ""
            return "This tool needs more permissions on your account. Sign in again to grant them."
        if credential is None:
            return "This tool needs you to sign in to its service first. Open the MCP server in Vault and choose Sign in."
        if credential.kind == "oauth" and error.status == 401:
            token = mcp_oauth.TokenSet.from_json(credential.value)
            if token.refresh_token and self._clock() - token.obtained_at > 5:
                try:
                    self._refresh(extension_id=extension_id, owner_user_id=credential.owner_user_id, token=token)
                    return None
                except mcp_http.McpAuthError as exc:
                    return str(exc)
        if credential.shared:
            return "The shared account for this tool was refused. Ask the device owner to reconnect it."
        return "The service refused your sign-in. Sign in to it again."

    def _refresh(self, *, extension_id: str, owner_user_id: str, token: mcp_oauth.TokenSet) -> mcp_oauth.TokenSet:
        with self._lock:
            lock = self._refresh_locks.setdefault((extension_id, owner_user_id), Lock())
        with lock:
            with self._repository._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """SELECT nonce, ciphertext FROM vault_private.vault_extension_credentials
                       WHERE extension_id=%s AND user_id=%s AND credential_kind='oauth' FOR UPDATE""",
                    (extension_id, owner_user_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise McpSignInRequired("Sign in to this service again.", status=401)
                current = mcp_oauth.TokenSet.from_json(
                    self._open(self._aad(extension_id, owner_user_id, "oauth"), row[0], row[1]))
                if current.access_token != token.access_token and not current.expires_soon(self._clock()):
                    return current        # another call already renewed it
                client = self._client_by_id(cursor, issuer=current.issuer, client_id=current.client_id,
                                            extension_id=extension_id)
                try:
                    renewed = mcp_oauth.refresh(current, client, fetch=self._fetch_for(current.resource),
                                                clock=self._clock)
                except mcp_oauth.McpSignInError as exc:
                    raise McpSignInRequired("Your sign-in to this service expired. Sign in again.",
                                            status=401) from exc
                except mcp_http.McpTransportError as exc:
                    raise McpSignInRequired("Vault could not renew your sign-in right now. Try again shortly.",
                                            status=401) from exc
                self._store(cursor, extension_id=extension_id, user_id=owner_user_id, kind="oauth",
                            value=renewed.to_json())
                return renewed

    # ---- clients ---------------------------------------------------------------------------
    def _client_rows(self, cursor: Any, key: str) -> mcp_oauth.ClientRegistration | None:
        cursor.execute("SELECT nonce, ciphertext FROM vault_private.vault_mcp_oauth_clients WHERE client_key=%s", (key,))
        row = cursor.fetchone()
        if row is None:
            return None
        value = self._open(f"mcp-oauth-client:v1:{key}", row[0], row[1])
        return mcp_oauth.ClientRegistration(**value)

    def _save_client(self, cursor: Any, key: str, client: mcp_oauth.ClientRegistration) -> None:
        nonce, ciphertext = self._seal(f"mcp-oauth-client:v1:{key}", {
            "issuer": client.issuer, "client_id": client.client_id, "client_secret": client.client_secret,
            "token_endpoint_auth_method": client.token_endpoint_auth_method, "source": client.source,
        })
        cursor.execute(
            """INSERT INTO vault_private.vault_mcp_oauth_clients (client_key, issuer, nonce, ciphertext)
               VALUES (%s,%s,%s,%s) ON CONFLICT (client_key) DO UPDATE SET issuer=EXCLUDED.issuer,
               nonce=EXCLUDED.nonce, ciphertext=EXCLUDED.ciphertext, updated_at=now()""",
            (key, client.issuer, nonce, ciphertext),
        )

    @staticmethod
    def _manual_key(extension_id: str, issuer: str) -> str:
        return f"manual\n{extension_id}\n{issuer}"

    @staticmethod
    def _dynamic_key(issuer: str, redirect_uri: str) -> str:
        return f"dynamic\n{issuer}\n{redirect_uri}"

    def _client_by_id(self, cursor: Any, *, issuer: str, client_id: str, extension_id: str) -> mcp_oauth.ClientRegistration:
        manual = self._client_rows(cursor, self._manual_key(extension_id, issuer))
        if manual is not None and manual.client_id == client_id:
            return manual
        if self._metadata_url and client_id == self._metadata_url:
            return mcp_oauth.ClientRegistration(issuer, client_id, None, "none", "metadata_document")
        cursor.execute("SELECT client_key FROM vault_private.vault_mcp_oauth_clients WHERE issuer=%s", (issuer,))
        for (key,) in cursor.fetchall():
            client = self._client_rows(cursor, key)
            if client is not None and client.client_id == client_id and client.issuer == issuer:
                return client
        # The registration that issued this token is gone; a public client needs only its id.
        return mcp_oauth.ClientRegistration(issuer, client_id, None, "none", "dynamic")

    def _client_for(self, cursor: Any, *, plan: mcp_oauth.SignInPlan, extension_id: str,
                    redirect_uri: str, fetch: Callable[..., mcp_http.FetchedDocument]) -> mcp_oauth.ClientRegistration:
        issuer = plan.server.issuer
        manual = self._client_rows(cursor, self._manual_key(extension_id, issuer))
        if manual is not None:
            return manual
        document = mcp_oauth.metadata_document_client(plan.server, self._metadata_url)
        if document is not None:
            return document
        key = self._dynamic_key(issuer, redirect_uri)
        cached = self._client_rows(cursor, key)
        if cached is not None and cached.issuer == issuer:
            return cached
        client = mcp_oauth.register_client(plan.server, redirect_uri=redirect_uri, client_name=self._client_name,
                                           fetch=fetch)
        self._save_client(cursor, key, client)
        return client

    def set_manual_client(self, *, actor_user_id: str, workspace_id: str, extension_id: str,
                          client_id: str, client_secret: str | None) -> dict[str, str]:
        """Owner enters a client registered with the provider; bound to the issuer found now."""
        with self._repository._connect() as connection, connection.cursor() as cursor:
            configuration = self._connection(cursor, user_id=actor_user_id, workspace_id=workspace_id,
                                             extension_id=extension_id, owner=True)
        plan = self._plan(configuration, extension_id=extension_id, user_id=actor_user_id)
        client = mcp_oauth.manual_client(plan.server, client_id=client_id, client_secret=client_secret or None)
        with self._repository._connect() as connection, connection.cursor() as cursor:
            self._save_client(cursor, self._manual_key(extension_id, plan.server.issuer), client)
        return {"issuer": plan.server.issuer}

    # ---- sign-in ---------------------------------------------------------------------------
    @staticmethod
    def _endpoint(configuration: dict[str, object]) -> str:
        endpoint = configuration.get("endpoint") or configuration.get("url")
        if not isinstance(endpoint, str) or not connection_executable(configuration):
            raise ValueError("This MCP connection cannot be signed in to.")
        return endpoint

    def _plan(self, configuration: dict[str, object], *, extension_id: str, user_id: str) -> mcp_oauth.SignInPlan:
        endpoint = self._endpoint(configuration)
        challenge = None
        try:
            # The owner chose this address, so a local MCP server may be probed.
            probe = self._fetch(endpoint, method="POST", require_https=False, headers={
                "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2026-07-28",
                "Mcp-Method": "server/discover",
            }, json_body={"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": {
                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientCapabilities": {}}}})
            if probe.status in (401, 403):
                challenge = probe.headers.get("www-authenticate")
        except mcp_http.McpTransportError as exc:
            raise mcp_oauth.McpSignInError("Vault could not reach this MCP server", code="unreachable") from exc
        with self._lock:
            hint = self._scope_hints.get((extension_id, user_id))
        try:
            return mcp_oauth.discover(endpoint, challenge, fetch=self._fetch_for(endpoint), previous_scope=hint)
        except mcp_oauth.McpSignInError as exc:
            if exc.code == "no_resource_metadata" and challenge is None:
                raise mcp_oauth.McpSignInError("This MCP server does not ask for sign-in.",
                                               code="not_required") from exc
            raise

    def start_sign_in(self, *, user_id: str, workspace_id: str, extension_id: str,
                      redirect_uri: str) -> dict[str, str]:
        validate_redirect_uri(redirect_uri)
        with self._repository._connect() as connection, connection.cursor() as cursor:
            configuration = self._connection(cursor, user_id=user_id, workspace_id=workspace_id,
                                             extension_id=extension_id)
        plan = self._plan(configuration, extension_id=extension_id, user_id=user_id)
        with self._repository._connect() as connection, connection.cursor() as cursor:
            client = self._client_for(cursor, plan=plan, extension_id=extension_id, redirect_uri=redirect_uri,
                                      fetch=self._fetch_for(plan.resource))
        verifier, challenge = mcp_oauth.pkce_pair()
        state = token_bytes.token_urlsafe(32)
        now = self._clock()
        with self._lock:
            for key in [key for key, item in self._pending.items() if item.expires_at <= now]:
                del self._pending[key]
            mine = sorted((item.expires_at, key) for key, item in self._pending.items() if item.user_id == user_id)
            for _expires, key in mine[:max(0, len(mine) - _MAX_PENDING_PER_USER + 1)]:
                del self._pending[key]
            self._pending[state] = _Pending(user_id, workspace_id, extension_id, plan, client, verifier,
                                            redirect_uri, now + _PENDING_SECONDS)
        return {"authorizationUrl": mcp_oauth.authorization_url(
            plan, client, redirect_uri=redirect_uri, state=state, code_challenge=challenge)}

    def complete_sign_in(self, *, user_id: str, state: str, code: str | None, iss: str | None,
                         error: str | None) -> str:
        """Finish the browser return. Returns the connection's extension id."""
        with self._lock:
            pending = self._pending.get(state)
            if pending is not None and pending.user_id == user_id:
                del self._pending[state]
            else:
                pending = None
        if pending is None or pending.expires_at <= self._clock():
            raise mcp_oauth.McpSignInError("This sign-in expired or was started by someone else. Start again.",
                                           code="sign_in_expired")
        # RFC 9207: check the issuer before acting on anything in the response, errors included.
        mcp_oauth.check_response_issuer(pending.plan.server, iss)
        if error:
            reason = error if mcp_oauth._ERROR_CODE.fullmatch(error) else "error"
            raise mcp_oauth.McpSignInError(f"Sign-in was not completed ({reason}).", code="sign_in_refused")
        if not code:
            raise mcp_oauth.McpSignInError("The sign-in response has no code.", code="sign_in_refused")
        token = mcp_oauth.exchange_code(pending.plan, pending.client, code=code, code_verifier=pending.verifier,
                                        redirect_uri=pending.redirect_uri, fetch=self._fetch_for(pending.plan.resource),
                                        clock=self._clock)
        with self._repository._connect() as connection, connection.cursor() as cursor:
            self._connection(cursor, user_id=user_id, workspace_id=pending.workspace_id,
                             extension_id=pending.extension_id)
            self._store(cursor, extension_id=pending.extension_id, user_id=user_id, kind="oauth",
                        value=token.to_json())
        with self._lock:
            self._scope_hints.pop((pending.extension_id, user_id), None)
        return pending.extension_id

    def disconnect(self, *, user_id: str, workspace_id: str, extension_id: str) -> None:
        with self._repository._connect() as connection, connection.cursor() as cursor:
            self._connection(cursor, user_id=user_id, workspace_id=workspace_id, extension_id=extension_id,
                             enabled=False)
            cursor.execute(
                """DELETE FROM vault_private.vault_extension_credentials WHERE extension_id=%s AND user_id=%s
                   RETURNING credential_kind, nonce, ciphertext""", (extension_id, user_id))
            row = cursor.fetchone()
            client = None
            token = None
            if row is not None and row[0] == "oauth":
                token = mcp_oauth.TokenSet.from_json(self._open(self._aad(extension_id, user_id, "oauth"), row[1], row[2]))
                client = self._client_by_id(cursor, issuer=token.issuer, client_id=token.client_id,
                                            extension_id=extension_id)
        if token is not None and client is not None:
            mcp_oauth.revoke(token, client, fetch=self._fetch_for(token.resource))

    # ---- sharing (device owner) ------------------------------------------------------------
    def set_shared(self, *, actor_user_id: str, workspace_id: str, extension_id: str, shared: bool) -> None:
        with self._repository._connect() as connection, connection.cursor() as cursor:
            self._connection(cursor, user_id=actor_user_id, workspace_id=workspace_id,
                             extension_id=extension_id, owner=True, enabled=False)
            cursor.execute(
                """UPDATE vault_private.vault_extension_credentials SET shared=%s, updated_at=now()
                   WHERE extension_id=%s AND user_id=%s""", (shared, extension_id, actor_user_id))
            if cursor.rowcount == 0:
                raise ValueError("Connect your own account first; only that account can be shared.")
            if not shared:
                cursor.execute("DELETE FROM vault_private.vault_extension_credential_grants WHERE extension_id=%s",
                               (extension_id,))

    def set_shared_grant(self, *, actor_user_id: str, workspace_id: str, extension_id: str,
                         target_user_id: str, granted: bool) -> None:
        with self._repository._connect() as connection, connection.cursor() as cursor:
            self._connection(cursor, user_id=actor_user_id, workspace_id=workspace_id,
                             extension_id=extension_id, owner=True, enabled=False)
            if not granted:
                cursor.execute("""DELETE FROM vault_private.vault_extension_credential_grants
                                  WHERE extension_id=%s AND user_id=%s""", (extension_id, target_user_id))
                return
            self._repository._require_scope(cursor, user_id=target_user_id, workspace_id=workspace_id)
            cursor.execute("""SELECT 1 FROM vault_private.vault_extension_credentials
                              WHERE extension_id=%s AND shared""", (extension_id,))
            if cursor.fetchone() is None:
                raise ValueError("This connection has no shared account.")
            cursor.execute(
                """INSERT INTO vault_private.vault_extension_credential_grants (extension_id,user_id,granted_by_user_id)
                   VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""", (extension_id, target_user_id, actor_user_id))

    def status(self, *, user_id: str, workspace_id: str, extension_id: str) -> dict[str, object]:
        """What this person's calls will use. Never includes secrets."""
        with self._repository._connect() as connection, connection.cursor() as cursor:
            self._connection(cursor, user_id=user_id, workspace_id=workspace_id, extension_id=extension_id,
                             enabled=False)
            cursor.execute(
                """SELECT user_id, credential_kind, shared, nonce, ciphertext, updated_at
                   FROM vault_private.vault_extension_credentials WHERE extension_id=%s
                   AND (user_id=%s OR shared)""", (extension_id, user_id))
            rows = cursor.fetchall()
            cursor.execute("""SELECT user_id FROM vault_private.vault_extension_credential_grants
                              WHERE extension_id=%s ORDER BY user_id""", (extension_id,))
            grants = [row[0] for row in cursor.fetchall()]
        mine = next((row for row in rows if row[0] == user_id), None)
        shared = next((row for row in rows if row[2]), None)
        result: dict[str, object] = {
            "account": "none", "kind": None, "expiresAt": None, "scope": None,
            "isSharedAccount": bool(mine and mine[2]),
            "sharedAccountAvailable": shared is not None and (shared[0] == user_id or user_id in grants),
        }
        if mine is not None:
            result.update(account="personal", kind=mine[1], updatedAt=mine[5].isoformat() if mine[5] else None)
            if mine[1] == "oauth":
                token = mcp_oauth.TokenSet.from_json(self._open(self._aad(extension_id, user_id, "oauth"), mine[3], mine[4]))
                result.update(expiresAt=token.expires_at, scope=token.scope, renewable=bool(token.refresh_token))
        elif result["sharedAccountAvailable"]:
            result.update(account="shared", kind=shared[1])
        if mine is not None and mine[2]:
            result["sharedWith"] = grants
        return result

    # ---- migration -------------------------------------------------------------------------
    def migrate_connection_headers(self) -> int:
        """Credentials stored per connection before personal accounts become the personal
        credential of the person who stored them. Hosted packages keep theirs."""
        moved = 0
        with self._repository._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT s.extension_id, e.installed_in_workspace_id, s.changed_by_user_id, s.nonce, s.ciphertext
                   FROM vault_private.vault_extension_secrets s
                   JOIN vault_private.vault_extensions e ON e.extension_id=s.extension_id
                   WHERE s.secret_name='headers' AND e.kind='mcp'
                     AND coalesce(e.configuration_json->>'packageType','') <> 'hosted'
                   FOR UPDATE OF s""")
            for extension_id, workspace_id, user_id, nonce, ciphertext in cursor.fetchall():
                try:
                    headers = json.loads(AESGCM(self._key.load_or_create()).decrypt(
                        bytes(nonce), bytes(ciphertext), f"{workspace_id}:{extension_id}:headers".encode()))
                except Exception:
                    continue          # unreadable: leave it where it is
                sealed_nonce, sealed = self._seal(self._aad(extension_id, user_id, "headers"), headers)
                cursor.execute(
                    """INSERT INTO vault_private.vault_extension_credentials
                         (extension_id,user_id,credential_kind,nonce,ciphertext)
                       VALUES (%s,%s,'headers',%s,%s) ON CONFLICT (extension_id,user_id) DO NOTHING""",
                    (extension_id, user_id, sealed_nonce, sealed))
                cursor.execute("""DELETE FROM vault_private.vault_extension_secrets
                                  WHERE extension_id=%s AND secret_name='headers'""", (extension_id,))
                moved += 1
        return moved
