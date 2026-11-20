"""Import plugin archive payloads into the Vault workspace files tree."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from app.vault_runtime.extensions.mcp_package_migration import McpPackageMigrationError
from app.vault_runtime.extensions.plugin_package_contract import WorkspaceImportItem, WorkspaceImportManifest
from app.vault_runtime.workspace_files.store import WorkspaceFilesystemStore
from app.vault_runtime.workspace_paths import normalize_workspace_file_key


_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_TREE_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class WorkspaceImportConflict:
    target: str
    path: Path


@dataclass(frozen=True, slots=True)
class WorkspaceImportAssessment:
    declared: bool
    on_conflict: str
    conflicts: tuple[WorkspaceImportConflict, ...]

    @property
    def requires_decision(self) -> bool:
        return self.on_conflict == "ask" and bool(self.conflicts)


@dataclass(frozen=True, slots=True)
class WorkspaceImportResult:
    status: dict[str, str]
    imported: tuple[str, ...]
    skipped: tuple[str, ...]


def validate_workspace_import_payload(
    package_root: Path, manifest: WorkspaceImportManifest,
) -> None:
    total = 0
    for item in manifest.items:
        source = _resolve_source(package_root, item.source)
        if item.kind == "file":
            if not source.is_file():
                raise McpPackageMigrationError(f"workspace import source is missing: {item.source}")
            size = source.stat().st_size
            if size > _MAX_FILE_BYTES:
                raise McpPackageMigrationError(f"workspace import file exceeds size limit: {item.source}")
            total += size
        else:
            if not source.is_dir():
                raise McpPackageMigrationError(f"workspace import directory is missing: {item.source}")
            tree_size = sum(path.stat().st_size for path in source.rglob("*") if path.is_file())
            if tree_size > _MAX_TREE_BYTES:
                raise McpPackageMigrationError(f"workspace import directory exceeds size limit: {item.source}")
            total += tree_size
    if total > _MAX_TREE_BYTES:
        raise McpPackageMigrationError("workspaceImport total payload exceeds the size limit")


def assess_workspace_import(
    *,
    store: WorkspaceFilesystemStore,
    workspace_id: str,
    manifest: WorkspaceImportManifest | None,
) -> WorkspaceImportAssessment:
    if manifest is None:
        return WorkspaceImportAssessment(False, "skip-if-exists", ())
    conflicts: list[WorkspaceImportConflict] = []
    files_root = store.files_root(workspace_id=workspace_id)
    for item in manifest.items:
        target_path = _target_path(files_root=files_root, target=item.target, kind=item.kind)
        if target_path.exists():
            conflicts.append(WorkspaceImportConflict(item.target or ".", target_path))
    return WorkspaceImportAssessment(True, manifest.on_conflict, tuple(conflicts))


def import_workspace_payload(
    *,
    package_root: Path,
    store: WorkspaceFilesystemStore,
    workspace_id: str,
    manifest: WorkspaceImportManifest,
    assessment: WorkspaceImportAssessment,
    replace_package: bool,
    replace_workspace_import: bool,
) -> WorkspaceImportResult:
    imported: list[str] = []
    skipped: list[str] = []
    status: dict[str, str] = {}
    for item in manifest.items:
        on_conflict = item.on_conflict or manifest.on_conflict
        conflict = any(entry.target == (item.target or ".") for entry in assessment.conflicts)
        action = _resolve_action(
            conflict,
            on_conflict,
            replace_package=replace_package,
            replace_import=replace_workspace_import,
        )
        key = item.target or item.source
        if action == "import":
            _import_item(
                package_root=package_root,
                store=store,
                workspace_id=workspace_id,
                item=item,
            )
            imported.append(key)
            status[key] = "imported"
        else:
            skipped.append(key)
            status[key] = "skipped" if conflict else "absent"
    return WorkspaceImportResult(status=status, imported=tuple(imported), skipped=tuple(skipped))


def revert_workspace_import(
    *,
    store: WorkspaceFilesystemStore,
    workspace_id: str,
    manifest: WorkspaceImportManifest,
    imported: tuple[str, ...],
) -> None:
    items_by_key = {item.target or item.source: item for item in manifest.items}
    for key in imported:
        item = items_by_key.get(key)
        if item is None:
            continue
        target = item.target
        try:
            store.delete_path(
                workspace_id=workspace_id,
                path=target,
                recursive=item.kind == "directory",
            )
        except Exception:
            continue


def _import_item(
    *,
    package_root: Path,
    store: WorkspaceFilesystemStore,
    workspace_id: str,
    item: WorkspaceImportItem,
) -> None:
    source = _resolve_source(package_root, item.source)
    if item.kind == "file":
        content = source.read_bytes()
        store.write_bytes(
            workspace_id=workspace_id,
            file_key=normalize_workspace_file_key(item.target),
            content=content,
        )
        return
    files_root = store.files_root(workspace_id=workspace_id)
    destination = _target_path(files_root=files_root, target=item.target, kind="directory")
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copytree(source, destination, symlinks=False)
    _chmod_tree(destination)


def _resolve_action(
    conflict: bool, on_conflict: str, *, replace_package: bool, replace_import: bool,
) -> str:
    if not conflict:
        return "import"
    if on_conflict == "replace":
        return "import" if replace_package else "skip"
    if on_conflict == "skip-if-exists":
        return "skip"
    return "import" if replace_import else "skip"


def _resolve_source(package_root: Path, relative: str) -> Path:
    source = (package_root / relative).resolve()
    if not source.is_relative_to(package_root.resolve()):
        raise McpPackageMigrationError("workspace import source escapes the package root")
    return source


def _target_path(*, files_root: Path, target: str, kind: str) -> Path:
    normalized = normalize_workspace_file_key(target) if target else ""
    if kind == "file":
        return files_root / normalized if normalized else files_root
    return files_root / normalized if normalized else files_root


def _chmod_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            path.chmod(0o600)
        elif path.is_dir():
            path.chmod(0o700)
