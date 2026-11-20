"""Quarantine extraction adapted from R1 plugins/archives.py (SHA in Phase 5 inventory)."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
import os
import shutil
import stat
import tarfile
from uuid import uuid4
import zipfile


MAX_UPLOAD_BYTES = 16 * 1024 * 1024
DEFAULT_LOCAL_API_MAX_BODY_BYTES = 134_217_728
# Raw archive limit for MCP package upload; matches default HTTP body after base64 decode.
MAX_MCP_PACKAGE_UPLOAD_BYTES = (DEFAULT_LOCAL_API_MAX_BODY_BYTES * 3) // 4
MAX_EXPANDED_BYTES = MAX_MCP_PACKAGE_UPLOAD_BYTES
MAX_ENTRY_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 512
MAX_COMPRESSION_RATIO = 100


class ArchiveRejected(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class QuarantinedArchive:
    candidate_id: str
    candidate_root: Path
    content_root: Path
    content_hash: str
    entries: tuple[str, ...]

    def discard(self) -> None:
        shutil.rmtree(self.candidate_root, ignore_errors=True)


class ArchiveInspector:
    def __init__(self, quarantine_root: Path) -> None:
        self._root = quarantine_root.resolve()

    def inspect(
        self, payload: bytes, filename: str, *, required_root_file: str,
        max_upload_bytes: int = MAX_UPLOAD_BYTES,
    ) -> QuarantinedArchive:
        if (
            not filename or Path(filename).name != filename or not payload
            or len(payload) > max_upload_bytes
        ):
            raise ArchiveRejected("extension upload is invalid")
        if required_root_file not in {"plugin.json", "SKILL.md", "mcp.package.json"}:
            raise ValueError("unsupported archive contract")
        entries = _read_entries(payload, filename)
        root_name = _one_root(entries, required_root_file)
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        candidate_root = (self._root / uuid4().hex).resolve()
        if not candidate_root.is_relative_to(self._root):
            raise ArchiveRejected("quarantine path is invalid")
        content_root = candidate_root / root_name
        try:
            candidate_root.mkdir(mode=0o700)
            for relative, content in entries:
                target = candidate_root.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                target.write_bytes(content)
                os.chmod(target, 0o600)
            return QuarantinedArchive(
                candidate_id=candidate_root.name,
                candidate_root=candidate_root,
                content_root=content_root,
                content_hash=_tree_hash(entries),
                entries=tuple(path.as_posix() for path, _ in entries),
            )
        except Exception:
            shutil.rmtree(candidate_root, ignore_errors=True)
            raise


def _read_entries(payload: bytes, filename: str) -> tuple[tuple[PurePosixPath, bytes], ...]:
    lower = filename.casefold()
    if lower.endswith(".zip"):
        return _zip_entries(payload)
    if lower.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz")):
        return _tar_entries(payload)
    raise ArchiveRejected("extension archive must be ZIP or TAR")


def _zip_entries(payload: bytes) -> tuple[tuple[PurePosixPath, bytes], ...]:
    try:
        archive = zipfile.ZipFile(BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ArchiveRejected("extension ZIP cannot be read") from exc
    entries: list[tuple[PurePosixPath, bytes]] = []
    expanded = 0
    with archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            _entry_count(entries)
            path = _safe_path(member.filename)
            mode = member.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if member.flag_bits & 1 or stat.S_ISLNK(mode) or (
                file_type not in {0, stat.S_IFREG}
            ):
                raise ArchiveRejected("extension ZIP contains an encrypted or special entry")
            if member.file_size > MAX_ENTRY_BYTES:
                raise ArchiveRejected("extension entry exceeds the size limit")
            if member.file_size and member.file_size / max(member.compress_size, 1) > MAX_COMPRESSION_RATIO:
                raise ArchiveRejected("extension archive compression ratio is unsafe")
            expanded += member.file_size
            _expanded_size(expanded)
            content = archive.read(member)
            if len(content) != member.file_size:
                raise ArchiveRejected("extension ZIP entry size changed while reading")
            entries.append((path, content))
    return _finish_entries(entries)


def _tar_entries(payload: bytes) -> tuple[tuple[PurePosixPath, bytes], ...]:
    try:
        archive = tarfile.open(fileobj=BytesIO(payload), mode="r:*")
    except tarfile.TarError as exc:
        raise ArchiveRejected("extension TAR cannot be read") from exc
    entries: list[tuple[PurePosixPath, bytes]] = []
    expanded = 0
    with archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            _entry_count(entries)
            path = _safe_path(member.name)
            if not member.isfile():
                raise ArchiveRejected("extension TAR contains a non-regular entry")
            if member.size > MAX_ENTRY_BYTES:
                raise ArchiveRejected("extension entry exceeds the size limit")
            expanded += member.size
            _expanded_size(expanded)
            source = archive.extractfile(member)
            content = source.read(MAX_ENTRY_BYTES + 1) if source else b""
            if len(content) != member.size:
                raise ArchiveRejected("extension TAR entry size changed while reading")
            entries.append((path, content))
    return _finish_entries(entries)


def _safe_path(raw: str) -> PurePosixPath:
    if "\\" in raw or "\x00" in raw:
        raise ArchiveRejected("extension archive has an unsafe path")
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ArchiveRejected("extension archive has an unsafe path")
    if ":" in path.parts[0]:
        raise ArchiveRejected("extension archive has an unsafe path")
    return path


def _entry_count(entries: list[object]) -> None:
    if len(entries) >= MAX_ENTRIES:
        raise ArchiveRejected("extension archive has too many entries")


def _expanded_size(total: int) -> None:
    if total > MAX_EXPANDED_BYTES:
        raise ArchiveRejected("extension archive expands beyond the size limit")


def _finish_entries(entries: list[tuple[PurePosixPath, bytes]]) -> tuple[tuple[PurePosixPath, bytes], ...]:
    if not entries:
        raise ArchiveRejected("extension archive is empty")
    folded = [path.as_posix().casefold() for path, _ in entries]
    if len(folded) != len(set(folded)):
        raise ArchiveRejected("extension archive has duplicate paths")
    return tuple(sorted(entries, key=lambda item: item[0].as_posix()))


def _one_root(entries: tuple[tuple[PurePosixPath, bytes], ...], required: str) -> str:
    roots = {path.parts[0] for path, _ in entries}
    if len(roots) != 1:
        raise ArchiveRejected("extension archive must contain exactly one root directory")
    root = next(iter(roots))
    if not any(path == PurePosixPath(root, required) for path, _ in entries):
        raise ArchiveRejected(f"extension archive requires root {required}")
    return root


def _tree_hash(entries: tuple[tuple[PurePosixPath, bytes], ...]) -> str:
    digest = sha256()
    for path, content in entries:
        encoded = path.as_posix().encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()
