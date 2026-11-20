"""Personal MCP sign-in, shared accounts and no borrowing, against real PostgreSQL and an
in-process protected MCP server with its own OAuth 2.1 authorization server."""
from __future__ import annotations

import os
from urllib.parse import parse_qs, urlsplit

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.extensions import mcp_client, mcp_legacy
from app.vault_runtime.extensions.mcp_accounts import McpAccounts
from app.vault_runtime.extensions.mcp_client import HttpMcpTransport, McpClient
from app.vault_runtime.extensions.mcp_lifecycle import McpLifecycle
from app.vault_runtime.extensions.mcp_oauth import McpSignInError
from app.vault_runtime.extensions.models import ExtensionKind
from app.vault_runtime.extensions.repository import ExtensionAuthorizationError, ExtensionRepository
from app.vault_runtime.extensions.secrets import ExtensionSecretStore, LocalMasterKey
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext
from tests.support.mcp_oauth_server import OAuthMcpServer

REDIRECT = "https://127.0.0.1:8765/extensions/oauth/callback"


@pytest.fixture()
def people(tmp_path):
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    identities = LocalIdentityService(repository=LocalIdentityRepository(database_url=database_url),
                                      setup_credential_hash=hash_token("setup"))
    identities.ensure_schema()
    owner = identities.bootstrap_owner(setup_credential="setup", username="owner", password="owner-password",
                                       display_name="Owner", experience_style="strict")
    users = {"owner": owner.principal.user_id}
    for name in ("member", "guest"):
        identities.create_user(actor=owner.principal, username=name, password=f"{name}-password",
                               display_name=name.title(), experience_style="funny")
        identities.add_member(principal=owner.principal, workspace_id=owner.principal.workspace_id, username=name)
        users[name] = identities.login(username=name, password=f"{name}-password").principal.user_id
    extensions = ExtensionRepository(database_url=database_url)
    extensions.ensure_schema()
    mcp_client._ERAS.clear()
    mcp_legacy._SESSIONS.clear()
    yield extensions, owner.principal.workspace_id, users, LocalMasterKey(tmp_path / "keys" / "credentials.key")
    mcp_client._ERAS.clear()
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")


def _connection(extensions, workspace, owner, endpoint):
    return extensions.install(
        actor_user_id=owner, workspace_id=workspace, kind=ExtensionKind.MCP, identity="crm",
        display_name="CRM", version=None, description="Protected CRM", content_hash="hash-crm",
        configuration={"endpoint": endpoint, "transport": "streamable-http"}, components=(),
    )


def _sign_in(accounts, server, *, user, workspace_id, extension_id, as_user=None):
    started = accounts.start_sign_in(user_id=user, workspace_id=workspace_id, extension_id=extension_id,
                                     redirect_uri=REDIRECT)
    returned = server.authorize(started["authorizationUrl"], user=as_user or user)
    return started, returned


def test_personal_sign_in_shared_account_and_no_borrowing(people) -> None:
    extensions, workspace, users, key = people
    clock = [1_000_000.0]
    accounts = McpAccounts(repository=extensions, master_key=key, clock=lambda: clock[0])
    with OAuthMcpServer() as server:
        connection = _connection(extensions, workspace, users["owner"], server.endpoint)
        scope = {"workspace_id": workspace, "extension_id": connection.extension_id}

        # The member signs in: PKCE S256, the resource indicator and the server's scope are sent.
        started, returned = _sign_in(accounts, server, user=users["member"], **scope)
        query = parse_qs(urlsplit(started["authorizationUrl"]).query)
        assert query["code_challenge_method"] == ["S256"] and query["resource"] == [server.endpoint]
        assert query["scope"] == ["tools:read offline_access"] and query["redirect_uri"] == [REDIRECT]
        # Someone else's session cannot finish the member's sign-in, and it stays usable for them.
        with pytest.raises(McpSignInError):
            accounts.complete_sign_in(user_id=users["guest"], state=returned["state"], code=returned["code"],
                                      iss=returned["iss"], error=None)
        # A response claiming a different issuer is refused before the code is used.
        with pytest.raises(McpSignInError, match="different server"):
            accounts.complete_sign_in(user_id=users["member"], state=returned["state"], code=returned["code"],
                                      iss="https://evil.example", error=None)
        assert server.token_requests == []
        started, returned = _sign_in(accounts, server, user=users["member"], **scope)
        accounts.complete_sign_in(user_id=users["member"], state=returned["state"], code=returned["code"],
                                  iss=returned["iss"], error=None)
        token_request = server.token_requests[-1]
        assert token_request["resource"] == server.endpoint and token_request["code_verifier"]

        member_headers = accounts.headers_for(user_id=users["member"], endpoint=server.endpoint, **scope)
        assert server.access[member_headers[0][1].removeprefix("Bearer ")]["user"] == users["member"]
        # Nobody else uses the member's account.
        assert accounts.headers_for(user_id=users["owner"], endpoint=server.endpoint, **scope) == ()
        assert accounts.headers_for(user_id=users["guest"], endpoint=server.endpoint, **scope) == ()
        assert accounts.status(user_id=users["guest"], **scope)["account"] == "none"

        # The owner signs in and shares their account with the guest only.
        _started, returned = _sign_in(accounts, server, user=users["owner"], **scope)
        accounts.complete_sign_in(user_id=users["owner"], state=returned["state"], code=returned["code"],
                                  iss=returned["iss"], error=None)
        with pytest.raises(ExtensionAuthorizationError):
            accounts.set_shared(actor_user_id=users["member"], shared=True, **scope)    # not the owner
        accounts.set_shared(actor_user_id=users["owner"], shared=True, **scope)
        assert accounts.headers_for(user_id=users["guest"], endpoint=server.endpoint, **scope) == ()  # no grant yet
        accounts.set_shared_grant(actor_user_id=users["owner"], target_user_id=users["guest"], granted=True, **scope)
        guest = accounts.headers_for(user_id=users["guest"], endpoint=server.endpoint, **scope)
        assert server.access[guest[0][1].removeprefix("Bearer ")]["user"] == users["owner"]
        assert accounts.status(user_id=users["guest"], **scope)["account"] == "shared"
        # The member keeps their own account even though a shared one exists.
        assert accounts.headers_for(user_id=users["member"], endpoint=server.endpoint, **scope) == member_headers
        accounts.set_shared_grant(actor_user_id=users["owner"], target_user_id=users["guest"], granted=False, **scope)
        assert accounts.headers_for(user_id=users["guest"], endpoint=server.endpoint, **scope) == ()

        # Near expiry the token is renewed with the resource indicator; the refresh token rotates.
        clock[0] += 3600
        renewed = accounts.headers_for(user_id=users["member"], endpoint=server.endpoint, **scope)
        assert renewed != member_headers and server.token_requests[-1]["grant_type"] == "refresh_token"
        assert server.token_requests[-1]["resource"] == server.endpoint
        # The token is never sent to a different server.
        with pytest.raises(Exception, match="address changed"):
            accounts.headers_for(user_id=users["member"], endpoint="http://127.0.0.1:1/other", **scope)

        # Disconnect revokes at the server and removes the credential.
        accounts.disconnect(user_id=users["member"], **scope)
        assert server.revoked and accounts.status(user_id=users["member"], **scope)["account"] == "none"


