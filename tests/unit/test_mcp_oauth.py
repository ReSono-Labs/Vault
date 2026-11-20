import json

import pytest

from app.vault_runtime.extensions import mcp_http, mcp_oauth
from app.vault_runtime.extensions.mcp_accounts import validate_redirect_uri
from app.vault_runtime.extensions.mcp_oauth import McpSignInError


def _doc(status=200, value=None):
    return mcp_http.FetchedDocument(status, {}, json.dumps(value).encode() if value is not None else b"")


def _metadata(issuer="https://auth.example", **extra):
    return {"issuer": issuer, "authorization_endpoint": issuer + "/authorize", "token_endpoint": issuer + "/token",
            "code_challenge_methods_supported": ["S256"], **extra}


def test_challenge_parsing_handles_quotes_order_and_other_schemes() -> None:
    header = ('Basic realm="x", Bearer error="insufficient_scope", scope="files:read files:write", '
              'resource_metadata="https://mcp.example/.well-known/oauth-protected-resource"')
    assert mcp_oauth.parse_challenge(header) == {
        "error": "insufficient_scope", "scope": "files:read files:write",
        "resource_metadata": "https://mcp.example/.well-known/oauth-protected-resource"}
    assert mcp_oauth.parse_challenge('Bearer realm="a", Basic realm="b"') == {"realm": "a"}
    assert mcp_oauth.parse_challenge("Basic realm=x") == {}
    assert mcp_oauth.parse_challenge(None) == {}


def test_canonical_resource_and_discovery_url_order() -> None:
    assert mcp_oauth.canonical_resource("HTTPS://MCP.Example.com/") == "https://mcp.example.com"
    assert mcp_oauth.canonical_resource("https://mcp.example.com:8443/server/mcp#x") == "https://mcp.example.com:8443/server/mcp"
    assert mcp_oauth.protected_resource_metadata_urls("https://m.example/public/mcp", "https://m.example/prm") == [
        "https://m.example/prm",
        "https://m.example/.well-known/oauth-protected-resource/public/mcp",
        "https://m.example/.well-known/oauth-protected-resource"]
    assert mcp_oauth.authorization_server_metadata_urls("https://auth.example/tenant1") == [
        "https://auth.example/.well-known/oauth-authorization-server/tenant1",
        "https://auth.example/.well-known/openid-configuration/tenant1",
        "https://auth.example/tenant1/.well-known/openid-configuration"]
    assert mcp_oauth.authorization_server_metadata_urls("https://auth.example") == [
        "https://auth.example/.well-known/oauth-authorization-server",
        "https://auth.example/.well-known/openid-configuration"]


def test_discovery_falls_back_validates_resource_and_selects_scope() -> None:
    seen = []

    def fetch(url, **_):
        seen.append(url)
        if url == "https://m.example/.well-known/oauth-protected-resource":
            return _doc(value={"resource": "https://m.example", "authorization_servers": ["https://auth.example"],
                               "scopes_supported": ["a", "b"]})
        if url == "https://auth.example/.well-known/openid-configuration":
            return _doc(value=_metadata(scopes_supported=["a", "offline_access"]))
        return _doc(404)

    plan = mcp_oauth.discover("https://m.example/mcp", None, fetch=fetch)
    assert seen[:2] == ["https://m.example/.well-known/oauth-protected-resource/mcp",
                        "https://m.example/.well-known/oauth-protected-resource"]
    assert plan.resource == "https://m.example" and plan.scope == "a b offline_access"
    # The challenge's scope wins over scopes_supported.
    plan = mcp_oauth.discover("https://m.example/mcp", 'Bearer scope="only"', fetch=fetch)
    assert plan.scope == "only offline_access"

    def other_resource(url, **_):
        return _doc(value={"resource": "https://other.example/mcp", "authorization_servers": ["https://auth.example"]})

    with pytest.raises(McpSignInError, match="different server"):
        mcp_oauth.discover("https://m.example/mcp", None, fetch=other_resource)


