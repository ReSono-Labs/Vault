"""Atomic extension tree replacement adapted from R1 Plugin/Skill lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import shutil
from uuid import uuid4


class ExtensionFilesystemError(RuntimeError):
    pass


_MAX_IDENTITY_LENGTH = 512


def extension_relative_path(identity: str) -> PurePosixPath:
    """Treat extension identity as a relative path under a category or data root."""
    if not identity or len(identity) > _MAX_IDENTITY_LENGTH:
        raise ExtensionFilesystemError("extension identity is unsafe")
    if "\0" in identity or "\\" in identity:
        raise ExtensionFilesystemError("extension identity is unsafe")
    if identity.startswith("/") or identity.endswith("/"):
        raise ExtensionFilesystemError("extension identity is unsafe")
    relative = PurePosixPath(identity)
    if relative.is_absolute() or not relative.parts:
        raise ExtensionFilesystemError("extension identity is unsafe")
    for part in relative.parts:
        if part in {".", ".."}:
            raise ExtensionFilesystemError("extension identity is unsafe")
    return relative


# Every install's files live under its workspace: <root>/<category>/.ws/<workspace>/<identity>
# and <root>/data/.ws/<workspace>/<identity>. Extension names cannot start with ".", so the
# prefix never meets a name. Installs from before this layout used <root>/<category>/<identity>
# and are moved by ExtensionFilesystem.adopt_legacy at startup.
WORKSPACE_PREFIX = ".ws"


def workspace_storage_identity(workspace_id: str, identity: str) -> str:
    workspace = extension_relative_path(workspace_id)
    if len(workspace.parts) != 1 or workspace_id.startswith("."):
        raise ExtensionFilesystemError("workspace identity is unsafe")
    return str(PurePosixPath(WORKSPACE_PREFIX) / workspace / extension_relative_path(identity))


def managed_mcp_identity(*, plugin_identity: str, server_name: str) -> str:
    plugin = extension_relative_path(plugin_identity)
    server = extension_relative_path(server_name)
    return str(plugin / server)


def extension_category_path(*, root: Path, category: str, identity: str) -> Path:
    if category not in {"plugins", "skills", "mcps"}:
        raise ExtensionFilesystemError("unsupported extension category")
    relative = extension_relative_path(identity)
    extension_root = root.resolve()
    category_root = (extension_root / category).resolve()
    target = (category_root / relative).resolve()
    if not target.is_relative_to(extension_root):
        raise ExtensionFilesystemError("extension path escapes its root")
    return target


def extension_data_path(*, root: Path, identity: str) -> Path:
    relative = extension_relative_path(identity)
    extension_root = root.resolve()
    data_root = (extension_root / "data").resolve()
    target = (data_root / relative).resolve()
    if not target.is_relative_to(extension_root):
        raise ExtensionFilesystemError("plugin data path escapes its root")
    return target


@dataclass(frozen=True, slots=True)
class InstalledTree:
    identity: str
    current: Path
    previous: Path | None


class ExtensionFilesystem:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._recovery = self._root / "recovery"

    def replace(
        self, *, category: str, identity: str, candidate_root: Path,
        exclude_root_names: frozenset[str] = frozenset(),
    ) -> InstalledTree:
        base = self._component_base(category, identity)
        source = candidate_root.resolve(strict=True)
        if not source.is_dir() or source == self._root or self._root.is_relative_to(source):
            raise ExtensionFilesystemError("candidate extension tree is invalid")
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._recovery.mkdir(parents=True, exist_ok=True, mode=0o700)
        operation_id = uuid4().hex
        staged = base / f".staged-{operation_id}"
        current = base / "current"
        previous = base / "previous"
        record = self._recovery / f"{operation_id}.json"
        ignore = None
        if exclude_root_names:
            excluded = set(exclude_root_names)
            def ignore(_dir: str, names: list[str]) -> list[str]:
                return [name for name in names if name in excluded]
        shutil.copytree(source, staged, symlinks=False, ignore=ignore)
        _reject_links(staged)
        self._write_record(record, {
            "operationId": operation_id, "category": category, "identity": identity,
            "state": "staged", "hadCurrent": current.exists(),
        })
        try:
            if previous.exists():
                shutil.rmtree(previous)
            if current.exists():
                os.replace(current, previous)
            self._write_record(record, {
                "operationId": operation_id, "category": category, "identity": identity,
                "state": "previous-moved", "hadCurrent": previous.exists(),
            })
            os.replace(staged, current)
            self._write_record(record, {
                "operationId": operation_id, "category": category, "identity": identity,
                "state": "committed", "hadCurrent": previous.exists(),
            })
            record.unlink()
            return InstalledTree(identity, current, previous if previous.exists() else None)
        except Exception as exc:
            if not current.exists() and previous.exists():
                os.replace(previous, current)
            shutil.rmtree(staged, ignore_errors=True)
            raise ExtensionFilesystemError("extension replacement failed and was rolled back") from exc

    def rollback(self, *, category: str, identity: str) -> InstalledTree:
        base = self._component_base(category, identity)
        current, previous = base / "current", base / "previous"
        if not previous.is_dir():
            raise ExtensionFilesystemError("no previous extension version exists")
        displaced = base / f".rollback-{uuid4().hex}"
        if current.exists():
            os.replace(current, displaced)
        try:
            os.replace(previous, current)
            if displaced.exists():
                os.replace(displaced, previous)
        except Exception as exc:
            if not current.exists() and displaced.exists():
                os.replace(displaced, current)
            raise ExtensionFilesystemError("extension rollback failed") from exc
        return InstalledTree(identity, current, previous if previous.exists() else None)

    def recover(self) -> tuple[str, ...]:
        if not self._recovery.exists():
            return ()
        recovered: list[str] = []
        for record in sorted(self._recovery.glob("*.json")):
            try:
                data = json.loads(record.read_text(encoding="utf-8"))
                base = self._component_base(str(data["category"]), str(data["identity"]))
                current, previous = base / "current", base / "previous"
                staged = base / f".staged-{data['operationId']}"
                if not current.exists() and previous.exists():
                    os.replace(previous, current)
                shutil.rmtree(staged, ignore_errors=True)
                record.unlink()
                recovered.append(str(data["operationId"]))
            except Exception as exc:
                raise ExtensionFilesystemError(f"cannot recover extension operation {record.name}") from exc
        return tuple(recovered)

    def remove(self, *, category: str, identity: str) -> None:
        base = self._component_base(category, identity)
        shutil.rmtree(base, ignore_errors=True)

    def revert(self, *, category: str, identity: str, had_active_install: bool) -> None:
        if not had_active_install:
            self.remove(category=category, identity=identity)
            return
        try:
            self.rollback(category=category, identity=identity)
        except ExtensionFilesystemError:
            self.remove(category=category, identity=identity)

    def plugin_data_dir(self, identity: str) -> Path:
        return extension_data_path(root=self._root, identity=identity)

    def data_set_aside_dir(self) -> Path:
        """A fresh, not yet created folder for data an import moves aside (same filesystem)."""
        return self._recovery / f"data-{uuid4().hex}"

    def remove_plugin_data(self, identity: str) -> None:
        shutil.rmtree(self.plugin_data_dir(identity), ignore_errors=True)

    def scoped(self, workspace_id: str) -> "WorkspaceExtensionFilesystem":
        """The same operations on one workspace's files."""
        return WorkspaceExtensionFilesystem(self, workspace_id)

    def adopt_legacy(self, owners: dict[tuple[str, str], set[str]]) -> tuple[tuple[str, str, str], ...]:
        """Move pre-workspace trees and data into their workspace's layout.

        ``owners`` maps (category, identity), with category "data" for data folders, to
        the workspaces whose non-removed installs use that legacy path. A path moves only
        when exactly one workspace uses it and the target is free; anything else stays
        where it is (its installs are blocked as a storage conflict). ``os.replace`` makes
        each move atomic, so a crash leaves every folder either moved or untouched, and a
        second run finds nothing left to move. Returns the moves made.
        """
        moved: list[tuple[str, str, str]] = []
        for (category, identity), workspaces in sorted(owners.items()):
            if len(workspaces) != 1:
                continue
            (workspace_id,) = tuple(workspaces)
            scoped = workspace_storage_identity(workspace_id, identity)
            if category == "data":
                source = extension_data_path(root=self._root, identity=identity)
                target = extension_data_path(root=self._root, identity=scoped)
            else:
                source = extension_category_path(root=self._root, category=category, identity=identity)
                target = extension_category_path(root=self._root, category=category, identity=scoped)
            if not source.is_dir() or source.is_symlink() or target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.replace(source, target)
            moved.append((category, identity, workspace_id))
        return tuple(moved)

    def _component_base(self, category: str, identity: str) -> Path:
        return extension_category_path(root=self._root, category=category, identity=identity)

    @staticmethod
    def _write_record(path: Path, value: dict[str, object]) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)


