"""Migration payload import for hosted MCP packages and Agent Plugins."""

from __future__ import annotations

from dataclasses import dataclass
import shutil
from pathlib import Path


class McpPackageMigrationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class McpPackageMigrationResource:
    source: str
    target: str


@dataclass(frozen=True, slots=True)
class McpPackageMigrationManifest:
    database: McpPackageMigrationResource | None
    workspace: McpPackageMigrationResource | None
    on_conflict: str


def parse_migration_block(block: object) -> McpPackageMigrationManifest:
    if not isinstance(block, dict):
        raise McpPackageMigrationError("migration must be an object")
    database = None
    workspace = None
    if "database" in block:
        database_value = block["database"]
        if not isinstance(database_value, dict):
            raise McpPackageMigrationError("migration.database must be an object")
        database = McpPackageMigrationResource(
            source=str(database_value["source"]),
            target=str(database_value["target"]),
        )
    if "workspace" in block:
        workspace_value = block["workspace"]
        if not isinstance(workspace_value, dict):
            raise McpPackageMigrationError("migration.workspace must be an object")
        workspace = McpPackageMigrationResource(
            source=str(workspace_value["source"]),
            target=str(workspace_value["target"]),
        )
    if database is None and workspace is None:
        raise McpPackageMigrationError("migration must declare database and/or workspace")
    return McpPackageMigrationManifest(
        database=database,
        workspace=workspace,
        on_conflict=str(block.get("onConflict", "ask")),
    )


_SQLITE_HEADER = b"SQLite format 3\x00"
_MAX_DATABASE_BYTES = 64 * 1024 * 1024
_MAX_WORKSPACE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class MigrationConflict:
    target: str
    path: Path


@dataclass(frozen=True, slots=True)
class MigrationAssessment:
    declared: bool
    on_conflict: str
    database: MigrationConflict | None
    workspace: MigrationConflict | None

    @property
    def requires_decision(self) -> bool:
        return self.on_conflict == "ask" and (self.database is not None or self.workspace is not None)


@dataclass(frozen=True, slots=True)
class MigrationImportResult:
    status: dict[str, str]
    imported: tuple[str, ...]
    skipped: tuple[str, ...]


def validate_migration_payload(
    package_root: Path, migration: McpPackageMigrationManifest,
) -> None:
    if migration.database is not None:
        source = _resolve_source(package_root, migration.database.source)
        if not source.is_file():
            raise McpPackageMigrationError("migration database source is missing")
        if source.stat().st_size > _MAX_DATABASE_BYTES:
            raise McpPackageMigrationError("migration database exceeds the size limit")
        header = source.read_bytes()[:16]
        if header != _SQLITE_HEADER:
            raise McpPackageMigrationError("migration database must be a SQLite file")
        _safe_relative_target(migration.database.target)
    if migration.workspace is not None:
        source = _resolve_source(package_root, migration.workspace.source)
        if not source.is_dir():
            raise McpPackageMigrationError("migration workspace source is missing")
        total = sum(path.stat().st_size for path in source.rglob("*") if path.is_file())
        if total > _MAX_WORKSPACE_BYTES:
            raise McpPackageMigrationError("migration workspace exceeds the size limit")
        _safe_relative_target(migration.workspace.target)


def assess_migration(
    *, data_dir: Path, migration: McpPackageMigrationManifest | None,
) -> MigrationAssessment:
    if migration is None:
        return MigrationAssessment(False, "skip-if-exists", None, None)
    database_conflict = None
    workspace_conflict = None
    if migration.database is not None:
        target = (data_dir / migration.database.target).resolve()
        if target.exists():
            database_conflict = MigrationConflict(migration.database.target, target)
    if migration.workspace is not None:
        target = (data_dir / migration.workspace.target).resolve()
        if target.exists() and any(target.iterdir()):
            workspace_conflict = MigrationConflict(migration.workspace.target, target)
    return MigrationAssessment(
        True, migration.on_conflict, database_conflict, workspace_conflict,
    )


def import_migration_payload(
    *,
    package_root: Path,
    data_dir: Path,
    migration: McpPackageMigrationManifest,
    assessment: MigrationAssessment,
    replace_package: bool,
    replace_migration: bool,
) -> MigrationImportResult:
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    imported: list[str] = []
    skipped: list[str] = []
    status: dict[str, str] = {}

    if migration.database is not None:
        action = _resolve_action(
            assessment.database is not None, migration.on_conflict,
            replace_package=replace_package, replace_migration=replace_migration,
        )
        if action == "import":
            target = data_dir / migration.database.target
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(_resolve_source(package_root, migration.database.source), target)
            target.chmod(0o600)
            imported.append("database")
            status["database"] = "imported"
        else:
            skipped.append("database")
            status["database"] = "skipped" if assessment.database else "absent"

    if migration.workspace is not None:
        action = _resolve_action(
            assessment.workspace is not None, migration.on_conflict,
            replace_package=replace_package, replace_migration=replace_migration,
        )
        target_root = data_dir / migration.workspace.target
        if action == "import":
            source = _resolve_source(package_root, migration.workspace.source)
            if target_root.exists():
                shutil.rmtree(target_root)
            shutil.copytree(source, target_root, symlinks=False)
            _chmod_tree(target_root)
            imported.append("workspace")
            status["workspace"] = "imported"
        else:
            skipped.append("workspace")
            status["workspace"] = "skipped" if assessment.workspace else "absent"

    return MigrationImportResult(status=status, imported=tuple(imported), skipped=tuple(skipped))


def _resolve_action(
    conflict: bool, on_conflict: str, *, replace_package: bool, replace_migration: bool,
) -> str:
    if not conflict:
        return "import"
    if on_conflict == "replace":
        return "import" if replace_package else "skip"
    if on_conflict == "skip-if-exists":
        return "skip"
    return "import" if replace_migration else "skip"


def _resolve_source(package_root: Path, relative: str) -> Path:
    source = (package_root / relative).resolve()
    if not source.is_relative_to(package_root.resolve()):
        raise McpPackageMigrationError("migration source escapes the package root")
    return source


def _safe_relative_target(relative: str) -> None:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or path.parts[:1] == (".",):
        raise McpPackageMigrationError("migration target must be a safe relative path")


def _chmod_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            path.chmod(0o600)
        elif path.is_dir():
            path.chmod(0o700)