def test_authorization_server_metadata_rules() -> None:
    with pytest.raises(McpSignInError, match="different issuer"):
        mcp_oauth.authorization_server("https://attacker.example",
                                       fetch=lambda url, **_: _doc(value=_metadata("https://honest.example")))
    no_pkce = _metadata()
    del no_pkce["code_challenge_methods_supported"]
    with pytest.raises(McpSignInError, match="PKCE"):
        mcp_oauth.authorization_server("https://auth.example", fetch=lambda url, **_: _doc(value=no_pkce))
    with pytest.raises(McpSignInError, match="HTTPS"):
        mcp_oauth.authorization_server("https://auth.example", fetch=lambda url, **_: _doc(
            value=_metadata(token_endpoint="http://auth.example/token")))
    # A root issuer with or without its trailing slash is the same issuer.
    server = mcp_oauth.authorization_server("https://auth.example/", fetch=lambda url, **_: _doc(value=_metadata()))
    assert server.issuer == "https://auth.example"


def test_authorization_response_issuer_table() -> None:
    promised = mcp_oauth.AuthServer("https://auth.example", "a", "t", iss_parameter_supported=True)
    silent = mcp_oauth.AuthServer("https://auth.example", "a", "t")
    mcp_oauth.check_response_issuer(promised, "https://auth.example")
    with pytest.raises(McpSignInError):
        mcp_oauth.check_response_issuer(promised, None)
    with pytest.raises(McpSignInError):
        mcp_oauth.check_response_issuer(silent, "https://auth.example/")     # no normalisation
    mcp_oauth.check_response_issuer(silent, None)


def test_tokens_are_refused_unless_bearer_and_errors_carry_no_secrets() -> None:
    server = mcp_oauth.AuthServer("https://auth.example", "https://auth.example/a", "https://auth.example/t")
    plan = mcp_oauth.SignInPlan("https://m.example/mcp", server, None)
    client = mcp_oauth.ClientRegistration(server.issuer, "c", "s3cret", "client_secret_basic")
    sent = []

    def fetch(url, **kwargs):
        sent.append(kwargs)
        return _doc(400, {"error": "invalid_grant", "error_description": "token rt-SECRET is bad"})

    with pytest.raises(McpSignInError) as refused:
        mcp_oauth.exchange_code(plan, client, code="code", code_verifier="v", redirect_uri="https://v/cb", fetch=fetch)
    assert "SECRET" not in str(refused.value) and "s3cret" not in str(refused.value)
    assert sent[0]["headers"]["Authorization"].startswith("Basic ") and "client_secret" not in sent[0]["form"]
    assert sent[0]["form"]["resource"] == "https://m.example/mcp"
    with pytest.raises(McpSignInError, match="unusable"):
        mcp_oauth.exchange_code(plan, client, code="c", code_verifier="v", redirect_uri="https://v/cb",
                                fetch=lambda url, **_: _doc(value={"access_token": "x", "token_type": "mac"}))


def test_sign_in_return_address_must_be_vaults_callback() -> None:
    assert validate_redirect_uri("https://192.168.1.5:8765/extensions/oauth/callback")
    assert validate_redirect_uri("http://127.0.0.1:8766/extensions/oauth/callback")
    for bad in ("http://192.168.1.5:8765/extensions/oauth/callback", "https://vault/other",
                "https://vault/extensions/oauth/callback?x=1", "javascript:alert(1)"):
        with pytest.raises(ValueError):
            validate_redirect_uri(bad)


def test_a_remote_servers_addresses_may_not_point_vault_at_this_machine() -> None:
    for url in ("http://127.0.0.1:8765/token", "https://localhost/token", "http://host.docker.internal/x"):
        with pytest.raises(mcp_http.McpTransportError, match="this machine"):
            mcp_http.fetch(url, allow_local=False)
    with pytest.raises(mcp_http.McpTransportError, match="HTTPS"):
        mcp_http.fetch("http://auth.example/token")