def _reject_links(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ExtensionFilesystemError("extension tree contains a link")


class WorkspaceExtensionFilesystem:
    """ExtensionFilesystem for one workspace: every identity is mapped into that
    workspace's folder, so two workspaces never share an install tree or data folder."""

    def __init__(self, base: ExtensionFilesystem, workspace_id: str) -> None:
        self._base, self._workspace_id = base, workspace_id

    def _key(self, identity: str) -> str:
        return workspace_storage_identity(self._workspace_id, identity)

    def replace(self, *, category: str, identity: str, candidate_root: Path,
                exclude_root_names: frozenset[str] = frozenset()) -> InstalledTree:
        return self._base.replace(category=category, identity=self._key(identity),
                                  candidate_root=candidate_root, exclude_root_names=exclude_root_names)

    def rollback(self, *, category: str, identity: str) -> InstalledTree:
        return self._base.rollback(category=category, identity=self._key(identity))

    def remove(self, *, category: str, identity: str) -> None:
        self._base.remove(category=category, identity=self._key(identity))

    def revert(self, *, category: str, identity: str, had_active_install: bool) -> None:
        self._base.revert(category=category, identity=self._key(identity), had_active_install=had_active_install)

    def plugin_data_dir(self, identity: str) -> Path:
        return self._base.plugin_data_dir(self._key(identity))

    def data_set_aside_dir(self) -> Path:
        return self._base.data_set_aside_dir()

    def remove_plugin_data(self, identity: str) -> None:
        self._base.remove_plugin_data(self._key(identity))
