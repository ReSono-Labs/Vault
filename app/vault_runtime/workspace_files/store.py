from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from mimetypes import guess_type
from pathlib import Path, PurePosixPath

from app.vault_runtime.workspace_files.constants import WORKSPACE_FILES_DIRECTORY
from app.vault_runtime.workspace_files.errors import (
    WorkspaceFileBadRequestError as BadRequestError,
    WorkspaceFileConflictError as ConflictError,
    WorkspaceFileNotFoundError as NotFoundError,
)
from app.vault_runtime.workspace_paths import (
    UnsafeWorkspacePathError,
    normalize_workspace_file_key,
    normalize_workspace_file_prefix,
    resolve_workspace_staging_path,
)
from app.vault_runtime.workspace_storage import WorkspaceStorage


@dataclass(frozen=True, slots=True)
class WorkspaceStoredEntry:
    file_key: str
    entry_kind: str
    mime_type: str | None
    size_bytes: int
    updated_at: datetime
    content_hash: str


class WorkspaceFilesystemStore:
    """Authoritative workspace file storage on disk under each workspace files root."""

    def __init__(self, storage: WorkspaceStorage, *, private_user_id: str | None = None) -> None:
        self._storage = storage
        self._private_user_id = private_user_id

    def files_root(self, *, workspace_id: str) -> Path:
        if self._private_user_id is None:
            root = self._storage.workspace_root(workspace_id) / WORKSPACE_FILES_DIRECTORY
        else:
            # Same managed-file operations, separate private namespace. Inputs
            # never appear in the workspace browser or another member's files.
            self._storage.workspace_root(workspace_id)  # Validate the scope identifier.
            user_root = self._storage.user_root(self._private_user_id)
            if not user_root.is_dir() or user_root.is_symlink():
                raise BadRequestError("Private input storage is unavailable.")
            parent = user_root / "conversation-inputs"
            parent.mkdir(mode=0o700, exist_ok=True)
            if parent.is_symlink():
                raise BadRequestError("Private input storage is unavailable.")
            root = parent / workspace_id
        root.mkdir(mode=0o700, exist_ok=True)
        if root.is_symlink():
            raise BadRequestError("Workspace files root is unavailable.")
        return root

    def logical_root_description(self, *, workspace_id: str) -> dict[str, str]:
        files_root = self.files_root(workspace_id=workspace_id)
        return {
            "workspaceId": workspace_id,
            "filesRoot": WORKSPACE_FILES_DIRECTORY,
            "hostPath": str(files_root),
            "pathStyle": "relative",
        }

    def list_directory(
        self,
        *,
        workspace_id: str,
        directory: str,
    ) -> tuple[str, list[WorkspaceStoredEntry]]:
        files_root = self.files_root(workspace_id=workspace_id)
        display_directory = self._resolve_existing_directory_key(
            files_root=files_root,
            directory=directory,
        )
        base = self._directory_path(files_root=files_root, directory=display_directory)
        if not base.exists():
            raise NotFoundError("That workspace folder was not found.")
        if not base.is_dir():
            raise NotFoundError("That workspace folder was not found.")
        entries: list[WorkspaceStoredEntry] = []
        for child in sorted(base.iterdir(), key=lambda item: item.name.lower()):
            if child.name.startswith("."):
                continue
            file_key = self._path_to_file_key(files_root=files_root, path=child)
            entries.append(self._entry_from_path(files_root=files_root, path=child, file_key=file_key))
        return display_directory, entries

    def read_file(
        self,
        *,
        workspace_id: str,
        file_key: str,
    ) -> WorkspaceStoredEntry:
        files_root = self.files_root(workspace_id=workspace_id)
        path, resolved_key = self._resolve_existing_file_path(files_root=files_root, file_key=file_key)
        if not path.is_file():
            raise NotFoundError("That workspace file was not found.")
        stat = path.stat()
        content = path.read_bytes()
        return WorkspaceStoredEntry(
            file_key=resolved_key,
            entry_kind="file",
            mime_type=self._mime_type(resolved_key),
            size_bytes=stat.st_size,
            updated_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            content_hash=sha256(content).hexdigest(),
        )

    def read_file_bytes(
        self,
        *,
        workspace_id: str,
        file_key: str,
        max_bytes: int | None = None,
    ) -> tuple[str, str, bytes]:
        files_root = self.files_root(workspace_id=workspace_id)
        path, resolved_key = self._resolve_existing_file_path(files_root=files_root, file_key=file_key)
        if not path.is_file():
            raise NotFoundError("That workspace file was not found.")
        if max_bytes is not None:
            if type(max_bytes) is not int or max_bytes<1:
                raise BadRequestError("A positive file read limit is required.")
            with path.open('rb') as stream:
                content=stream.read(max_bytes+1)
            if len(content)>max_bytes:
                raise ConflictError("Stored file exceeds its input size limit.")
        else:
            content = path.read_bytes()
        return PurePosixPath(resolved_key).name, self._mime_type(resolved_key), content

    def read_text(
        self,
        *,
        workspace_id: str,
        file_key: str,
    ) -> tuple[WorkspaceStoredEntry, str]:
        entry = self.read_file(workspace_id=workspace_id, file_key=file_key)
        _, _, content = self.read_file_bytes(workspace_id=workspace_id, file_key=entry.file_key)
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ConflictError("That workspace file is not text-readable.") from exc
        return entry, text

    def write_bytes(
        self,
        *,
        workspace_id: str,
        file_key: str,
        content: bytes,
        mime_type: str | None = None,
    ) -> WorkspaceStoredEntry:
        files_root = self.files_root(workspace_id=workspace_id)
        normalized_key = normalize_workspace_file_key(file_key)
        path = resolve_workspace_staging_path(workspace_root=files_root, file_key=normalized_key)
        if path.exists() and path.is_dir():
            raise ConflictError("A workspace folder already exists at that path.")
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            target.write(content)
        return self.read_file(workspace_id=workspace_id, file_key=normalized_key)

    def write_text(
        self,
        *,
        workspace_id: str,
        file_key: str,
        content: str,
        mime_type: str | None = None,
    ) -> WorkspaceStoredEntry:
        return self.write_bytes(
            workspace_id=workspace_id,
            file_key=file_key,
            content=content.encode("utf-8"),
            mime_type=mime_type,
        )

    def create_directory(
        self,
        *,
        workspace_id: str,
        directory: str,
    ) -> WorkspaceStoredEntry:
        files_root = self.files_root(workspace_id=workspace_id)
        normalized = normalize_workspace_file_prefix(directory)
        if not normalized:
            raise BadRequestError("Directory path is required.")
        path = resolve_workspace_staging_path(workspace_root=files_root, file_key=normalized)
        if path.exists():
            if path.is_dir():
                raise ConflictError("A workspace folder already exists at that path.")
            raise ConflictError("A workspace file already exists at that path.")
        path.mkdir(parents=True, mode=0o700, exist_ok=False)
        stat = path.stat()
        return WorkspaceStoredEntry(
            file_key=normalized,
            entry_kind="directory",
            mime_type=None,
            size_bytes=0,
            updated_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            content_hash=sha256(b"").hexdigest(),
        )

    def move_path(
        self,
        *,
        workspace_id: str,
        source_path: str,
        destination_path: str,
    ) -> int:
        files_root = self.files_root(workspace_id=workspace_id)
        source_file_key = self._normalize_possible_file_key(source_path)
        if source_file_key is not None:
            source, resolved_source = self._resolve_existing_file_path(
                files_root=files_root,
                file_key=source_file_key,
            )
            if source.is_file():
                destination_key = normalize_workspace_file_key(destination_path)
                destination = resolve_workspace_staging_path(
                    workspace_root=files_root,
                    file_key=destination_key,
                )
                if destination.exists():
                    raise ConflictError("A workspace item already exists at that destination.")
                destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                shutil.move(str(source), str(destination))
                return 1

        source_prefix = normalize_workspace_file_prefix(source_path)
        destination_prefix = normalize_workspace_file_prefix(destination_path)
        if not source_prefix or not destination_prefix:
            raise BadRequestError("Source and destination folders are required.")
        if destination_prefix == source_prefix or destination_prefix.startswith(f"{source_prefix}/"):
            raise BadRequestError("A folder cannot be moved inside itself.")
        source_dir = self._directory_path(files_root=files_root, directory=source_prefix)
        destination_dir = resolve_workspace_staging_path(
            workspace_root=files_root,
            file_key=destination_prefix,
        )
        if not source_dir.is_dir():
            raise NotFoundError("That workspace folder was not found.")
        if destination_dir.exists():
            raise ConflictError("A workspace folder already exists at that destination.")
        destination_dir.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        shutil.move(str(source_dir), str(destination_dir))
        return self._count_entries(files_root=files_root, directory=destination_prefix)

    def delete_path(
        self,
        *,
        workspace_id: str,
        path: str,
        recursive: bool,
    ) -> int:
        files_root = self.files_root(workspace_id=workspace_id)
        source_file_key = self._normalize_possible_file_key(path)
        if source_file_key is not None:
            target, _resolved = self._resolve_existing_file_path(
                files_root=files_root,
                file_key=source_file_key,
            )
            if target.is_file():
                target.unlink()
                return 1

        source_prefix = normalize_workspace_file_prefix(path)
        if not source_prefix:
            raise BadRequestError("The workspace root cannot be deleted.")
        target_dir = self._directory_path(files_root=files_root, directory=source_prefix)
        if not target_dir.exists():
            raise NotFoundError("That workspace folder was not found.")
        if not recursive:
            raise BadRequestError("Folder deletion requires recursive confirmation.")
        affected = self._count_entries(files_root=files_root, directory=source_prefix)
        shutil.rmtree(target_dir)
        return affected

    def build_directory_archive(
        self,
        *,
        workspace_id: str,
        directory: str,
    ) -> tuple[str, bytes]:
        from io import BytesIO
        from zipfile import ZIP_DEFLATED, ZipFile

        files_root = self.files_root(workspace_id=workspace_id)
        display_directory = self._resolve_existing_directory_key(
            files_root=files_root,
            directory=directory,
        )
        base = self._directory_path(files_root=files_root, directory=display_directory)
        if not base.exists() or not base.is_dir():
            raise NotFoundError("That workspace folder was not found or is empty.")
        archive_buffer = BytesIO()
        file_count = 0
        with ZipFile(archive_buffer, mode="w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(base.rglob("*")):
                if not path.is_file() or path.name.startswith("."):
                    continue
                file_key = self._path_to_file_key(files_root=files_root, path=path)
                archive.writestr(file_key, path.read_bytes())
                file_count += 1
        if file_count == 0:
            raise NotFoundError("That workspace folder was not found or is empty.")
        filename = f"{(PurePosixPath(display_directory).name if display_directory else 'workspace-files')}.zip"
        return filename, archive_buffer.getvalue()

    def import_legacy_projection(
        self,
        *,
        workspace_id: str,
        file_key: str,
        entry_kind: str,
        content_markdown: str,
        content_bytes: bytes | None,
    ) -> None:
        files_root = self.files_root(workspace_id=workspace_id)
        if entry_kind == "directory":
            path = resolve_workspace_staging_path(workspace_root=files_root, file_key=file_key)
            path.mkdir(parents=True, mode=0o700, exist_ok=True)
            return
        payload = content_bytes if content_bytes is not None else content_markdown.encode("utf-8")
        self.write_bytes(workspace_id=workspace_id, file_key=file_key, content=payload)

    @staticmethod
    def _mime_type(file_key: str) -> str:
        guessed, _ = guess_type(file_key)
        return (guessed or "application/octet-stream").lower()

    @staticmethod
    def _normalize_possible_file_key(path: str) -> str | None:
        try:
            return normalize_workspace_file_key(path)
        except (BadRequestError, UnsafeWorkspacePathError, ValueError):
            return None

    def _directory_path(self, *, files_root: Path, directory: str) -> Path:
        if not directory:
            return files_root
        return resolve_workspace_staging_path(workspace_root=files_root, file_key=directory)

    def _path_to_file_key(self, *, files_root: Path, path: Path) -> str:
        relative = path.relative_to(files_root.resolve(strict=False))
        return relative.as_posix()

    def _entry_from_path(
        self,
        *,
        files_root: Path,
        path: Path,
        file_key: str,
    ) -> WorkspaceStoredEntry:
        stat = path.stat()
        if path.is_dir():
            return WorkspaceStoredEntry(
                file_key=file_key,
                entry_kind="directory",
                mime_type=None,
                size_bytes=0,
                updated_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                content_hash=sha256(b"").hexdigest(),
            )
        content = path.read_bytes()
        return WorkspaceStoredEntry(
            file_key=file_key,
            entry_kind="file",
            mime_type=self._mime_type(file_key),
            size_bytes=stat.st_size,
            updated_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            content_hash=sha256(content).hexdigest(),
        )

    def _resolve_existing_directory_key(self, *, files_root: Path, directory: str) -> str:
        normalized = normalize_workspace_file_prefix(directory)
        if not normalized:
            return ""
        parts = PurePosixPath(normalized).parts
        current = files_root
        resolved_parts: list[str] = []
        for part in parts:
            if not current.is_dir():
                raise NotFoundError("That workspace folder was not found.")
            match = self._case_insensitive_child(current, part)
            if match is None:
                raise NotFoundError("That workspace folder was not found.")
            resolved_parts.append(match.name)
            current = match
        return "/".join(resolved_parts)

    def _resolve_existing_file_path(
        self,
        *,
        files_root: Path,
        file_key: str,
    ) -> tuple[Path, str]:
        normalized = normalize_workspace_file_key(file_key)
        try:
            candidate = resolve_workspace_staging_path(workspace_root=files_root, file_key=normalized)
        except UnsafeWorkspacePathError as exc:
            raise BadRequestError(str(exc)) from exc
        if candidate.exists():
            return candidate, self._path_to_file_key(files_root=files_root, path=candidate)
        parent_key = PurePosixPath(normalized).parent.as_posix()
        parent = files_root if parent_key in {"", "."} else self._directory_path(
            files_root=files_root,
            directory=self._resolve_existing_directory_key(files_root=files_root, directory=parent_key),
        )
        match = self._case_insensitive_child(parent, PurePosixPath(normalized).name)
        if match is None:
            raise NotFoundError("That workspace file was not found.")
        resolved_key = self._path_to_file_key(files_root=files_root, path=match)
        return match, resolved_key

    @staticmethod
    def _case_insensitive_child(directory: Path, name: str) -> Path | None:
        folded = name.casefold()
        matches = [child for child in directory.iterdir() if child.name.casefold() == folded]
        if not matches:
            return None
        if len(matches) > 1:
            raise ConflictError("That workspace path is ambiguous.")
        return matches[0]

    def _count_entries(self, *, files_root: Path, directory: str) -> int:
        base = self._directory_path(files_root=files_root, directory=directory)
        count = 0
        for path in base.rglob("*"):
            if path.is_file() or path.is_dir():
                count += 1
        return max(count, 1)

