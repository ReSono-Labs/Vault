#!/usr/bin/env python3
"""Create, validate, inspect and package Vault plugins without a live Vault."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - produces a direct install hint
    Draft202012Validator = None  # type: ignore[assignment]


KIT_ROOT = Path(__file__).resolve().parents[1]
AGENT_PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
VAULT_SCHEMA = "https://schemas.resonolabs.com/vault/plugin/v1.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
CONFIG_SCHEMA = "https://schemas.resonolabs.com/vault/plugin-config/v1.json"
MAX_FILES = 512
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_PACKAGE_BYTES = 32 * 1024 * 1024
# Agent Plugins 1.0.0 plugin.schema.json name pattern (1-64 characters).
NAME_PATTERN = re.compile(r"^(?!.*(?:--|\.\.))(?=.{1,64}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
VAULT_NAMESPACE = "com.resonolabs.vault"


class KitError(ValueError):
    pass


# The kit runs Vault's own parsers instead of a copy of their rules. In the repository it
# loads them from app/; the kit download bundles the same files next to this one.
_RUNTIME_SOURCES = {
    "skills": ("vault_skills.py", "app/vault_runtime/extensions/skills.py"),
    "mcp_rules": ("vault_mcp_rules.py", "app/vault_runtime/extensions/mcp_rules.py"),
}
_RUNTIME_MODULES: dict[str, object] = {}


def _runtime(name: str):
    if name in _RUNTIME_MODULES:
        return _RUNTIME_MODULES[name]
    bundled, repository = _RUNTIME_SOURCES[name]
    for path in (KIT_ROOT / "cli" / bundled, KIT_ROOT.parent / repository):
        if not path.is_file():
            continue
        spec = importlib.util.spec_from_file_location(f"vault_plugin_kit_{name}", path)
        if spec is None or spec.loader is None:
            break
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # dataclasses resolve their module by name.
        try:
            spec.loader.exec_module(module)
        except ImportError as exc:
            del sys.modules[spec.name]
            raise KitError(f"Install the Python package the validator needs: {exc.name}.") from exc
        _RUNTIME_MODULES[name] = module
        return module
    raise KitError(f"The kit is missing Vault's {name} parser ({bundled}).")


def _validate_skills(root: Path) -> list[str]:
    """Run Vault's Skill parser on every immediate folder under skills/, as import does."""
    skill_root = root / "skills"
    if not skill_root.exists():
        return []
    if not skill_root.is_dir():
        raise KitError("skills must be a directory.")
    skills = _runtime("skills")
    names = []
    for child in sorted(skill_root.iterdir()):
        if not child.is_dir():
            raise KitError(f"skills/{child.name} must be a directory containing SKILL.md.")
        try:
            names.append(skills.parse_skill(child).name)
        except skills.SkillSpecificationError as exc:
            raise KitError(f"skills/{child.name}: {exc}") from exc
    return names


