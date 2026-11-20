import json
from pathlib import Path

import pytest

from app.vault_runtime.extensions.specification import (
    MCP_SCHEMA_ID, PLUGIN_SCHEMA_ID, PluginSpecificationError,
    parse_mcp_document, parse_plugin_manifest,
)


def test_pinned_plugin_manifest_and_mcp_document_parse(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin.json"
    plugin.write_text(json.dumps({"$schema": PLUGIN_SCHEMA_ID, "name": "local.demo", "version": "1.0.0", "description": "Demo"}), encoding="utf-8")
    assert parse_plugin_manifest(plugin).name == "local.demo"
    mcp = tmp_path / "mcp.json"
    mcp.write_text(json.dumps({"$schema": MCP_SCHEMA_ID, "mcpServers": {"demo": {"type": "streamable-http", "url": "https://example.test/mcp"}}}), encoding="utf-8")
    servers = parse_mcp_document(mcp)
    assert servers[0].name == "demo" and servers[0].validated.executable


def test_plugin_ignores_unknown_and_non_object_extensions_with_diagnostics(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin.json"
    plugin.write_text(json.dumps({
        "$schema": PLUGIN_SCHEMA_ID, "name": "demo", "agent": "ignored",
        "extensions": "ignored",
    }), encoding="utf-8")
    manifest = parse_plugin_manifest(plugin)
    assert manifest.name == "demo"
    assert manifest.diagnostics == (
        "plugin.json ignored unknown top-level field: agent",
        "plugin.json ignored non-object extensions field",
    )


def test_empty_mcp_document_is_valid_and_embedded_secret_is_rejected(tmp_path: Path) -> None:
    empty = tmp_path / "empty-mcp.json"
    empty.write_text(json.dumps({"$schema": MCP_SCHEMA_ID, "mcpServers": {}}), encoding="utf-8")
    assert parse_mcp_document(empty) == ()
    mcp = tmp_path / "mcp.json"
    mcp.write_text(json.dumps({"$schema": MCP_SCHEMA_ID, "mcpServers": {"demo": {"type": "streamable-http", "url": "https://example.test/mcp", "headers": {"Authorization": "secret"}}}}), encoding="utf-8")
    with pytest.raises(PluginSpecificationError, match="secret storage"):
        parse_mcp_document(mcp)


@pytest.mark.parametrize("foreign", ["string-value", 7, ["a"], None, {"nested": True}])
def test_foreign_extension_namespaces_are_ignored_without_checking_values(tmp_path: Path, foreign) -> None:
    plugin = tmp_path / "plugin.json"
    plugin.write_text(json.dumps({
        "$schema": PLUGIN_SCHEMA_ID, "name": "demo",
        "extensions": {"org.other.client": foreign, "com.resonolabs.vault": {"agents": ["voice"]}},
    }), encoding="utf-8")
    manifest = parse_plugin_manifest(plugin)
    assert manifest.diagnostics == ()
    assert manifest.vault_extension == {"agents": ["voice"]}


def test_vault_namespace_value_must_be_an_object(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin.json"
    plugin.write_text(json.dumps({
        "$schema": PLUGIN_SCHEMA_ID, "name": "demo", "extensions": {"com.resonolabs.vault": "nope"},
    }), encoding="utf-8")
    with pytest.raises(PluginSpecificationError, match="at extensions.com.resonolabs.vault"):
        parse_plugin_manifest(plugin)


def test_manifest_errors_name_the_version_and_the_failing_field(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin.json"
    future = "https://agent-plugins.org/schemas/9.0.0/plugin.schema.json"
    plugin.write_text(json.dumps({"$schema": future, "name": "demo"}), encoding="utf-8")
    with pytest.raises(PluginSpecificationError, match=f"unsupported Agent Plugins version {future}"):
        parse_plugin_manifest(plugin)
    plugin.write_text(json.dumps({"$schema": PLUGIN_SCHEMA_ID, "name": "has--double"}), encoding="utf-8")
    with pytest.raises(PluginSpecificationError, match="plugin.json at name is invalid"):
        parse_plugin_manifest(plugin)


def test_whole_mcp_document_skips_unsupported_transports_and_bad_names(tmp_path: Path) -> None:
    from app.vault_runtime.extensions.specification import parse_mcp_bytes, parse_mcp_value_partial

    document = {"$schema": MCP_SCHEMA_ID, "mcpServers": {
        "remote": {"type": "streamable-http", "url": "https://example.test/mcp"},
        "local-cli": {"type": "stdio", "command": "server"},
        "legacy": {"type": "sse", "url": "https://example.test/sse"},
    }}
    skipped: list[str] = []
    servers = parse_mcp_bytes(json.dumps(document).encode(), diagnostics=skipped)
    assert [item.name for item in servers] == ["remote"]
    assert skipped == [
        "mcp:local-cli: unsupported transport stdio; Vault connects only to streamable-http servers",
        "mcp:legacy: unsupported transport sse; Vault connects only to streamable-http servers",
    ]
    only_unsupported = {"$schema": MCP_SCHEMA_ID, "mcpServers": {"legacy": document["mcpServers"]["legacy"]}}
    with pytest.raises(PluginSpecificationError, match="no server Vault can connect to"):
        parse_mcp_bytes(json.dumps(only_unsupported).encode())
    partial = parse_mcp_value_partial({"$schema": MCP_SCHEMA_ID, "mcpServers": {
        **document["mcpServers"],
        "../escape": {"type": "streamable-http", "url": "https://example.test/a"},
        "a/b": {"type": "streamable-http", "url": "https://example.test/b"},
        "..": {"type": "streamable-http", "url": "https://example.test/c"},
    }})
    assert [item.name for item in partial.servers] == ["remote"]
    assert sum("one safe path segment" in item for item in partial.diagnostics) == 3
    assert sum("unsupported transport" in item for item in partial.diagnostics) == 2
    future = "https://agent-plugins.org/schemas/9.0.0/mcp.schema.json"
    with pytest.raises(PluginSpecificationError, match=f"unsupported Agent Plugins version {future}"):
        parse_mcp_value_partial({"$schema": future, "mcpServers": {}})


def test_kit_ships_the_pinned_mcp_schema_unchanged() -> None:
    from hashlib import sha256

    root = Path(__file__).resolve().parents[2]
    runtime = (root / "app/vault_runtime/extensions/standards/mcp.schema.json").read_bytes()
    kit = (root / "plugin-kit/schemas/mcp.schema.json").read_bytes()
    # agentplugins/agent-plugins-spec bd38355, schemas/1.0.0/mcp.schema.json.
    assert sha256(runtime).hexdigest() == "6539175bfcdf43085855183e86da40ea94b166547a72b47ae9a0a390516d3acb"
    assert kit == runtime
