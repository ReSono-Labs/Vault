"""Exact Agent Plugins 1.0.0 validation adapted from R1 plugins/specification.py."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from app.vault_runtime.extensions.mcp_config import McpConfiguration, validate_mcp_configuration


PLUGIN_SCHEMA_ID = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA_ID = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
_SCHEMA_ROOT = Path(__file__).with_name("standards")
MAX_MANIFEST_BYTES = 256 * 1024


class PluginSpecificationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PluginManifest:
    name: str
    version: str | None
    description: str | None
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class McpServer:
    name: str
    configuration: dict[str, object]
    validated: McpConfiguration


@dataclass(frozen=True, slots=True)
class McpDocument:
    servers: tuple[McpServer, ...]
    diagnostics: tuple[str, ...] = ()


_PLUGIN_FIELDS = frozenset({
    "$schema", "name", "version", "description", "author", "homepage",
    "repository", "license", "keywords", "extensions",
})


def parse_plugin_manifest(source: Path) -> PluginManifest:
    value = _read_object(source, "plugin.json")
    diagnostics: list[str] = []
    for field in sorted(set(value) - _PLUGIN_FIELDS):
        diagnostics.append(f"plugin.json ignored unknown top-level field: {field}")
        value.pop(field)
    if "extensions" in value and not isinstance(value["extensions"], dict):
        diagnostics.append("plugin.json ignored non-object extensions field")
        value.pop("extensions")
    _validate(value, _schema("plugin.schema.json"), "plugin.json")
    return PluginManifest(
        str(value["name"]), value.get("version"), value.get("description"),
        tuple(diagnostics),
    )


def parse_mcp_document(source: Path) -> tuple[McpServer, ...]:
    value = _read_object(source, "mcp.json")
    return parse_mcp_value(value)


def parse_mcp_document_partial(source: Path) -> McpDocument:
    value = _read_object(source, "mcp.json")
    return parse_mcp_value_partial(value)


def parse_mcp_bytes(payload: bytes) -> tuple[McpServer, ...]:
    if not payload or len(payload) > MAX_MANIFEST_BYTES:
        raise PluginSpecificationError("mcp.json upload is invalid")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PluginSpecificationError("mcp.json must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PluginSpecificationError("mcp.json must be a JSON object")
    return parse_mcp_value(value)


def parse_mcp_value(value: dict[str, object]) -> tuple[McpServer, ...]:
    _validate(value, _schema("mcp.schema.json"), "mcp.json")
    servers = value["mcpServers"]
    assert isinstance(servers, dict)
    result: list[McpServer] = []
    for name, configuration in servers.items():
        if not isinstance(name, str) or not name or len(name) > 128 or not isinstance(configuration, dict):
            raise PluginSpecificationError("mcp.json server identity is invalid")
        try:
            validated = validate_mcp_configuration(configuration)
        except ValueError as exc:
            raise PluginSpecificationError(f"MCP server {name} is invalid: {exc}") from exc
        result.append(McpServer(name, configuration, validated))
    return tuple(result)


def parse_mcp_value_partial(value: dict[str, object]) -> McpDocument:
    schema = _schema("mcp.schema.json")
    if set(value) - {"$schema", "mcpServers"}:
        raise PluginSpecificationError("mcp.json contains unknown top-level fields")
    if value.get("$schema") != MCP_SCHEMA_ID:
        raise PluginSpecificationError("mcp.json declares an unsupported schema")
    servers = value.get("mcpServers")
    if not isinstance(servers, dict):
        raise PluginSpecificationError("mcp.json mcpServers must be an object")
    server_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **schema["$defs"]["server"],
        "$defs": schema["$defs"],
    }
    result: list[McpServer] = []
    diagnostics: list[str] = []
    for name, configuration in servers.items():
        try:
            if not isinstance(name, str) or not name or len(name) > 128:
                raise PluginSpecificationError("server identity is invalid")
            _validate(configuration, server_schema, f"mcp.json server {name}")
            assert isinstance(configuration, dict)
            validated = validate_mcp_configuration(configuration)
            result.append(McpServer(name, configuration, validated))
        except (PluginSpecificationError, ValueError) as exc:
            diagnostics.append(f"mcp:{name}: {exc}")
    return McpDocument(tuple(result), tuple(diagnostics))


def _read_object(source: Path, label: str) -> dict[str, object]:
    try:
        if source.stat().st_size > MAX_MANIFEST_BYTES:
            raise PluginSpecificationError(f"{label} exceeds the size limit")
        value = json.loads(source.read_text(encoding="utf-8"))
    except PluginSpecificationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PluginSpecificationError(f"{label} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PluginSpecificationError(f"{label} must be a JSON object")
    return value


def _schema(filename: str) -> dict[str, object]:
    value = json.loads((_SCHEMA_ROOT / filename).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("pinned Agent Plugins schema is invalid")
    return value


def _validate(value: object, schema: dict[str, object], label: str) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda item: list(item.path))
    if errors:
        raise PluginSpecificationError(f"{label} is invalid: {errors[0].message}")
