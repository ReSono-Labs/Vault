from __future__ import annotations

from dataclasses import dataclass
from mimetypes import guess_type
from pathlib import PurePosixPath
from typing import Any

from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.workspace_files.errors import (
    WorkspaceFileBadRequestError as BadRequestError,
    WorkspaceFileConflictError as ConflictError,
    WorkspaceFileNotFoundError as NotFoundError,
)
from app.vault_runtime.workspace_files.models import (
    WorkspaceFileDirectory,
    WorkspaceFileEntry,
    WorkspaceFileMutation,
    WorkspaceFileRead,
)
from app.vault_runtime.workspace_files.repository import is_reserved_workspace_file_key
from app.vault_runtime.workspace_files.store import WorkspaceFilesystemStore, WorkspaceStoredEntry
from app.vault_runtime.workspace_paths import (
    UnsafeWorkspacePathError,
    normalize_workspace_file_key,
    normalize_workspace_file_prefix,
)

WORKSPACE_TEXT_CONTENT_MAX_LENGTH = 32 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class WorkspaceFileUpload:
    filename: str
    content: bytes
    mime_type: str | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceFileScope:
    workspace_id: str
    permission: str
    share_id: str | None = None
    share_root: str = ""


class WorkspaceFileManagerService:
    _MAX_UPLOAD_BYTES = 128 * 1024 * 1024
    _MAX_UPLOAD_REQUEST_BYTES = 128 * 1024 * 1024
    _TEXT_EDITABLE_CONTENT_MAX_BYTES = WORKSPACE_TEXT_CONTENT_MAX_LENGTH
    _TEXT_EDITABLE_EXTENSIONS = {
        "",
        ".csv",
        ".json",
        ".jsonl",
        ".markdown",
        ".md",
        ".rtf",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
    _STRUCTURED_BINARY_DOCUMENT_EXTENSIONS = {
        ".doc",
        ".docx",
        ".odp",
        ".ods",
        ".odt",
        ".pdf",
        ".ppt",
        ".pptx",
        ".xls",
        ".xlsx",
    }
    _BLOCKED_DOCUMENT_EXTENSIONS = {
        ".app",
        ".apk",
        ".bat",
        ".bin",
        ".bash",
        ".c",
        ".class",
        ".cmd",
        ".com",
        ".cpp",
        ".cjs",
        ".deb",
        ".dll",
        ".dylib",
        ".elf",
        ".exe",
        ".fish",
        ".go",
        ".h",
        ".hpp",
        ".htm",
        ".html",
        ".jar",
        ".java",
        ".js",
        ".jsx",
        ".kt",
        ".lua",
        ".mjs",
        ".msi",
        ".php",
        ".pl",
        ".ps1",
        ".py",
        ".pyc",
        ".rb",
        ".rpm",
        ".rs",
        ".run",
        ".sh",
        ".so",
        ".swift",
        ".ts",
        ".tsx",
        ".war",
        ".zsh",
    }
    _ALLOWED_DOCUMENT_EXTENSIONS = {
        ".7z",
        ".csv",
        ".doc",
        ".docx",
        ".gif",
        ".gz",
        ".heic",
        ".heif",
        ".jpeg",
        ".jpg",
        ".json",
        ".jsonl",
        ".md",
        ".markdown",
        ".odp",
        ".ods",
        ".odt",
        ".pdf",
        ".png",
        ".ppt",
        ".pptx",
        ".rar",
        ".rtf",
        ".tar",
        ".tif",
        ".tiff",
        ".txt",
        ".webp",
        ".xls",
        ".xlsx",
        ".xml",
        ".yaml",
        ".yml",
        ".zip",
    }
    _ALLOWED_DOCUMENT_MIME_TYPES = {
        "application/gzip",
        "application/json",
        "application/ld+json",
        "application/msword",
        "application/octet-stream",
        "application/onenote",
        "application/pdf",
        "application/rtf",
        "application/vnd.ms-excel",
        "application/vnd.ms-powerpoint",
        "application/vnd.oasis.opendocument.presentation",
        "application/vnd.oasis.opendocument.spreadsheet",
        "application/vnd.oasis.opendocument.text",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/x-7z-compressed",
        "application/x-bzip2",
        "application/x-gzip",
        "application/x-ndjson",
        "application/x-rar-compressed",
        "application/x-tar",
        "application/x-yaml",
        "application/xml",
        "application/yaml",
        "application/zip",
        "image/gif",
        "image/heic",
        "image/heif",
        "image/jpeg",
        "image/png",
        "image/tiff",
        "image/webp",
        "text/csv",
        "text/markdown",
        "text/plain",
        "text/rtf",
        "text/tab-separated-values",
        "text/xml",
        "text/yaml",
    }
    _EXECUTABLE_MAGIC_HEADERS = (
        b"#!",
        b"MZ",
        b"\x7fELF",
        b"\xca\xfe\xba\xbe",
        b"\xce\xfa\xed\xfe",
        b"\xcf\xfa\xed\xfe",
        b"\xfe\xed\xfa\xce",
        b"\xfe\xed\xfa\xcf",
    )

    def __init__(self, store: WorkspaceFilesystemStore) -> None:
        self._store = store

    def workspace_root_info(self, *, actor: LocalPrincipal) -> dict[str, str]:
        workspace_id = self._require_workspace_id(actor=actor)
        return self._store.logical_root_description(workspace_id=workspace_id)

    def list_directory(
        self,
        *,
        actor: LocalPrincipal,
        directory: str | None,
        include_reserved: bool = False,
    ) -> WorkspaceFileDirectory:
        workspace_id = self._require_workspace_id(actor=actor)
        current_directory = normalize_workspace_file_prefix(directory)
        display_directory, stored_entries = self._store.list_directory(
            workspace_id=workspace_id,
            directory=current_directory,
        )
        directory_entries: dict[str, dict[str, Any]] = {}
        file_entries: list[WorkspaceFileEntry] = []

        for entry in stored_entries:
            if not include_reserved and is_reserved_workspace_file_key(entry.file_key):
                continue
            relative_name = PurePosixPath(entry.file_key).name
            if entry.entry_kind == "directory":
                directory_path = entry.file_key
                directory_entries[directory_path.casefold()] = {
                    "name": relative_name,
                    "path": directory_path,
                    "child_count": None,
                    "updated_at": entry.updated_at,
                }
                continue
            file_entries.append(self._entry_to_model(entry=entry, name=relative_name, path=entry.file_key))

        entries = [
            WorkspaceFileEntry(
                kind="directory",
                name=item["name"],
                path=item["path"],
                childCount=item["child_count"],
                updatedAt=item["updated_at"],
            )
            for item in sorted(directory_entries.values(), key=lambda value: value["path"])
        ]
        entries.extend(sorted(file_entries, key=lambda item: item.name.lower()))
        return WorkspaceFileDirectory(
            currentDirectory=display_directory,
            parentDirectory=self._parent_directory(display_directory),
            entries=entries,
        )

    def read_file(
        self,
        *,
        actor: LocalPrincipal,
        file_key: str,
        include_reserved: bool = False,
    ) -> WorkspaceFileRead:
        workspace_id = self._require_workspace_id(actor=actor)
        self._ensure_user_accessible_file_key(file_key, include_reserved=include_reserved)
        try:
            entry, content = self._store.read_text(workspace_id=workspace_id, file_key=file_key)
        except ConflictError:
            entry = self._store.read_file(workspace_id=workspace_id, file_key=file_key)
            content = ""
        return WorkspaceFileRead(
            fileKey=entry.file_key,
            filename=PurePosixPath(entry.file_key).name,
            contentMarkdown=content,
            sizeBytes=entry.size_bytes,
            mimeType=entry.mime_type,
            editable=self._is_editable_entry(entry=entry),
            projectionVersion=self._entry_version(entry),
            updatedAt=entry.updated_at,
        )

    def read_file_bytes(
        self,
        *,
        actor: LocalPrincipal,
        file_key: str,
        include_reserved: bool = False,
    ) -> tuple[str, str, bytes]:
        workspace_id = self._require_workspace_id(actor=actor)
        self._ensure_user_accessible_file_key(file_key, include_reserved=include_reserved)
        return self._store.read_file_bytes(workspace_id=workspace_id, file_key=file_key)

    def save_file(
        self,
        *,
        actor: LocalPrincipal,
        payload: dict[str, Any],
    ) -> WorkspaceFileMutation:
        workspace_id = self._require_workspace_id(actor=actor)
        file_key = str(payload["fileKey"])
        self._ensure_user_accessible_file_key(file_key)
        self._ensure_text_save_file_key_allowed(file_key)
        content = str(payload["contentMarkdown"])
        if len(content.encode("utf-8")) > self._TEXT_EDITABLE_CONTENT_MAX_BYTES:
            raise ConflictError("That workspace file is not text-editable.")
        self._store.write_text(workspace_id=workspace_id, file_key=file_key, content=content)
        return WorkspaceFileMutation(
            status="completed",
            message="Workspace file saved.",
            affectedCount=1,
            path=file_key,
        )

    def write_text_file(
        self,
        *,
        actor: LocalPrincipal,
        file_key: str,
        content_markdown: str,
        overwrite_existing: bool,
    ) -> WorkspaceFileMutation:
        workspace_id = self._require_workspace_id(actor=actor)
        normalized_key = normalize_workspace_file_key(file_key)
        self._ensure_user_accessible_file_key(normalized_key)
        self._ensure_text_save_file_key_allowed(normalized_key)
        filename = PurePosixPath(normalized_key).name
        content_bytes = content_markdown.encode("utf-8")
        mime_type = self._resolve_mime_type(filename=filename, provided=None)
        if not self._filename_extension(filename) and mime_type == "application/octet-stream":
            mime_type = "text/plain"
        self._ensure_document_upload_allowed(
            filename=filename,
            mime_type=mime_type,
            content=content_bytes,
        )
        if not self._is_text_mime_type(mime_type):
            mime_type = "text/plain" if filename.endswith(".txt") else "text/markdown"
        try:
            self._store.read_file(workspace_id=workspace_id, file_key=normalized_key)
            existing = True
        except NotFoundError:
            existing = False
        if existing and not overwrite_existing:
            raise ConflictError("A workspace file already exists at that path.")
        self._store.write_text(
            workspace_id=workspace_id,
            file_key=normalized_key,
            content=content_markdown,
            mime_type=mime_type,
        )
        return WorkspaceFileMutation(
            status="completed",
            message="Workspace file saved." if existing else "Workspace file created.",
            affectedCount=1,
            path=normalized_key,
        )

    def create_directory(
        self,
        *,
        actor: LocalPrincipal,
        payload: dict[str, Any],
    ) -> WorkspaceFileMutation:
        workspace_id = self._require_workspace_id(actor=actor)
        directory = normalize_workspace_file_prefix(payload["directory"])
        if not directory:
            raise BadRequestError("Directory path is required.")
        self._ensure_user_accessible_file_key(directory)
        self._store.create_directory(workspace_id=workspace_id, directory=directory)
        return WorkspaceFileMutation(
            status="completed",
            message="Workspace folder created.",
            affectedCount=1,
            path=directory,
        )

    def upload_files(
        self,
        *,
        actor: LocalPrincipal,
        directory: str | None,
        uploads: list[WorkspaceFileUpload],
    ) -> WorkspaceFileMutation:
        workspace_id = self._require_workspace_id(actor=actor)
        current_directory = normalize_workspace_file_prefix(directory)
        if not uploads:
            raise BadRequestError("At least one file is required.")
        total_bytes = sum(len(upload.content) for upload in uploads)
        if total_bytes > self._MAX_UPLOAD_REQUEST_BYTES:
            raise BadRequestError("Workspace uploads are limited to 128 MB per request.")
        uploaded_paths: list[str] = []
        for upload in uploads:
            filename = self._normalize_upload_filename(upload.filename)
            file_key = normalize_workspace_file_key(
                f"{current_directory}/{filename}" if current_directory else filename
            )
            self._ensure_user_accessible_file_key(file_key)
            mime_type = self._resolve_mime_type(filename=filename, provided=upload.mime_type)
            self._ensure_document_upload_allowed(
                filename=filename,
                mime_type=mime_type,
                content=upload.content,
            )
            self._store.write_bytes(
                workspace_id=workspace_id,
                file_key=file_key,
                content=upload.content,
                mime_type=mime_type,
            )
            uploaded_paths.append(file_key)
        return WorkspaceFileMutation(
            status="completed",
            message=f"Uploaded {len(uploaded_paths)} workspace file{'s' if len(uploaded_paths) != 1 else ''}.",
            affectedCount=len(uploaded_paths),
            path=current_directory or None,
            destinationPath=uploaded_paths[0] if len(uploaded_paths) == 1 else None,
        )

    def move_path(
        self,
        *,
        actor: LocalPrincipal,
        payload: dict[str, Any],
    ) -> WorkspaceFileMutation:
        workspace_id = self._require_workspace_id(actor=actor)
        source_path = str(payload["sourcePath"])
        destination_path = str(payload["destinationPath"])
        self._ensure_user_accessible_file_key(source_path)
        self._ensure_user_accessible_file_key(destination_path)
        affected = self._store.move_path(
            workspace_id=workspace_id,
            source_path=source_path,
            destination_path=destination_path,
        )
        source_file_key = self._normalize_possible_file_key(source_path)
        if source_file_key is not None and affected == 1:
            return WorkspaceFileMutation(
                status="completed",
                message="Workspace file moved.",
                affectedCount=1,
                path=source_path,
                destinationPath=destination_path,
            )
        return WorkspaceFileMutation(
            status="completed",
            message="Workspace folder moved.",
            affectedCount=affected,
            path=normalize_workspace_file_prefix(source_path),
            destinationPath=normalize_workspace_file_prefix(destination_path),
        )

    def delete_path(
        self,
        *,
        actor: LocalPrincipal,
        payload: dict[str, Any],
    ) -> WorkspaceFileMutation:
        workspace_id = self._require_workspace_id(actor=actor)
        path = str(payload["path"])
        self._ensure_user_accessible_file_key(path)
        affected = self._store.delete_path(
            workspace_id=workspace_id,
            path=path,
            recursive=bool(payload.get("recursive", False)),
        )
        source_file_key = self._normalize_possible_file_key(path)
        if source_file_key is not None and affected == 1:
            return WorkspaceFileMutation(
                status="completed",
                message="Workspace file deleted.",
                affectedCount=1,
                path=path,
            )
        return WorkspaceFileMutation(
            status="completed",
            message="Workspace folder deleted.",
            affectedCount=affected,
            path=normalize_workspace_file_prefix(path),
        )

    def build_directory_archive(
        self,
        *,
        actor: LocalPrincipal,
        directory: str | None,
    ) -> tuple[str, bytes]:
        workspace_id = self._require_workspace_id(actor=actor)
        current_directory = normalize_workspace_file_prefix(directory)
        return self._store.build_directory_archive(
            workspace_id=workspace_id,
            directory=current_directory,
        )

    def _entry_to_model(
        self,
        *,
        entry: WorkspaceStoredEntry,
        name: str,
        path: str,
    ) -> WorkspaceFileEntry:
        editable = entry.entry_kind == "file" and self._is_editable_entry(entry=entry)
        return WorkspaceFileEntry(
            kind=entry.entry_kind,
            name=name,
            path=path,
            sizeBytes=entry.size_bytes,
            mimeType=entry.mime_type,
            editable=editable,
            projectionVersion=self._entry_version(entry),
            updatedAt=entry.updated_at,
        )

    @staticmethod
    def _entry_version(entry: WorkspaceStoredEntry) -> int:
        return int(entry.updated_at.timestamp())

    @classmethod
    def _ensure_document_upload_allowed(cls, *, filename: str, mime_type: str, content: bytes) -> None:
        if len(content) > cls._MAX_UPLOAD_BYTES:
            raise BadRequestError("Workspace uploads are limited to 128 MB per file.")
        extension = cls._filename_extension(filename)
        if extension in cls._BLOCKED_DOCUMENT_EXTENSIONS or cls._has_executable_signature(content):
            raise BadRequestError(
                "Workspace uploads are limited to documents, media, and archives. "
                "Executable and script files are not allowed."
            )
        if extension and extension not in cls._ALLOWED_DOCUMENT_EXTENSIONS:
            raise BadRequestError("Workspace uploads are limited to documents, media, and archives.")
        if not cls._is_allowed_document_mime_type(mime_type):
            raise BadRequestError("Workspace uploads are limited to documents, media, and archives.")
        if not extension and mime_type == "application/octet-stream" and not cls._looks_plain_document_content(content):
            raise BadRequestError("Workspace uploads without a document extension must be plain text.")

    @staticmethod
    def _filename_extension(filename: str) -> str:
        name = PurePosixPath(filename).name.lower()
        suffixes = PurePosixPath(name).suffixes
        if suffixes and suffixes[-1] in {".gz", ".bz2", ".xz"} and len(suffixes) >= 2:
            return "".join(suffixes[-2:])
        return suffixes[-1] if suffixes else ""

    @classmethod
    def _has_executable_signature(cls, content: bytes) -> bool:
        sample = content[:16]
        return any(sample.startswith(header) for header in cls._EXECUTABLE_MAGIC_HEADERS)

    @staticmethod
    def _looks_plain_document_content(content: bytes) -> bool:
        sample = content[:4096]
        if b"\x00" in sample:
            return False
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return True

    @classmethod
    def _is_allowed_document_mime_type(cls, mime_type: str) -> bool:
        lowered = (mime_type or "").lower()
        if lowered in cls._ALLOWED_DOCUMENT_MIME_TYPES:
            return True
        return lowered.startswith("image/") and lowered != "image/svg+xml"

    @classmethod
    def _is_editable_entry(cls, *, entry: WorkspaceStoredEntry) -> bool:
        if entry.entry_kind != "file":
            return False
        extension = cls._filename_extension(entry.file_key)
        if extension in cls._STRUCTURED_BINARY_DOCUMENT_EXTENSIONS:
            return False
        mime_type = (entry.mime_type or "").lower()
        if not cls._is_text_mime_type(mime_type):
            return False
        return entry.size_bytes <= cls._TEXT_EDITABLE_CONTENT_MAX_BYTES

    @classmethod
    def _ensure_text_save_file_key_allowed(cls, file_key: str) -> None:
        extension = cls._filename_extension(file_key)
        if extension not in cls._TEXT_EDITABLE_EXTENSIONS:
            raise BadRequestError(
                "Workspace text saves are limited to plain text document formats. "
                "Use Document Editor for DOCX edits."
            )

    @staticmethod
    def _normalize_upload_filename(filename: str) -> str:
        raw = str(filename or "").strip().replace("\\", "/")
        if not raw:
            raise BadRequestError("Uploaded file name is required.")
        name = PurePosixPath(raw).name
        if not name or name in {".", ".."}:
            raise BadRequestError("Uploaded file name is invalid.")
        return name

    @staticmethod
    def _resolve_mime_type(*, filename: str, provided: str | None) -> str:
        normalized = (provided or "").split(";", 1)[0].strip().lower()
        if normalized:
            return normalized
        guessed, _ = guess_type(filename)
        return (guessed or "application/octet-stream").lower()

    @staticmethod
    def _is_text_mime_type(mime_type: str) -> bool:
        lowered = (mime_type or "").lower()
        if lowered in {
            "text/plain",
            "text/markdown",
            "text/csv",
            "text/tab-separated-values",
            "text/xml",
            "text/yaml",
            "text/rtf",
        }:
            return True
        return lowered in {
            "application/json",
            "application/ld+json",
            "application/rtf",
            "application/xml",
            "application/yaml",
            "application/x-yaml",
            "application/x-ndjson",
        }

    @staticmethod
    def _normalize_possible_file_key(path: str) -> str | None:
        try:
            return normalize_workspace_file_key(path)
        except (BadRequestError, UnsafeWorkspacePathError, ValueError):
            return None

    @staticmethod
    def _ensure_user_accessible_file_key(file_key: str, *, include_reserved: bool = False) -> None:
        if include_reserved or not is_reserved_workspace_file_key(file_key):
            return
        raise NotFoundError("That workspace file was not found.")

    @staticmethod
    def _parent_directory(current_directory: str) -> str | None:
        if not current_directory:
            return None
        parent = PurePosixPath(current_directory).parent.as_posix()
        return "" if parent == "." else parent

    @staticmethod
    def _require_workspace_id(*, actor: LocalPrincipal) -> str:
        if not actor.workspace_id:
            raise BadRequestError("A workspace context is required.")
        return actor.workspace_id