def test_tools_run_with_the_callers_own_account_through_the_catalog(people) -> None:
    extensions, workspace, users, key = people
    accounts = McpAccounts(repository=extensions, master_key=key)
    with OAuthMcpServer() as server:
        connection = _connection(extensions, workspace, users["owner"], server.endpoint)
        scope = {"workspace_id": workspace, "extension_id": connection.extension_id}

        def factory(record, context):
            return McpClient(HttpMcpTransport(record.configuration["endpoint"], credential_headers=accounts.headers_for(
                user_id=context.user_id, workspace_id=context.workspace_id, extension_id=record.extension_id,
                endpoint=record.configuration["endpoint"])))

        def refused(record, context, error):
            return accounts.explain_rejection(user_id=context.user_id, workspace_id=context.workspace_id,
                                              extension_id=record.extension_id,
                                              endpoint=record.configuration["endpoint"], error=error)

        extensions.set_safe_mode(actor_user_id=users["owner"], workspace_id=workspace, enabled=False)
        catalog = ToolCatalog(authorizer=lambda _d, _c: True)
        lifecycle = McpLifecycle(repository=extensions, catalog=catalog, client_factory=factory, auth_refused=refused)
        for name in ("owner", "member"):
            _started, returned = _sign_in(accounts, server, user=users[name], **scope)
            accounts.complete_sign_in(user_id=users[name], state=returned["state"], code=returned["code"],
                                      iss=returned["iss"], error=None)

        def context(name):
            return ToolInvocationContext(agent=AgentKind.VOICE, user_id=users[name], workspace_id=workspace,
                                         tool_call_id=f"call-{name}", local_session_id="session")

        lifecycle.discover(actor_user_id=users["owner"], workspace_id=workspace, connection=connection,
                           client=factory(connection, context("owner")))
        names = {}
        for name in ("owner", "member", "guest"):
            extensions.set_grant(actor_user_id=users["owner"], target_user_id=users[name], workspace_id=workspace,
                                 extension_id=connection.extension_id, agent=AgentKind.VOICE,
                                 capability_name="whoami", enabled=True, effect_class="read")
            names[name] = lifecycle.project_scope(user_id=users[name], workspace_id=workspace,
                                                  agent=AgentKind.VOICE, connection=connection)[0]
        assert catalog.invoke(names["member"], {}, context=context("member")).text == f"signed in as {users['member']}"
        assert catalog.invoke(names["owner"], {}, context=context("owner")).text == f"signed in as {users['owner']}"
        # A granted tool without an account is refused with a sign-in message; nothing runs.
        before = list(server.calls)
        guest = catalog.invoke(names["guest"], {}, context=context("guest"))
        assert guest.is_error and "sign in" in guest.text.lower() and server.calls == before
        # The server revokes the member's access token early: Vault renews once and the call goes through.
        member_token = accounts.headers_for(user_id=users["member"], endpoint=server.endpoint,
                                            **scope)[0][1].removeprefix("Bearer ")
        server.access.pop(member_token)
        import time
        time.sleep(5.1)          # refresh only tokens older than a few seconds (no renew loops)
        again = catalog.invoke(names["member"], {}, context=context("member"))
        assert not again.is_error and again.text == f"signed in as {users['member']}"
        # A scope challenge asks for a new sign-in and remembers the extra scope for it.
        server.required_scope = "tools:write"
        challenged = catalog.invoke(names["member"], {}, context=context("member"))
        assert challenged.is_error and "more permissions" in challenged.text
        started = accounts.start_sign_in(user_id=users["member"], redirect_uri=REDIRECT, **scope)
        # Previously granted scopes are kept alongside the new one (spec: step-up scope union).
        assert parse_qs(urlsplit(started["authorizationUrl"]).query)["scope"] == [
            "tools:read offline_access tools:write"]


