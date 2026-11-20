"""Bounded Vault additions layered beside the Agent Plugins standard.

Vault package data lives in ``plugin.json`` under ``extensions["com.resonolabs.vault"]``,
with the files it names in the top-level ``com.resonolabs.vault/`` folder. The root
``vault.json`` is the legacy form, read only when the namespace is absent; the two are
never merged.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from app.core.security.json_schema import offline_validator

from app.vault_runtime.extensions.mcp_package_migration import (
    McpPackageMigrationError,
    McpPackageMigrationManifest,
    parse_migration_block,
)
from app.vault_runtime.extensions.plugin_package_contract import (
    LocalShareManifest,
    PluginLifecycleManifest,
    WorkspaceImportManifest,
    parse_lifecycle_block,
    parse_local_share_block,
    parse_workspace_import_block,
)
from app.vault_runtime.extensions.mcp_rules import is_reserved_header
from app.vault_runtime.extensions.specification import VAULT_NAMESPACE
from app.vault_runtime.system_agents.inventory import AgentKind


VAULT_SCHEMA_ID = "https://schemas.resonolabs.com/vault/plugin/v1.json"
CONFIG_SCHEMA_ID = "https://schemas.resonolabs.com/vault/plugin-config/v1.json"
_ROOT = Path(__file__).with_name("standards")
_MAX_BYTES = 256 * 1024


class VaultManifestError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VaultPluginManifest:
    minimum_version: str
    agents: frozenset[AgentKind]
    services: tuple[str, ...]
    configuration_file: str | None
    mcp_file: str | None
    migration: McpPackageMigrationManifest | None = None
    workspace_import: WorkspaceImportManifest | None = None
    local_share: LocalShareManifest | None = None
    lifecycle: PluginLifecycleManifest | None = None
    # "namespace" (plugin.json extensions) or "vault.json" (legacy root file).
    source: str = "vault.json"
    # Folder, relative to the package root, that holds the files this data names.
    data_directory: str = ""
    diagnostics: tuple[str, ...] = ()


def parse_vault_manifest(
    plugin_root: Path, *, namespace: dict[str, object] | None = None,
) -> tuple[VaultPluginManifest | None, dict[str, object] | None]:
    """Read Vault data from the namespace when present, else from the legacy vault.json."""
    legacy = plugin_root / "vault.json"
    if namespace is not None:
        if not isinstance(namespace, dict):
            raise VaultManifestError(f'plugin.json at extensions.{VAULT_NAMESPACE}: must be an object')
        value = dict(namespace)
        value.setdefault("$schema", VAULT_SCHEMA_ID)
        diagnostics = (
            (f"vault.json ignored: plugin.json extensions.{VAULT_NAMESPACE} takes precedence",)
            if legacy.exists() else ()
        )
        return _parse_manifest(
            plugin_root, value, label=f"plugin.json extensions.{VAULT_NAMESPACE}",
            source="namespace", data_directory=VAULT_NAMESPACE, diagnostics=diagnostics,
        )
    if not legacy.exists():
        return None, None
    return _parse_manifest(
        plugin_root, _read(legacy), label="vault.json", source="vault.json", data_directory="",
        diagnostics=(),
    )


def _parse_manifest(
    plugin_root: Path, value: dict[str, object], *, label: str, source: str,
    data_directory: str, diagnostics: tuple[str, ...],
) -> tuple[VaultPluginManifest, dict[str, object] | None]:
    _validate(value, "vault.schema.json", label)
    data_root = plugin_root / data_directory if data_directory else plugin_root
    migration = None
    workspace_import = None
    local_share = None
    lifecycle = None
    if "migration" in value:
        try:
            migration = parse_migration_block(value["migration"])
        except McpPackageMigrationError as exc:
            raise VaultManifestError(str(exc)) from exc
    if "workspaceImport" in value:
        try:
            workspace_import = parse_workspace_import_block(value["workspaceImport"])
        except McpPackageMigrationError as exc:
            raise VaultManifestError(str(exc)) from exc
    if "localShare" in value:
        try:
            local_share = parse_local_share_block(value["localShare"])
        except McpPackageMigrationError as exc:
            raise VaultManifestError(str(exc)) from exc
    if "lifecycle" in value:
        try:
            lifecycle = parse_lifecycle_block(value["lifecycle"])
        except McpPackageMigrationError as exc:
            raise VaultManifestError(str(exc)) from exc
    manifest = VaultPluginManifest(
        minimum_version=str(value["minimumVaultVersion"]),
        agents=frozenset(AgentKind(str(item)) for item in value["agents"]),
        services=tuple(str(item) for item in value.get("services", [])),
        configuration_file=str(value["configuration"]) if "configuration" in value else None,
        mcp_file=str(value["mcp"]) if "mcp" in value else None,
        migration=migration,
        workspace_import=workspace_import,
        local_share=local_share,
        lifecycle=lifecycle,
        source=source,
        data_directory=data_directory,
        diagnostics=diagnostics,
    )
    configuration = None
    if manifest.configuration_file:
        configuration = _read(data_root / manifest.configuration_file)
        _validate(configuration, "config.schema.json", f"{data_directory + '/' if data_directory else ''}{manifest.configuration_file}")
        keys = [field["key"] for field in configuration["fields"]]
        if len(keys) != len(set(keys)):
            raise VaultManifestError("config.schema.json field keys must be unique")
        for field in configuration["fields"]:
            header = field.get("secretHeader") if isinstance(field, dict) else None
            if isinstance(header, str) and is_reserved_header(header):
                raise VaultManifestError(
                    f"config.schema.json field {field['key']}: secretHeader {header} is set by Vault"
                )
    if manifest.mcp_file and not (plugin_root / manifest.mcp_file).is_file():
        raise VaultManifestError(f"{label} declares mcp.json but the root mcp.json is missing")
    return manifest, configuration


def validate_settings(schema: dict[str, object], values: object) -> tuple[dict[str, object], dict[str, str]]:
    if not isinstance(values, dict):
        raise VaultManifestError("Plugin settings must be an object")
    fields = schema.get("fields")
    if not isinstance(fields, list):
        raise VaultManifestError("Plugin settings schema is invalid")
    clean: dict[str, object] = {}
    secrets: dict[str, str] = {}
    supplied = set(values)
    known = {str(field["key"]) for field in fields if isinstance(field, dict) and "key" in field}
    if supplied - known:
        raise VaultManifestError("Plugin settings contain an unknown field")
    for field in fields:
        assert isinstance(field, dict)
        key, kind = str(field["key"]), str(field["type"])
        value = values.get(key, field.get("default"))
        if value in (None, "", []) and bool(field.get("required")) and kind != "secret":
            raise VaultManifestError(f"{field['label']} is required")
        if value is None:
            continue
        if kind in {"text", "long_text", "url", "location", "secret"}:
            if not isinstance(value, str):
                raise VaultManifestError(f"{field['label']} must be text")
            if kind == "url" and value and not value.startswith(("https://", "http://127.0.0.1", "http://localhost")):
                raise VaultManifestError(f"{field['label']} must use HTTPS or a local address")
            if len(value) < int(field.get("minLength", 0)) or len(value) > int(field.get("maxLength", 100000)):
                raise VaultManifestError(f"{field['label']} has an invalid length")
        elif kind == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise VaultManifestError(f"{field['label']} must be a number")
            if "minimum" in field and value < field["minimum"] or "maximum" in field and value > field["maximum"]:
                raise VaultManifestError(f"{field['label']} is outside the allowed range")
        elif kind == "checkbox" and not isinstance(value, bool):
            raise VaultManifestError(f"{field['label']} must be on or off")
        elif kind in {"list", "multiple_choice"} and not isinstance(value, list):
            raise VaultManifestError(f"{field['label']} must be a list")
        if kind in {"choice", "multiple_choice"}:
            allowed = {item["value"] for item in field.get("choices", [])}
            selected = value if isinstance(value, list) else [value]
            if any(item not in allowed for item in selected):
                raise VaultManifestError(f"{field['label']} contains an unavailable choice")
        if kind == "secret":
            if value:
                secrets[str(field["secretHeader"])] = value
        else:
            clean[key] = value
    return clean, secrets


def _read(path: Path) -> dict[str, object]:
    try:
        if path.stat().st_size > _MAX_BYTES:
            raise VaultManifestError(f"{path.name} exceeds the size limit")
        value = json.loads(path.read_text(encoding="utf-8"))
    except VaultManifestError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VaultManifestError(f"{path.name} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise VaultManifestError(f"{path.name} must be a JSON object")
    return value


def _validate(value: dict[str, object], filename: str, label: str) -> None:
    schema = json.loads((_ROOT / filename).read_text(encoding="utf-8"))
    errors = sorted(offline_validator(schema).iter_errors(value), key=lambda item: list(item.path))
    if errors:
        location = ".".join(str(item) for item in errors[0].path)
        raise VaultManifestError(f"{label}{' at ' + location if location else ''}: {errors[0].message}")
