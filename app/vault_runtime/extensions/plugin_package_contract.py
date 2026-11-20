"""Vault plugin manifest extensions: workspace import, local share, lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.vault_runtime.extensions.mcp_package_migration import McpPackageMigrationError


_NAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$")
_MOUNT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass(frozen=True, slots=True)
class WorkspaceImportItem:
    source: str
    target: str
    kind: str
    on_conflict: str | None


@dataclass(frozen=True, slots=True)
class WorkspaceImportManifest:
    on_conflict: str
    items: tuple[WorkspaceImportItem, ...]


@dataclass(frozen=True, slots=True)
class LocalShareManifest:
    mount_name: str
    permission: str
    label: str
    required: bool


@dataclass(frozen=True, slots=True)
class PluginProcessRuntime:
    command: tuple[str, ...]
    cwd: str
    port: int
    health_path: str


@dataclass(frozen=True, slots=True)
class PluginLifecycleManifest:
    supervised: bool
    runtime: PluginProcessRuntime | None


def parse_workspace_import_block(block: object) -> WorkspaceImportManifest:
    if not isinstance(block, dict):
        raise McpPackageMigrationError("workspaceImport must be an object")
    on_conflict = str(block.get("onConflict", "ask"))
    if on_conflict not in {"ask", "replace", "skip-if-exists"}:
        raise McpPackageMigrationError("workspaceImport.onConflict is invalid")
    raw_items = block.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise McpPackageMigrationError("workspaceImport.items must be a non-empty array")
    items: list[WorkspaceImportItem] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise McpPackageMigrationError(f"workspaceImport.items[{index}] must be an object")
        kind = str(item.get("kind", "directory"))
        if kind not in {"file", "directory"}:
            raise McpPackageMigrationError(f"workspaceImport.items[{index}].kind must be file or directory")
        source = str(item["source"])
        target = str(item["target"])
        _safe_package_relative(source, label=f"workspaceImport.items[{index}].source")
        _safe_workspace_target(target, label=f"workspaceImport.items[{index}].target")
        item_conflict = item.get("onConflict")
        if item_conflict is not None and str(item_conflict) not in {"ask", "replace", "skip-if-exists"}:
            raise McpPackageMigrationError(f"workspaceImport.items[{index}].onConflict is invalid")
        items.append(WorkspaceImportItem(
            source=source,
            target=target,
            kind=kind,
            on_conflict=str(item_conflict) if item_conflict is not None else None,
        ))
    return WorkspaceImportManifest(on_conflict=on_conflict, items=tuple(items))


def parse_local_share_block(block: object) -> LocalShareManifest:
    if not isinstance(block, dict):
        raise McpPackageMigrationError("localShare must be an object")
    mount_name = str(block["mountName"])
    if not _MOUNT_NAME_PATTERN.fullmatch(mount_name):
        raise McpPackageMigrationError("localShare.mountName is invalid")
    permission = str(block.get("permission", "read"))
    if permission not in {"read", "write"}:
        raise McpPackageMigrationError("localShare.permission must be read or write")
    label = str(block.get("label", mount_name)).strip()
    if not label:
        raise McpPackageMigrationError("localShare.label must not be empty")
    return LocalShareManifest(
        mount_name=mount_name,
        permission=permission,
        label=label[:120],
        required=bool(block.get("required", False)),
    )


def parse_lifecycle_block(block: object) -> PluginLifecycleManifest:
    if not isinstance(block, dict):
        raise McpPackageMigrationError("lifecycle must be an object")
    supervised = bool(block.get("supervised", False))
    runtime = None
    if "runtime" in block:
        runtime_value = block["runtime"]
        if not isinstance(runtime_value, dict):
            raise McpPackageMigrationError("lifecycle.runtime must be an object")
        command_raw = runtime_value.get("command")
        if not isinstance(command_raw, list) or not command_raw:
            raise McpPackageMigrationError("lifecycle.runtime.command must be a non-empty array")
        runtime = PluginProcessRuntime(
            command=tuple(str(item) for item in command_raw),
            cwd=str(runtime_value.get("cwd", ".")),
            port=int(runtime_value.get("port", 8790)),
            health_path=str(runtime_value.get("healthPath", "/health")),
        )
    if supervised and runtime is None:
        raise McpPackageMigrationError("lifecycle.supervised requires lifecycle.runtime")
    if not supervised and runtime is not None:
        raise McpPackageMigrationError("lifecycle.runtime requires lifecycle.supervised=true")
    return PluginLifecycleManifest(supervised=supervised, runtime=runtime)


def _safe_package_relative(relative: str, *, label: str) -> None:
    path_parts = relative.replace("\\", "/").split("/")
    if not relative or relative.startswith("/") or ".." in path_parts or relative.endswith("/"):
        raise McpPackageMigrationError(f"{label} must be a safe relative path")


def _safe_workspace_target(relative: str, *, label: str) -> None:
    normalized = relative.strip("/")
    if relative != normalized:
        raise McpPackageMigrationError(f"{label} must not start or end with /")
    if ".." in normalized.split("/"):
        raise McpPackageMigrationError(f"{label} must not contain ..")
    if normalized and not _NAME_PATTERN.fullmatch(normalized.split("/")[0]):
        raise McpPackageMigrationError(f"{label} must use lowercase workspace path segments")