def _object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise KitError(f"Missing {path.name}.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KitError(f"{path.name} must be valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise KitError(f"{path.name} must contain a JSON object.")
    return value


def _schema(name: str) -> dict[str, object]:
    return _object(KIT_ROOT / "schemas" / name)


def _validate_schema(value: dict[str, object], schema_name: str, label: str) -> None:
    if Draft202012Validator is None:
        raise KitError("Install the 'jsonschema' Python package to use the validator.")
    errors = sorted(Draft202012Validator(_schema(schema_name)).iter_errors(value), key=lambda item: list(item.path))
    if errors:
        error = errors[0]
        location = ".".join(str(item) for item in error.absolute_path)
        raise KitError(f"{label}{' at ' + location if location else ''}: {error.message}")


def validate(root: Path) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise KitError("Plugin path must be a directory.")
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if len(files) > MAX_FILES:
        raise KitError(f"Plugin has more than {MAX_FILES} files.")
    total = 0
    for path in files:
        if path.is_symlink():
            raise KitError(f"Symbolic links are not allowed: {path.relative_to(root)}")
        size = path.stat().st_size
        total += size
        if size > MAX_FILE_BYTES:
            raise KitError(f"File is too large: {path.relative_to(root)}")
    if total > MAX_PACKAGE_BYTES:
        raise KitError("Plugin package is larger than 32 MiB.")

    plugin = _object(root / "plugin.json")
    declared = plugin.get("$schema")
    if declared != AGENT_PLUGIN_SCHEMA:
        raise KitError(f"plugin.json: unsupported Agent Plugins version {declared}" if isinstance(declared, str)
                       else f"plugin.json at $schema: use {AGENT_PLUGIN_SCHEMA}")
    _validate_schema(plugin, "plugin.schema.json", "plugin.json")
    name = plugin.get("name")
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        raise KitError("plugin.json name must use lowercase letters, numbers, dots or dashes.")

    warnings: list[str] = []
    vault, data_root, label = _vault_data(root, plugin, warnings)
    if "configuration" in vault:
        config_label = f"{data_root.relative_to(root).as_posix() + '/' if data_root != root else ''}{vault['configuration']}"
        config = _object(data_root / str(vault["configuration"]))
        _validate_schema(config, "config.schema.json", config_label)
        keys = [field.get("key") for field in config.get("fields", []) if isinstance(field, dict)]
        if len(keys) != len(set(keys)):
            raise KitError("config.schema.json field keys must be unique.")
        rules = _runtime("mcp_rules")
        for field in config.get("fields", []):
            header = field.get("secretHeader") if isinstance(field, dict) else None
            if isinstance(header, str) and rules.is_reserved_header(header):
                raise KitError(f"{config_label} field {field.get('key')}: secretHeader {header} is set by Vault.")
    if "mcp" in vault and not (root / "mcp.json").is_file():
        raise KitError(f"{label} declares mcp.json but the root mcp.json is missing.")
    servers = _validate_mcp(root, warnings)
    skills = _validate_skills(root)
    return {"name": name, "files": len(files), "bytes": total, "vault": vault, "plugin": plugin,
            "skills": skills, "mcpServers": servers, "warnings": warnings}


def _vault_data(root: Path, plugin: dict[str, object], warnings: list[str]) -> tuple[dict[str, object], Path, str]:
    """Vault data from plugin.json extensions (preferred) or the legacy root vault.json; never both."""
    extensions = plugin.get("extensions")
    namespace = extensions.get(VAULT_NAMESPACE) if isinstance(extensions, dict) else None
    legacy = root / "vault.json"
    if namespace is not None:
        label = f"plugin.json extensions.{VAULT_NAMESPACE}"
        if legacy.exists():
            warnings.append(f"vault.json is ignored because {label} is present. Delete vault.json.")
        value = {"$schema": VAULT_SCHEMA, **namespace} if isinstance(namespace, dict) else namespace
        if not isinstance(value, dict):
            raise KitError(f"{label} must be an object.")
        _validate_schema(value, "vault.schema.json", label)
        return value, root / VAULT_NAMESPACE, label
    if legacy.exists():
        vault = _object(legacy)
        _validate_schema(vault, "vault.schema.json", "vault.json")
        warnings.append(f"vault.json is the legacy form. Move its fields to plugin.json extensions.{VAULT_NAMESPACE}.")
        return vault, root, "vault.json"
    return {}, root, "plugin.json"


def _validate_mcp(root: Path, warnings: list[str]) -> list[str]:
    """Root mcp.json with the rules Vault's import applies (portable schema plus Vault's checks)."""
    path = root / "mcp.json"
    if not path.exists():
        return []
    if not path.is_file():
        raise KitError("mcp.json must be a file.")
    mcp = _object(path)
    _validate_schema(mcp, "mcp.schema.json", "mcp.json")
    rules = _runtime("mcp_rules")
    servers = []
    for server_name, server in mcp["mcpServers"].items():
        problem = rules.server_name_problem(server_name)
        if problem is not None:
            raise KitError(f"mcp.json server '{server_name}': {problem}.")
        unsupported = rules.transport_problem(server)
        if unsupported is not None:
            warnings.append(f"mcp.json server '{server_name}': Vault skips it ({unsupported}).")
            continue
        problem = rules.url_problem(server.get("url"))
        if problem is not None:
            raise KitError(f"mcp.json server '{server_name}': {problem}.")
        try:
            rules.validate_headers(server.get("headers", {}), allow_credentials=False)
        except rules.McpRuleError as exc:
            hint = " Declare credentials as secret fields in config.schema.json." if "secret storage" in str(exc) else ""
            raise KitError(f"mcp.json server '{server_name}': {exc}.{hint}") from exc
        servers.append(server_name)
    return servers


def create(name: str, destination: Path, language: str) -> Path:
    if not NAME_PATTERN.fullmatch(name):
        raise KitError("Plugin name must be 1-64 lowercase letters, numbers, dots or dashes, start and end "
                       "with a letter or number, and contain no '--' or '..'.")
    target = (destination / name).resolve()
    if target.exists():
        raise KitError(f"Destination already exists: {target}")
    starter = KIT_ROOT / "starters" / language
    shutil.copytree(starter, target)
    replacements = {
        "plugin.json": [("starter.example", name)],
        "README.md": [("starter.example", name)],
    }
    for relative, changes in replacements.items():
        path = target / relative
        text = path.read_text(encoding="utf-8")
        for old, new in changes:
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")
    return target


def package(root: Path, output: Path | None) -> Path:
    result = validate(root)
    resolved = root.resolve()
    destination = output.resolve() if output else resolved.parent / f"{result['name']}.zip"
    if destination.exists():
        raise KitError(f"Output already exists: {destination}")
    paths = sorted(path for path in resolved.rglob("*") if path.is_file())
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in paths:
            info = zipfile.ZipInfo(f"{result['name']}/{path.relative_to(resolved).as_posix()}")
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vault-plugin", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new", help="Create a starter plugin")
    new.add_argument("name")
    new.add_argument("--language", choices=("python", "typescript"), default="python")
    new.add_argument("--destination", type=Path, default=Path.cwd())
    for command in ("validate", "inspect", "package"):
        item = commands.add_parser(command)
        item.add_argument("path", type=Path)
        if command == "package":
            item.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "new":
            print(f"Created {create(args.name, args.destination, args.language)}")
        elif args.command == "validate":
            result = validate(args.path)
            for warning in result["warnings"]:
                print(f"Warning: {warning}", file=sys.stderr)
            print(f"Valid Vault plugin: {result['name']} ({result['files']} files)")
        elif args.command == "inspect":
            result = validate(args.path)
            vault = result["vault"]
            print(json.dumps({
                "name": result["name"], "agentsRequested": vault.get("agents", []),
                "servicesRequested": vault.get("services", []),
                "hasConfiguration": "configuration" in vault,
                "hasMcpTools": bool(result["mcpServers"]),
                "note": "Vault grants nothing automatically. The owner approves access after installation."
            }, indent=2))
        else:
            print(f"Created {package(args.path, args.output)}")
        return 0
    except KitError as exc:
        print(f"Plugin Kit error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
