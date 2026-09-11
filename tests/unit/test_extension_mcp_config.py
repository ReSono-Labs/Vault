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
