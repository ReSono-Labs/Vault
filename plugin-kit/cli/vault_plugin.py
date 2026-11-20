#!/usr/bin/env python3
"""Create, validate, inspect and package Vault plugins without a live Vault."""

from __future__ import annotations

import argparse
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
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


class KitError(ValueError):
    pass


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
    _validate_schema(plugin, "plugin.schema.json", "plugin.json")
    name = plugin.get("name")
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        raise KitError("plugin.json name must use lowercase letters, numbers, dots, dashes or underscores.")

    vault = _object(root / "vault.json")
    _validate_schema(vault, "vault.schema.json", "vault.json")
    if "configuration" in vault:
        config = _object(root / str(vault["configuration"]))
        _validate_schema(config, "config.schema.json", "config.schema.json")
        keys = [field.get("key") for field in config.get("fields", []) if isinstance(field, dict)]
        if len(keys) != len(set(keys)):
            raise KitError("config.schema.json field keys must be unique.")
    if "mcp" in vault:
        mcp = _object(root / str(vault["mcp"]))
        _validate_schema(mcp, "mcp.schema.json", "mcp.json")
        for server_name, server in mcp["mcpServers"].items():
            if not isinstance(server_name, str) or not isinstance(server, dict):
                raise KitError("Every MCP server needs a name and object configuration.")
            if server.get("type") != "streamable-http" or not isinstance(server.get("url"), str):
                raise KitError(f"MCP server '{server_name}' must use streamable-http and provide a URL.")
            if "headers" in server:
                raise KitError("Do not put credentials in mcp.json. Declare them in config.schema.json.")
    return {"name": name, "files": len(files), "bytes": total, "vault": vault, "plugin": plugin}


def create(name: str, destination: Path, language: str) -> Path:
    if not NAME_PATTERN.fullmatch(name):
        raise KitError("Plugin name must use lowercase letters, numbers, dots, dashes or underscores.")
    target = (destination / name).resolve()
    if target.exists():
        raise KitError(f"Destination already exists: {target}")
    starter = KIT_ROOT / "starters" / language
    shutil.copytree(starter, target)
    replacements = {
        "plugin.json": [("starter.example", name)],
        "vault.json": [],
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
            print(f"Valid Vault plugin: {result['name']} ({result['files']} files)")
        elif args.command == "inspect":
            result = validate(args.path)
            vault = result["vault"]
            print(json.dumps({
                "name": result["name"], "agentsRequested": vault.get("agents", []),
                "servicesRequested": vault.get("services", []),
                "hasConfiguration": "configuration" in vault,
                "hasMcpTools": "mcp" in vault,
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
