import pytest

from app.vault_runtime.extensions.mcp_config import McpConfigurationError, validate_mcp_configuration


def test_streamable_http_is_executable_and_remote_requires_https() -> None:
    local = validate_mcp_configuration({"type": "streamable-http", "url": "http://127.0.0.1:8123/mcp"})
    remote = validate_mcp_configuration({"type": "streamable-http", "url": "https://mcp.example.test/path"})
    assert local.executable and remote.executable
    docker_host = validate_mcp_configuration({
        "type": "streamable-http", "url": "http://host.docker.internal:8123/mcp",
    })
    assert docker_host.executable
    with pytest.raises(McpConfigurationError, match="HTTPS"):
        validate_mcp_configuration({"type": "streamable-http", "url": "http://example.test/mcp"})


@pytest.mark.parametrize("url", [
    "https://169.254.169.254/latest/meta-data",
    "https://10.0.0.8/mcp",
    "https://[fc00::1]/mcp",
])
def test_remote_mcp_rejects_private_and_metadata_literals(url: str) -> None:
    with pytest.raises(McpConfigurationError, match="local or private"):
        validate_mcp_configuration({"type": "streamable-http", "url": url})


@pytest.mark.parametrize("headers", [
    {"Authorization": "secret"}, {"Cookie": "secret"}, {"X-API-Key": "secret"},
])
def test_public_configuration_rejects_secret_headers(headers: dict[str, str]) -> None:
    with pytest.raises(McpConfigurationError, match="secret storage"):
        validate_mcp_configuration({"type": "streamable-http", "url": "https://example.test/mcp", "headers": headers})


def test_sse_and_stdio_validate_but_are_not_executable() -> None:
    assert not validate_mcp_configuration({"type": "sse", "url": "https://example.test/sse"}).executable
    assert not validate_mcp_configuration({"type": "stdio", "command": "server", "args": []}).executable


def test_rejects_url_credentials_fragments_and_reserved_environment() -> None:
    for url in ("https://u:p@example.test/mcp", "https://example.test/mcp#fragment"):
        with pytest.raises(McpConfigurationError):
            validate_mcp_configuration({"type": "streamable-http", "url": url})
    with pytest.raises(McpConfigurationError, match="reserved"):
        validate_mcp_configuration({"type": "stdio", "command": "server", "env": {"PLUGIN_ROOT": "x"}})


@pytest.mark.parametrize(("headers", "message"), [
    ({"X Tenant": "a"}, "not a valid HTTP field name"),
    ({"X-Tenant": "a\r\nInjected: yes"}, "line break"),
    ({"X-Tenant": "a\nb"}, "line break"),
    ({"X-Tenant": "a", "x-tenant": "b"}, "collide by case"),
    ({"accept": "text/plain"}, "set by Vault"),
    ({"Content-Type": "text/plain"}, "set by Vault"),
    ({"MCP-Protocol-Version": "1"}, "set by Vault"),
    ({"Mcp-Session-Id": "s"}, "set by Vault"),
    ({"x-vault-capability": "forged"}, "set by Vault"),
])
def test_public_headers_must_be_valid_fields_and_not_vault_generated(headers, message) -> None:
    with pytest.raises(McpConfigurationError, match=message):
        validate_mcp_configuration({"type": "streamable-http", "url": "https://example.test/mcp", "headers": headers})


def test_harmless_public_headers_are_kept_literally() -> None:
    config = validate_mcp_configuration({
        "type": "streamable-http", "url": "https://example.test/mcp", "headers": {"X-Tenant": "${PLUGIN_ROOT}"},
    })
    assert config.headers == (("X-Tenant", "${PLUGIN_ROOT}"),)


def test_header_rules_cover_credentials_and_merge_ignoring_case() -> None:
    from app.vault_runtime.extensions.mcp_rules import McpRuleError, merge_headers, validate_headers

    assert validate_headers({"Authorization": "Bearer t"}, allow_credentials=True) == {"Authorization": "Bearer t"}
    for headers in ({"X-Vault-Capability": "x"}, {"authorization": "a", "Authorization": "b"}, {"Bad Name": "x"}):
        with pytest.raises(McpRuleError):
            validate_headers(headers, allow_credentials=True)
    assert merge_headers({"authorization": "old", "X-A": "1"}, {"Authorization": "new"}) == {
        "Authorization": "new", "X-A": "1"}
