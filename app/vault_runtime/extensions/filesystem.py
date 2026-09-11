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

    def remove_plugin_data(self, identity: str) -> None:
        shutil.rmtree(self.plugin_data_dir(identity), ignore_errors=True)

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
