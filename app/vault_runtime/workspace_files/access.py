from __future__ import annotations

from dataclasses import dataclass

from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.workspace_files.errors import (
    WorkspaceFileBadRequestError,
    WorkspaceFileForbiddenError,
    WorkspaceFileNotFoundError,
)
from app.vault_runtime.workspace_files.repository import WorkspaceFileRepository, WorkspaceFolderShare, is_reserved_workspace_file_key
from app.vault_runtime.workspace_files.local_paths import is_local_view_path
from app.vault_runtime.workspace_files.shared_paths import (
    SHARED_FILES_ROOT,
    build_shared_mount_path,
    is_shared_view_path,
    join_shared_view_path,
    parse_shared_view_path,
    shared_owner_directory,
)
from app.vault_runtime.workspace_files.store import WorkspaceFilesystemStore
from app.vault_runtime.workspace_paths import (
    normalize_workspace_file_key,
    normalize_workspace_file_prefix,
    resolve_workspace_staging_path,
)


def _join_path(directory: str, name: str) -> str:
    return f"{directory}/{name}".strip("/") if directory else name


def path_is_within_root(*, path: str, root: str) -> bool:
    normalized_path = normalize_workspace_file_prefix(path)
    normalized_root = normalize_workspace_file_prefix(root)
    if not normalized_root:
        return True
    if normalized_path == normalized_root:
        return True
    return normalized_path.startswith(f"{normalized_root}/")


@dataclass(frozen=True, slots=True)
class WorkspaceAccess:
    workspace_id: str
    permission: str
    share_id: str | None = None
    share_root: str = ""
    share_kind: str | None = None
    share_mount_path: str = ""
    owner_username: str | None = None
    virtual_shared: bool = False

    @property
    def can_read(self) -> bool:
        return self.permission in {"owner", "write", "read"}

    @property
    def can_write(self) -> bool:
        return self.permission in {"owner", "write"}


