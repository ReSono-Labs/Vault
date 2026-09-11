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
