"""Primary manifest for hosted MCP packages imported into Vault."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from app.vault_runtime.extensions.vault_manifest import VaultManifestError, validate_settings
from app.vault_runtime.extensions.mcp_package_migration import (
    McpPackageMigrationError,
    McpPackageMigrationManifest,
    parse_migration_block,
)


MCP_PACKAGE_SCHEMA_ID = "https://schemas.resonolabs.com/vault/mcp-package/v1.json"
_ROOT = Path(__file__).with_name("standards")
_MAX_BYTES = 256 * 1024


class McpPackageManifestError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class McpRuntimeManifest:
    type: str
    command: tuple[str, ...]
    cwd: str
    port: int
    health_path: str
    mcp_path: str


@dataclass(frozen=True, slots=True)
class CompanionPluginManifest:
    directory: str
    remove_with_package: bool


@dataclass(frozen=True, slots=True)
class McpPackageManifest:
    name: str
    version: str
    description: str | None
    runtime: McpRuntimeManifest
    configuration_file: str | None
    companion_plugin: CompanionPluginManifest | None
    migration: McpPackageMigrationManifest | None


def parse_mcp_package_manifest(package_root: Path) -> tuple[McpPackageManifest, dict[str, object] | None]:
    path = package_root / "mcp.package.json"
    if not path.is_file():
        raise McpPackageManifestError("mcp.package.json is required at the package root")
    value = _read(path)
    _validate(value, "mcp.package.schema.json", "mcp.package.json")
    runtime_value = value["runtime"]
    runtime = McpRuntimeManifest(
        type=str(runtime_value["type"]),
        command=tuple(str(item) for item in runtime_value["command"]),
        cwd=str(runtime_value.get("cwd", ".")),
        port=int(runtime_value["port"]),
        health_path=str(runtime_value.get("healthPath", "/health")),
        mcp_path=str(runtime_value["mcpPath"]),
    )
    if runtime.type != "process":
        raise McpPackageManifestError("Only process runtime is supported in this release")
    companion = None
    if "companionPlugin" in value:
        block = value["companionPlugin"]
        companion = CompanionPluginManifest(
            directory=str(block["directory"]),
            remove_with_package=bool(block.get("removeWithPackage", True)),
        )
        plugin_root = package_root / companion.directory
        if not (plugin_root / "plugin.json").is_file():
            raise McpPackageManifestError("companionPlugin directory must contain plugin.json")
    migration = None
    if "migration" in value:
        try:
            migration = parse_migration_block(value["migration"])
        except McpPackageMigrationError as exc:
            raise McpPackageManifestError(str(exc)) from exc
    configuration = None
    configuration_file = str(value["configuration"]) if "configuration" in value else None
    if configuration_file:
        configuration = _read(package_root / configuration_file)
        _validate(configuration, "config.schema.json", configuration_file)
        keys = [field["key"] for field in configuration["fields"]]
        if len(keys) != len(set(keys)):
            raise McpPackageManifestError("config.schema.json field keys must be unique")
    return McpPackageManifest(
        name=str(value["name"]),
        version=str(value["version"]),
        description=str(value["description"]) if "description" in value else None,
        runtime=runtime,
        configuration_file=configuration_file,
        companion_plugin=companion,
        migration=migration,
    ), configuration


def validate_mcp_package_settings(schema: dict[str, object], values: object) -> tuple[dict[str, object], dict[str, str]]:
    try:
        return validate_settings(schema, values)
    except VaultManifestError as exc:
        raise McpPackageManifestError(str(exc)) from exc


def _read(path: Path) -> dict[str, object]:
    try:
        if path.stat().st_size > _MAX_BYTES:
            raise McpPackageManifestError(f"{path.name} exceeds the size limit")
        value = json.loads(path.read_text(encoding="utf-8"))
    except McpPackageManifestError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise McpPackageManifestError(f"{path.name} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise McpPackageManifestError(f"{path.name} must be a JSON object")
    return value


def _validate(value: dict[str, object], filename: str, label: str) -> None:
    schema = json.loads((_ROOT / filename).read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda item: list(item.path))
    if errors:
        location = ".".join(str(item) for item in errors[0].path)
        raise McpPackageManifestError(f"{label}{' at ' + location if location else ''}: {errors[0].message}")
