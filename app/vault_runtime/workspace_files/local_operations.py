from __future__ import annotations

import base64

from datetime import UTC, datetime

from app.vault_runtime.host_filesystem.service import HostFilesystemService, HostMountAccess
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.workspace_files.local_paths import (
    LOCAL_FILES_ROOT,
    build_local_mount_path,
    join_local_view_path,
    parse_local_view_path,
)
from app.vault_runtime.workspace_files.manager import WorkspaceFileUpload
from app.vault_runtime.workspace_files.models import (
    WorkspaceFileDirectory,
    WorkspaceFileEntry,
    WorkspaceFileMutation,
    WorkspaceFileRead,
)


class LocalFilesystemBridge:
    def __init__(self, *, host_filesystem: HostFilesystemService | None) -> None:
        self._host_filesystem = host_filesystem

    def is_available(self, *, principal: LocalPrincipal) -> bool:
        return self._host_filesystem is not None and self._host_filesystem.is_enabled_for(principal=principal)

    def list_root(self, *, principal: LocalPrincipal) -> WorkspaceFileDirectory:
        mounts = self._host_filesystem.list_mount_names(principal=principal) if self._host_filesystem else []
        entries = [
            WorkspaceFileEntry(
                kind="directory",
                name=mount_name,
                path=build_local_mount_path(mount_name=mount_name),
                linked=True,
            )
            for mount_name in mounts
        ]
        return WorkspaceFileDirectory(
            currentDirectory=LOCAL_FILES_ROOT,
            parentDirectory="",
            entries=entries,
        )

    def list_directory(self, *, principal: LocalPrincipal, view_path: str) -> WorkspaceFileDirectory:
        access = self._resolve(principal=principal, view_path=view_path)
        if access.mount.source == "browser":
            from app.vault_runtime.workspace_files.errors import WorkspaceFileBadRequestError

            raise WorkspaceFileBadRequestError(
                "Linked folders open in the Vault browser tab where they were added."
            )
        payload = self._host_filesystem.helper_list_directory(access=access, principal=principal)
        mount_path = access.mount_path
        entries = [
            WorkspaceFileEntry(
                kind=str(item["kind"]),
                name=str(item["name"]),
                path=join_local_view_path(mount_path, str(item["path"])),
                sizeBytes=item.get("sizeBytes"),
                childCount=item.get("childCount"),
                mimeType=item.get("mimeType"),
                editable=bool(item.get("editable")) and access.can_write,
                linked=True,
                permission=access.mount.permission,
            )
            for item in payload.get("entries", [])
        ]
        current_relative = str(payload.get("currentDirectory") or access.relative_path)
        current = mount_path if not current_relative else join_local_view_path(mount_path, current_relative)
        parent_relative = payload.get("parentDirectory")
        if current == mount_path:
            parent = LOCAL_FILES_ROOT
        elif parent_relative in (None, ""):
            parent = mount_path
        else:
            parent = join_local_view_path(mount_path, str(parent_relative))
        return WorkspaceFileDirectory(
            currentDirectory=current,
            parentDirectory=parent,
            entries=entries,
            permission=access.mount.permission,
        )

    def read_file(self, *, principal: LocalPrincipal, view_path: str) -> WorkspaceFileRead:
        access = self._resolve(principal=principal, view_path=view_path)
        if access.mount.source == "browser":
            from app.vault_runtime.workspace_files.errors import WorkspaceFileBadRequestError

            raise WorkspaceFileBadRequestError(
                "Browser-linked folders are visible in the Vault browser but are not readable by server-side agents."
            )
        payload = self._host_filesystem.helper_read_file(
            access=access,
            principal=principal,
            file_key=access.relative_path,
        )
        return WorkspaceFileRead(
            fileKey=view_path,
            filename=str(payload.get("filename") or access.relative_path.split("/")[-1]),
            contentMarkdown=str(payload.get("contentMarkdown") or ""),
            sizeBytes=int(payload.get("sizeBytes") or 0),
            mimeType=str(payload.get("mimeType") or "application/octet-stream"),
            editable=bool(payload.get("editable")) and access.can_write,
            projectionVersion=1,
            updatedAt=datetime.now(UTC),
        )

    def read_file_bytes(self, *, principal: LocalPrincipal, view_path: str) -> tuple[str, str, bytes]:
        access = self._resolve(principal=principal, view_path=view_path)
        payload = self._host_filesystem.helper_read_file(
            access=access,
            principal=principal,
            file_key=access.relative_path,
        )
        content = base64.b64decode(str(payload.get("contentBase64") or "").encode("ascii"))
        mime_type = str(payload.get("mimeType") or "application/octet-stream")
        return view_path, mime_type, content

    def save_file(
        self,
        *,
        principal: LocalPrincipal,
        view_path: str,
        content_markdown: str,
    ) -> WorkspaceFileMutation:
        access = self._resolve(principal=principal, view_path=view_path)
        encoded = base64.b64encode(content_markdown.encode("utf-8")).decode("ascii")
        self._host_filesystem.helper_write_file(
            access=access,
            principal=principal,
            file_key=access.relative_path,
            content_base64=encoded,
            mime_type="text/markdown",
        )
        return WorkspaceFileMutation(
            status="completed",
            message="Linked file saved.",
            affectedCount=1,
            path=view_path,
        )

    def write_text_file(
        self,
        *,
        principal: LocalPrincipal,
        view_path: str,
        content_markdown: str,
    ) -> WorkspaceFileMutation:
        return self.save_file(
            principal=principal,
            view_path=view_path,
            content_markdown=content_markdown,
        )

    def create_directory(self, *, principal: LocalPrincipal, view_path: str) -> WorkspaceFileMutation:
        access = self._resolve(principal=principal, view_path=view_path)
        self._host_filesystem.helper_create_directory(
            access=access,
            principal=principal,
            directory=access.relative_path,
        )
        return WorkspaceFileMutation(
            status="completed",
            message="Linked folder created.",
            affectedCount=1,
            path=view_path,
        )

    def upload_files(
        self,
        *,
        principal: LocalPrincipal,
        view_path: str,
        uploads: list[WorkspaceFileUpload],
    ) -> WorkspaceFileMutation:
        access = self._resolve(principal=principal, view_path=view_path)
        files = [
            {
                "filename": upload.filename,
                "contentBase64": base64.b64encode(upload.content).decode("ascii"),
            }
            for upload in uploads
        ]
        result = self._host_filesystem.helper_upload_files(
            access=access,
            principal=principal,
            directory=access.relative_path,
            files=files,
        )
        destination = result.get("destinationPath")
        destination_view = (
            join_local_view_path(access.mount_path, str(destination))
            if destination
            else None
        )
        return WorkspaceFileMutation(
            status="completed",
            message=f"Uploaded {len(uploads)} linked file{'s' if len(uploads) != 1 else ''}.",
            affectedCount=len(uploads),
            path=view_path or None,
            destinationPath=destination_view,
        )

    def move_path(
        self,
        *,
        principal: LocalPrincipal,
        source_path: str,
        destination_path: str,
    ) -> WorkspaceFileMutation:
        source = self._resolve(principal=principal, view_path=source_path)
        destination = self._resolve(principal=principal, view_path=destination_path)
        if source.mount.mount_id != destination.mount.mount_id:
            raise ValueError("Linked paths must stay within the same folder.")
        self._host_filesystem.helper_move_path(
            access=source,
            principal=principal,
            source_path=source.relative_path,
            destination_path=destination.relative_path,
        )
        return WorkspaceFileMutation(
            status="completed",
            message="Linked path moved.",
            affectedCount=1,
            path=source_path,
            destinationPath=destination_path,
        )

    def delete_path(
        self,
        *,
        principal: LocalPrincipal,
        view_path: str,
        recursive: bool,
    ) -> WorkspaceFileMutation:
        access = self._resolve(principal=principal, view_path=view_path)
        self._host_filesystem.helper_delete_path(
            access=access,
            principal=principal,
            path=access.relative_path,
            recursive=recursive,
        )
        return WorkspaceFileMutation(
            status="completed",
            message="Linked path deleted.",
            affectedCount=1,
            path=view_path,
        )

    def _resolve(self, *, principal: LocalPrincipal, view_path: str) -> HostMountAccess:
        if self._host_filesystem is None:
            raise RuntimeError("Host filesystem is unavailable.")
        access = self._host_filesystem.resolve_mount_access(principal=principal, view_path=view_path)
        if access is not None:
            return access
        parsed = parse_local_view_path(view_path)
        if parsed and parsed.mount_name:
            access = self._host_filesystem.resolve_mount_access(
                principal=principal,
                view_path=build_local_mount_path(mount_name=parsed.mount_name),
            )
        if access is None:
            raise RuntimeError("Linked folder resolution failed.")
        return access
