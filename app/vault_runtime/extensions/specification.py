"""Exact Agent Plugins 1.0.0 validation adapted from R1 plugins/specification.py."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from app.core.security.json_schema import offline_validator

from app.vault_runtime.extensions.mcp_config import McpConfiguration, validate_mcp_configuration
from app.vault_runtime.extensions.mcp_rules import server_name_problem, transport_problem


PLUGIN_SCHEMA_ID = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA_ID = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
_SCHEMA_ROOT = Path(__file__).with_name("standards")
MAX_MANIFEST_BYTES = 256 * 1024
# The one client-extension namespace Vault implements; vault_manifest reads its value.
VAULT_NAMESPACE = "com.resonolabs.vault"


class PluginSpecificationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PluginManifest:
    name: str
    version: str | None
    description: str | None
    diagnostics: tuple[str, ...] = ()
    # plugin.json extensions["com.resonolabs.vault"], checked with Vault's rules later.
    vault_extension: dict[str, object] | None = None


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
    if isinstance(value.get("extensions"), dict):
        # §8.1: namespaces Vault does not implement are ignored without checking their values.
        value["extensions"] = {
            key: item for key, item in value["extensions"].items() if key == VAULT_NAMESPACE
        }
    declared = value.get("$schema")
    if declared != PLUGIN_SCHEMA_ID:
        if isinstance(declared, str):
            raise PluginSpecificationError(f"unsupported Agent Plugins version {declared}")
        raise PluginSpecificationError("plugin.json at $schema: the Agent Plugins schema id is required")
    _validate(value, _schema("plugin.schema.json"), "plugin.json")
    extensions = value.get("extensions")
    return PluginManifest(
        str(value["name"]), value.get("version"), value.get("description"),
        tuple(diagnostics),
        extensions.get(VAULT_NAMESPACE) if isinstance(extensions, dict) else None,
    )


def parse_mcp_document(source: Path) -> tuple[McpServer, ...]:
    value = _read_object(source, "mcp.json")
    return parse_mcp_value(value)


def parse_mcp_document_partial(source: Path) -> McpDocument:
    value = _read_object(source, "mcp.json")
    return parse_mcp_value_partial(value)


def parse_mcp_bytes(payload: bytes, *, diagnostics: list[str] | None = None) -> tuple[McpServer, ...]:
    if not payload or len(payload) > MAX_MANIFEST_BYTES:
        raise PluginSpecificationError("mcp.json upload is invalid")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PluginSpecificationError("mcp.json must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PluginSpecificationError("mcp.json must be a JSON object")
    return parse_mcp_value(value, diagnostics=diagnostics)


def parse_mcp_value(value: dict[str, object], *, diagnostics: list[str] | None = None) -> tuple[McpServer, ...]:
    """A whole mcp.json import: any invalid server rejects it, unsupported ones are skipped.

    Skipped servers are reported in ``diagnostics``. If nothing usable remains, the
    import is rejected with those reasons.
    """
    _validate(value, _schema("mcp.schema.json"), "mcp.json")
    servers = value["mcpServers"]
    assert isinstance(servers, dict)
    result: list[McpServer] = []
    skipped: list[str] = []
    for name, configuration in servers.items():
        problem = server_name_problem(name)
        if problem is not None or not isinstance(configuration, dict):
            raise PluginSpecificationError(f"mcp.json server identity is invalid: {problem or 'not an object'}")
        unsupported = transport_problem(configuration)
        if unsupported is not None:
            skipped.append(f"mcp:{name}: {unsupported}")
            continue
        try:
            validated = validate_mcp_configuration(configuration)
        except ValueError as exc:
            raise PluginSpecificationError(f"MCP server {name} is invalid: {exc}") from exc
        result.append(McpServer(name, configuration, validated))
    if skipped and not result:
        raise PluginSpecificationError("mcp.json has no server Vault can connect to: " + "; ".join(skipped))
    if diagnostics is not None:
        diagnostics.extend(skipped)
    return tuple(result)


def parse_mcp_value_partial(value: dict[str, object]) -> McpDocument:
    schema = _schema("mcp.schema.json")
    if set(value) - {"$schema", "mcpServers"}:
        raise PluginSpecificationError("mcp.json contains unknown top-level fields")
    declared = value.get("$schema")
    if declared != MCP_SCHEMA_ID:
        raise PluginSpecificationError(
            f"unsupported Agent Plugins version {declared}" if isinstance(declared, str)
            else "mcp.json at $schema: the Agent Plugins schema id is required"
        )
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
            # Checked before anything derives a storage key, so one bad name cannot
            # abort or alias a healthy sibling.
            problem = server_name_problem(name)
            if problem is not None:
                raise PluginSpecificationError(problem)
            _validate(configuration, server_schema, f"mcp.json server {name}")
            assert isinstance(configuration, dict)
            unsupported = transport_problem(configuration)
            if unsupported is not None:
                raise PluginSpecificationError(unsupported)
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
    errors = sorted(offline_validator(schema).iter_errors(value), key=lambda item: list(item.path))
    if errors:
        location = ".".join(str(item) for item in errors[0].absolute_path)
        raise PluginSpecificationError(
            f"{label}{' at ' + location if location else ''} is invalid: {errors[0].message}"
        )