class WorkspaceAccessResolver:
    """Maps view paths to storage paths and enforces share boundaries down the tree."""

    def __init__(
        self,
        *,
        repository: WorkspaceFileRepository,
        store: WorkspaceFilesystemStore,
    ) -> None:
        self._repository = repository
        self._store = store

    def resolve(
        self,
        *,
        principal: LocalPrincipal,
        share_id: str | None,
        view_path: str = "",
    ) -> WorkspaceAccess:
        if share_id:
            share = self._repository.get_share(share_id=share_id, grantee_user_id=principal.user_id)
            if share is None:
                raise WorkspaceFileNotFoundError("That shared item is unavailable.")
            return self._access_from_share(share)

        parsed = parse_shared_view_path(view_path)
        if parsed is not None:
            if not parsed.owner_username:
                return WorkspaceAccess(
                    workspace_id=principal.workspace_id,
                    permission="owner",
                    virtual_shared=True,
                )
            if not parsed.remainder:
                return WorkspaceAccess(
                    workspace_id=principal.workspace_id,
                    permission="owner",
                    owner_username=parsed.owner_username,
                    virtual_shared=True,
                )
            share = self._match_shared_view(
                grantee_user_id=principal.user_id,
                owner_username=parsed.owner_username,
                remainder=parsed.remainder,
            )
            if share is None:
                raise WorkspaceFileNotFoundError("That shared item is unavailable.")
            return self._access_from_share(share)

        if is_shared_view_path(view_path):
            raise WorkspaceFileNotFoundError("That shared item is unavailable.")

        return WorkspaceAccess(
            workspace_id=principal.workspace_id,
            permission="owner",
            share_id=None,
            share_root="",
        )

    def _access_from_share(self, share: WorkspaceFolderShare) -> WorkspaceAccess:
        owner_username = share.owner_username or "user"
        mount_path = build_shared_mount_path(
            owner_username=owner_username,
            mount_name=share.share_mount_name,
        )
        return WorkspaceAccess(
            workspace_id=share.workspace_id,
            permission=share.permission,
            share_id=share.share_id,
            share_root=share.folder_path,
            share_kind=share.share_kind,
            share_mount_path=mount_path,
            owner_username=owner_username,
        )

    def _match_shared_view(
        self,
        *,
        grantee_user_id: str,
        owner_username: str,
        remainder: str,
    ) -> WorkspaceFolderShare | None:
        shares = [
            share for share in self._repository.list_shares_for_grantee(grantee_user_id=grantee_user_id)
            if (share.owner_username or "").casefold() == owner_username.casefold()
        ]
        matches: list[tuple[int, WorkspaceFolderShare]] = []
        for share in shares:
            mount = share.share_mount_name
            if remainder == mount:
                matches.append((len(mount), share))
                continue
            if share.share_kind == "folder" and remainder.startswith(f"{mount}/"):
                matches.append((len(mount), share))
        if not matches:
            return None
        matches.sort(key=lambda item: item[0], reverse=True)
        best_length, best_share = matches[0]
        if best_share.share_kind == "file" and remainder != best_share.share_mount_name:
            return None
        return best_share

    def view_directory_to_storage(self, *, access: WorkspaceAccess, directory: str | None) -> str:
        if access.virtual_shared:
            raise WorkspaceFileNotFoundError("That shared folder was not found.")
        relative = normalize_workspace_file_prefix(directory)
        if access.share_id:
            if not relative:
                if access.share_kind == "folder":
                    return access.share_root
                return access.share_root
            return self.view_path_to_storage(access=access, view_path=relative)
        if is_shared_view_path(relative):
            raise WorkspaceFileForbiddenError("The shared area is read-only in this workspace.")
        if is_local_view_path(relative):
            raise WorkspaceFileForbiddenError("Linked host folders are managed separately.")
        return relative

    def view_path_to_storage(self, *, access: WorkspaceAccess, view_path: str) -> str:
        if access.virtual_shared:
            raise WorkspaceFileNotFoundError("That shared item is unavailable.")
        if access.share_id:
            normalized = normalize_workspace_file_prefix(view_path)
            if access.share_kind == "file":
                if normalized != access.share_mount_path and normalized != access.share_root:
                    raise WorkspaceFileForbiddenError("That path is outside the shared item.")
                self.assert_storage_path_allowed(access=access, storage_path=access.share_root)
                return access.share_root
            if not normalized.startswith(f"{access.share_mount_path}/") and normalized != access.share_mount_path:
                raise WorkspaceFileForbiddenError("That path is outside the shared folder.")
            relative = (
                ""
                if normalized == access.share_mount_path
                else normalized[len(access.share_mount_path) + 1 :]
            )
            storage_path = access.share_root if not relative else _join_path(access.share_root, relative)
            self.assert_storage_path_allowed(access=access, storage_path=storage_path)
            return storage_path
        normalized = normalize_workspace_file_prefix(view_path) if view_path else ""
        if is_shared_view_path(normalized):
            raise WorkspaceFileForbiddenError("The shared area is read-only in this workspace.")
        if is_local_view_path(normalized):
            raise WorkspaceFileForbiddenError("Linked host folders are managed separately.")
        return normalized

    def storage_path_to_view(self, *, access: WorkspaceAccess, storage_path: str) -> str:
        if not access.share_id:
            return normalize_workspace_file_prefix(storage_path)
        normalized = normalize_workspace_file_prefix(storage_path)
        if access.share_kind == "file":
            return access.share_mount_path
        if not path_is_within_root(path=normalized, root=access.share_root):
            raise WorkspaceFileForbiddenError("That path is outside the shared folder.")
        if normalized == access.share_root:
            return access.share_mount_path
        relative = normalized[len(access.share_root) + 1 :]
        return join_shared_view_path(access.share_mount_path, relative)

    def require_read(self, access: WorkspaceAccess) -> None:
        if access.can_read:
            return
        raise WorkspaceFileForbiddenError("Read access is required.")

    def require_write(self, access: WorkspaceAccess) -> None:
        if access.can_write:
            return
        raise WorkspaceFileForbiddenError("Write access is required.")

    def assert_storage_path_allowed(self, *, access: WorkspaceAccess, storage_path: str) -> None:
        normalized = normalize_workspace_file_prefix(storage_path)
        if is_reserved_workspace_file_key(normalized):
            raise WorkspaceFileNotFoundError("That workspace file was not found.")
        if access.share_id and not path_is_within_root(path=normalized, root=access.share_root):
            raise WorkspaceFileForbiddenError("That path is outside the shared folder.")

    def assert_share_target_exists(
        self,
        *,
        access: WorkspaceAccess,
        target_path: str,
    ) -> tuple[str, str]:
        normalized = normalize_workspace_file_prefix(target_path)
        if not normalized:
            raise WorkspaceFileBadRequestError("A path is required to share.")
        if is_reserved_workspace_file_key(normalized):
            raise WorkspaceFileBadRequestError("That path cannot be shared.")
        files_root = self._store.files_root(workspace_id=access.workspace_id)
        target = resolve_workspace_staging_path(workspace_root=files_root, file_key=normalized)
        if target.is_file() and not target.is_symlink():
            return normalized, "file"
        if target.is_dir() and not target.is_symlink():
            return normalized, "folder"
        raise WorkspaceFileNotFoundError("That workspace item was not found.")

    def assert_view_path_allowed_for_write(self, *, access: WorkspaceAccess, view_path: str) -> None:
        self.require_write(access)
        if access.virtual_shared:
            raise WorkspaceFileForbiddenError("Write access is required.")
        storage_path = self.view_path_to_storage(access=access, view_path=view_path)
        if access.share_id:
            self.assert_storage_path_allowed(access=access, storage_path=storage_path)

    def assert_move_allowed(
        self,
        *,
        access: WorkspaceAccess,
        source_view_path: str,
        destination_view_path: str,
    ) -> tuple[str, str]:
        self.require_write(access)
        source_storage = self.view_path_to_storage(access=access, view_path=source_view_path)
        destination_storage = self.view_path_to_storage(access=access, view_path=destination_view_path)
        if access.share_id:
            self.assert_storage_path_allowed(access=access, storage_path=source_storage)
            self.assert_storage_path_allowed(access=access, storage_path=destination_storage)
        return source_storage, destination_storage

    def normalize_owner_target_path(self, target_path: str) -> str:
        normalized = normalize_workspace_file_prefix(target_path)
        if not normalized:
            raise WorkspaceFileBadRequestError("A path is required to share.")
        try:
            normalize_workspace_file_key(normalized, require_extension=False)
        except ValueError as exc:
            raise WorkspaceFileBadRequestError("That path is invalid.") from exc
        return normalized
