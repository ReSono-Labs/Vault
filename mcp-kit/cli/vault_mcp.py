#!/usr/bin/env python3
"""Create, validate, inspect and package Vault MCP packages without a live Vault."""

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
except ImportError:  # pragma: no cover
    Draft202012Validator = None  # type: ignore[assignment]


KIT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_KIT_ROOT = KIT_ROOT.parent / "plugin-kit"
MCP_PACKAGE_SCHEMA = "https://schemas.resonolabs.com/vault/mcp-package/v1.json"
CONFIG_SCHEMA = "https://schemas.resonolabs.com/vault/plugin-config/v1.json"
PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
VAULT_SCHEMA = "https://schemas.resonolabs.com/vault/plugin/v1.json"
MAX_FILES = 512
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_PACKAGE_BYTES = 32 * 1024 * 1024
NAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$")


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


def _plugin_schema(name: str) -> dict[str, object]:
    return _object(PLUGIN_KIT_ROOT / "schemas" / name)


def _validate_schema(value: dict[str, object], schema: dict[str, object], label: str) -> None:
    if Draft202012Validator is None:
        raise KitError("Install the 'jsonschema' Python package to use the validator.")
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda item: list(item.path))
    if errors:
        error = errors[0]
        location = ".".join(str(item) for item in error.absolute_path)
        raise KitError(f"{label}{' at ' + location if location else ''}: {error.message}")


def validate(root: Path) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise KitError("Package path must be a directory.")
    manifest_path = root / "mcp.package.json"
    if not manifest_path.is_file():
        raise KitError("mcp.package.json is required at the package root.")
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if len(files) > MAX_FILES:
        raise KitError(f"Package has more than {MAX_FILES} files.")
    total = 0
    for path in files:
        if path.is_symlink():
            raise KitError(f"Symbolic links are not allowed: {path.relative_to(root)}")
        size = path.stat().st_size
        total += size
        if size > MAX_FILE_BYTES:
            raise KitError(f"File is too large: {path.relative_to(root)}")
    if total > MAX_PACKAGE_BYTES:
        raise KitError("Package is larger than 32 MiB.")

    manifest = _object(manifest_path)
    _validate_schema(manifest, _schema("mcp.package.schema.json"), "mcp.package.json")
    name = manifest.get("name")
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        raise KitError("mcp.package.json name must use lowercase letters, numbers, dots, dashes or underscores.")
    if root.name != name:
        raise KitError(f"Directory name '{root.name}' must match mcp.package.json name '{name}'.")

    if "configuration" in manifest:
        config = _object(root / str(manifest["configuration"]))
        _validate_schema(config, _plugin_schema("config.schema.json"), "config.schema.json")
        keys = [field.get("key") for field in config.get("fields", []) if isinstance(field, dict)]
        if len(keys) != len(set(keys)):
            raise KitError("config.schema.json field keys must be unique.")

    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict):
        raise KitError("runtime must be an object.")
    command = runtime.get("command")
    if not isinstance(command, list) or not command:
        raise KitError("runtime.command must be a non-empty array.")
    cwd = root / str(runtime.get("cwd", "."))
    if not cwd.is_dir():
        raise KitError("runtime.cwd must exist inside the package.")
    executable = str(command[0])
    if Path(executable).name in {"python", "python3"}:
        if len(command) < 2:
            raise KitError("runtime.command must name a script after python.")
        script = cwd / str(command[1])
        if not script.is_file():
            raise KitError(f"runtime.command script is missing: {command[1]}")
    elif not (cwd / executable).is_file() and shutil.which(executable) is None:
        raise KitError(f"runtime.command entry is missing: {executable}")

    if "companionPlugin" in manifest:
        block = manifest["companionPlugin"]
        if not isinstance(block, dict):
            raise KitError("companionPlugin must be an object.")
        plugin_root = root / str(block["directory"])
        plugin = _object(plugin_root / "plugin.json")
        _validate_schema(plugin, _plugin_schema("plugin.schema.json"), "companion plugin.json")
        if (plugin_root / "vault.json").exists():
            vault = _object(plugin_root / "vault.json")
            _validate_schema(vault, _plugin_schema("vault.schema.json"), "companion vault.json")

    if "migration" in manifest:
        block = manifest["migration"]
        if not isinstance(block, dict):
            raise KitError("migration must be an object.")
        if "database" not in block and "workspace" not in block:
            raise KitError("migration must declare database and/or workspace.")
        if "database" in block:
            database = block["database"]
            if not isinstance(database, dict):
                raise KitError("migration.database must be an object.")
            source = root / str(database["source"])
            if not source.is_file():
                raise KitError("migration.database source is missing.")
            if source.read_bytes()[:16] != b"SQLite format 3\x00":
                raise KitError("migration.database must be a SQLite file.")
        if "workspace" in block:
            workspace = block["workspace"]
            if not isinstance(workspace, dict):
                raise KitError("migration.workspace must be an object.")
            source = root / str(workspace["source"])
            if not source.is_dir():
                raise KitError("migration.workspace source is missing.")

    return {"name": name, "files": len(files), "bytes": total, "manifest": manifest}


def create(name: str, destination: Path) -> Path:
    if not NAME_PATTERN.fullmatch(name):
        raise KitError("Package name must use lowercase letters, numbers, dots, dashes or underscores.")
    target = (destination / name).resolve()
    if target.exists():
        raise KitError(f"Destination already exists: {target}")
    starter = KIT_ROOT / "starters" / "starter.example"
    shutil.copytree(starter, target)
    replacements = {
        "mcp.package.json": [("starter.example", name)],
        "plugin/plugin.json": [("starter.example.ui", f"{name}.ui")],
    }
    for relative, changes in replacements.items():
        path = target / relative
        text = path.read_text(encoding="utf-8")
        for old, new in changes:
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")
    manifest = _object(target / "mcp.package.json")
    manifest["name"] = name
    target.joinpath("mcp.package.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
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
    parser = argparse.ArgumentParser(prog="vault-mcp", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new", help="Create a starter MCP package")
    new.add_argument("name")
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
            print(f"Created {create(args.name, args.destination)}")
        elif args.command == "validate":
            result = validate(args.path)
            print(f"Valid MCP package: {result['name']} ({result['files']} files)")
        elif args.command == "inspect":
            result = validate(args.path)
            manifest = result["manifest"]
            runtime = manifest.get("runtime", {})
            print(json.dumps({
                "name": result["name"],
                "runtimeType": runtime.get("type"),
                "hasConfiguration": "configuration" in manifest,
                "hasCompanionPlugin": "companionPlugin" in manifest,
                "hasRequirements": (args.path / "requirements.txt").is_file(),
                "note": "Vault supervises this package inside the Vault container on 127.0.0.1.",
            }, indent=2))
        else:
            print(f"Created {package(args.path, args.output)}")
        return 0
    except KitError as exc:
        print(f"MCP Kit error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
