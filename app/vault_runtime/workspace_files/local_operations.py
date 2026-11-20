"""local/{name}/... paths: the user's host folders, read and written on the server.

Each call resolves the folder again through FolderService (grant, folder and
path checks), then runs the normal workspace file engine over that folder's
directory and maps paths back to local/{name}/...
"""

from __future__ import annotations

from dataclasses import replace

from app.vault_runtime.folders.errors import FolderOutsideAccessError, FolderWriteNotAllowedError
from app.vault_runtime.folders.models import FolderAccess
from app.vault_runtime.folders.paths import resolve_inside
from app.vault_runtime.folders.search import FolderSearchHit, SearchOptions, ripgrep, search_folder
from app.vault_runtime.folders.service import FolderService
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.workspace_files.local_paths import (
    LOCAL_FILES_ROOT,
    build_local_mount_path,
    join_local_view_path,
)
from app.vault_runtime.workspace_files.manager import WorkspaceFileManagerService, WorkspaceFileUpload
from app.vault_runtime.workspace_files.models import (
    WorkspaceFileDirectory,
    WorkspaceFileEntry,
    WorkspaceFileMutation,
    WorkspaceFileRead,
)
from app.vault_runtime.workspace_files.store import WorkspaceFilesystemStore


class LocalFilesystemBridge:
    def __init__(self, *, folders: FolderService | None) -> None:
        self._folders = folders

    def is_available(self, *, principal: LocalPrincipal) -> bool:
        return self._folders is not None and self._folders.is_available_for(principal=principal)

    # Plumbing

    def _resolve(self, *, principal: LocalPrincipal, view_path: str, write: bool = False) -> FolderAccess:
        if self._folders is None:
            raise FolderOutsideAccessError("Folders aren't set up on this computer.")
        access = self._folders.resolve(principal=principal, view_path=view_path)
        if write and not access.can_write:
            raise FolderWriteNotAllowedError("This folder is view-only for your agents.")
        return access

    @staticmethod
    def _engine(principal: LocalPrincipal, access: FolderAccess) -> tuple[WorkspaceFileManagerService, LocalPrincipal]:
        root = access.root
        store = WorkspaceFilesystemStore(None, root_resolver=lambda _scope: root, show_hidden=access.include_hidden)
        actor = replace(principal, workspace_id=f"folder:{access.folder.folder_id}")
        return WorkspaceFileManagerService(store, enforce_reserved=False), actor

    @staticmethod
    def _view(access: FolderAccess, relative: str | None) -> str:
        return join_local_view_path(access.view_root, relative or "")

    def _mutation(self, access: FolderAccess, result: WorkspaceFileMutation, message: str) -> WorkspaceFileMutation:
        return WorkspaceFileMutation(
            status=result.status,
            message=message,
            affectedCount=result.affectedCount,
            path=self._view(access, result.path) if result.path is not None else None,
            destinationPath=self._view(access, result.destinationPath) if result.destinationPath else None,
        )

    # Reads

    def list_root(self, *, principal: LocalPrincipal) -> WorkspaceFileDirectory:
        folders = self._folders.folders_for(principal=principal) if self._folders else []
        entries = [
            WorkspaceFileEntry(
                kind="directory",
                name=folder.name,
                path=build_local_mount_path(mount_name=folder.name),
                linked=True,
                permission=folder.permission,
            )
            for folder in folders
        ]
        return WorkspaceFileDirectory(currentDirectory=LOCAL_FILES_ROOT, parentDirectory="", entries=entries)

    def list_directory(self, *, principal: LocalPrincipal, view_path: str) -> WorkspaceFileDirectory:
        access = self._resolve(principal=principal, view_path=view_path)
        manager, actor = self._engine(principal, access)
        listing = manager.list_directory(actor=actor, directory=access.relative_path or None, include_reserved=True)
        entries = [
            replace(
                entry,
                path=self._view(access, entry.path),
                editable=bool(entry.editable) and access.can_write,
                linked=True,
                permission=access.folder.permission,
            )
            for entry in listing.entries
        ]
        current = self._view(access, listing.currentDirectory)
        if not listing.currentDirectory:
            parent = LOCAL_FILES_ROOT
        else:
            parent = self._view(access, listing.parentDirectory)
        return WorkspaceFileDirectory(
            currentDirectory=current,
            parentDirectory=parent,
            entries=entries,
            permission=access.folder.permission,
        )

    def read_file(self, *, principal: LocalPrincipal, view_path: str) -> WorkspaceFileRead:
        access = self._resolve(principal=principal, view_path=view_path)
        manager, actor = self._engine(principal, access)
        read_back = manager.read_file(actor=actor, file_key=access.relative_path, include_reserved=True)
        return replace(
            read_back,
            fileKey=self._view(access, read_back.fileKey),
            editable=read_back.editable and access.can_write,
        )

    def read_file_bytes(self, *, principal: LocalPrincipal, view_path: str) -> tuple[str, str, bytes]:
        access = self._resolve(principal=principal, view_path=view_path)
        manager, actor = self._engine(principal, access)
        return manager.read_file_bytes(actor=actor, file_key=access.relative_path, include_reserved=True)

    # Search

    def can_search_fast(self) -> bool:
        return self._folders is not None and ripgrep() is not None

    def search(
        self, *, principal: LocalPrincipal, view_path: str, query: str, limit: int, deadline: float,
        options: SearchOptions | None = None,
    ) -> tuple[list[tuple[str, FolderSearchHit]], bool] | None:
        """ripgrep inside one folder (or a directory in it). None means use the slow walk instead."""
        executable = ripgrep()
        if executable is None:
            return None
        access = self._resolve(principal=principal, view_path=view_path)
        base = resolve_inside(access.root, access.relative_path, allow_hidden=access.include_hidden)
        if not base.is_dir():
            return None
        result = search_folder(
            base=base, query=query, include_hidden=access.include_hidden,
            limit=limit, deadline=deadline, executable=executable, options=options,
        )
        prefix = self._view(access, access.relative_path)
        return [(join_local_view_path(prefix, hit.relative_path), hit) for hit in result.hits], result.truncated

    # Writes

    def save_file(self, *, principal: LocalPrincipal, view_path: str, content_markdown: str) -> WorkspaceFileMutation:
        access = self._resolve(principal=principal, view_path=view_path, write=True)
        manager, actor = self._engine(principal, access)
        result = manager.save_file(
            actor=actor, payload={"fileKey": access.relative_path, "contentMarkdown": content_markdown},
        )
        return self._mutation(access, result, "File saved.")

    def write_text_file(
        self,
        *,
        principal: LocalPrincipal,
        view_path: str,
        content_markdown: str,
        overwrite_existing: bool = False,
    ) -> WorkspaceFileMutation:
        access = self._resolve(principal=principal, view_path=view_path, write=True)
        manager, actor = self._engine(principal, access)
        result = manager.write_text_file(
            actor=actor, file_key=access.relative_path,
            content_markdown=content_markdown, overwrite_existing=overwrite_existing,
        )
        return self._mutation(access, result, result.message.replace("Workspace file", "File"))

    def create_directory(self, *, principal: LocalPrincipal, view_path: str) -> WorkspaceFileMutation:
        access = self._resolve(principal=principal, view_path=view_path, write=True)
        manager, actor = self._engine(principal, access)
        result = manager.create_directory(actor=actor, payload={"directory": access.relative_path})
        return self._mutation(access, result, "Folder created.")

    def upload_files(
        self,
        *,
        principal: LocalPrincipal,
        view_path: str,
        uploads: list[WorkspaceFileUpload],
    ) -> WorkspaceFileMutation:
        access = self._resolve(principal=principal, view_path=view_path, write=True)
        manager, actor = self._engine(principal, access)
        result = manager.upload_files(actor=actor, directory=access.relative_path or None, uploads=uploads)
        count = result.affectedCount
        return self._mutation(access, result, f"Uploaded {count} file{'s' if count != 1 else ''}.")

    def move_path(
        self,
        *,
        principal: LocalPrincipal,
        source_path: str,
        destination_path: str,
    ) -> WorkspaceFileMutation:
        source = self._resolve(principal=principal, view_path=source_path, write=True)
        destination = self._resolve(principal=principal, view_path=destination_path, write=True)
        if source.folder.folder_id != destination.folder.folder_id:
            raise FolderOutsideAccessError("Files can only be moved within the same folder.")
        if not source.relative_path or not destination.relative_path:
            raise FolderOutsideAccessError("A folder you added can't be moved. Move items inside it instead.")
        manager, actor = self._engine(principal, source)
        result = manager.move_path(
            actor=actor,
            payload={"sourcePath": source.relative_path, "destinationPath": destination.relative_path},
        )
        return self._mutation(source, result, "Moved.")

    def delete_path(self, *, principal: LocalPrincipal, view_path: str, recursive: bool) -> WorkspaceFileMutation:
        access = self._resolve(principal=principal, view_path=view_path, write=True)
        if not access.relative_path:
            raise FolderOutsideAccessError(
                "A folder you added can't be deleted here. Remove it in Settings > Folders instead."
            )
        manager, actor = self._engine(principal, access)
        result = manager.delete_path(actor=actor, payload={"path": access.relative_path, "recursive": recursive})
        return self._mutation(access, result, "Deleted.")