def test_existing_connection_credentials_become_the_storers_own(people) -> None:
    extensions, workspace, users, key = people
    accounts = McpAccounts(repository=extensions, master_key=key)
    legacy = ExtensionSecretStore(repository=extensions, master_key=key)
    remote = _connection(extensions, workspace, users["owner"], "https://crm.example/mcp")
    hosted = extensions.install(
        actor_user_id=users["owner"], workspace_id=workspace, kind=ExtensionKind.MCP, identity="hosted",
        display_name="Hosted", version="1", description=None, content_hash="hash-hosted",
        configuration={"endpoint": "http://127.0.0.1:8790/mcp", "packageType": "hosted"}, components=(),
    )
    for record in (remote, hosted):
        legacy.set_headers(actor_user_id=users["owner"], workspace_id=workspace, extension_id=record.extension_id,
                           headers={"Authorization": "Bearer owner-token"})
    assert accounts.migrate_connection_headers() == 1
    assert accounts.migrate_connection_headers() == 0              # idempotent
    scope = {"workspace_id": workspace, "extension_id": remote.extension_id}
    assert accounts.headers_for(user_id=users["owner"], endpoint="https://crm.example/mcp", **scope) == (
        ("Authorization", "Bearer owner-token"),)
    assert accounts.headers_for(user_id=users["member"], endpoint="https://crm.example/mcp", **scope) == ()
    # The hosted package keeps its service secret where its process reads it.
    assert legacy.resolve_headers(user_id=users["owner"], workspace_id=workspace,
                                  extension_id=hosted.extension_id) == (("Authorization", "Bearer owner-token"),)


PEER_PATH = os.environ.get("VAULT_MCP_PEER_PATH", "")


@pytest.mark.skipif(not PEER_PATH, reason="VAULT_MCP_PEER_PATH (official MCP SDK) not set")
def test_sign_in_against_the_official_sdk_authorization_server(people) -> None:
    """Independent peer: the MCP Python SDK as protected server and OAuth authorization server."""
    import socket
    import subprocess
    import sys
    import time
    import urllib.error
    import urllib.request
    from pathlib import Path

    extensions, workspace, users, key = people
    accounts = McpAccounts(repository=extensions, master_key=key)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    peer = Path(__file__).parents[1] / "support" / "mcp_peer.py"
    process = subprocess.Popen([sys.executable, str(peer), "protected-server", str(port)],
                               env={**os.environ, "PYTHONPATH": PEER_PATH, "PYTHONDONTWRITEBYTECODE": "1"},
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(150):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.2)
        endpoint = f"http://127.0.0.1:{port}/mcp"
        connection = _connection(extensions, workspace, users["owner"], endpoint)
        scope = {"workspace_id": workspace, "extension_id": connection.extension_id}

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None

        def sign_in(user):
            started = accounts.start_sign_in(user_id=user, redirect_uri=REDIRECT, **scope)
            try:
                urllib.request.build_opener(NoRedirect).open(started["authorizationUrl"], timeout=10)
                raise AssertionError("no redirect")
            except urllib.error.HTTPError as redirect:
                assert redirect.code in (302, 303, 307), redirect.read()[:300]
                values = {k: v[0] for k, v in parse_qs(urlsplit(redirect.headers["Location"]).query).items()}
            accounts.complete_sign_in(user_id=user, state=values["state"], code=values.get("code"),
                                      iss=values.get("iss"), error=values.get("error"))

        def whoami(user):
            client = McpClient(HttpMcpTransport(endpoint, credential_headers=accounts.headers_for(
                user_id=user, endpoint=endpoint, **scope)))
            client.initialize()
            return client.call_tool("whoami", {})["content"][0]["text"]

        sign_in(users["member"])
        sign_in(users["owner"])
        member_says, owner_says = whoami(users["member"]), whoami(users["owner"])
        assert member_says.startswith("signed in as user-") and owner_says.startswith("signed in as user-")
        assert member_says != owner_says                      # each call used its own person's token
        with pytest.raises(Exception):
            whoami(users["guest"])                             # no account: the SDK refuses (401)
        accounts.disconnect(user_id=users["member"], **scope)
        assert accounts.status(user_id=users["member"], **scope)["account"] == "none"
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
