from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.workspace_files.access import WorkspaceAccessResolver, path_is_within_root
from app.vault_runtime.workspace_files.errors import (
    WorkspaceFileBadRequestError,
    WorkspaceFileForbiddenError,
    WorkspaceFileNotFoundError,
)
from app.vault_runtime.workspace_files.manager import WorkspaceFileManagerService
from app.vault_runtime.workspace_files.repository import WorkspaceFolderShare, share_mount_name_for_path
from app.vault_runtime.workspace_files.service import WorkspaceFileService
from app.vault_runtime.workspace_files.shared_paths import SHARED_FILES_ROOT, build_shared_mount_path
from app.vault_runtime.workspace_files.store import WorkspaceFilesystemStore
from app.vault_runtime.workspace_storage import WorkspaceStorage


@dataclass
class FakeWorkspaceShareRepository:
    shares: dict[str, WorkspaceFolderShare] = field(default_factory=dict)

    def get_share(self, *, share_id: str, grantee_user_id: str | None = None) -> WorkspaceFolderShare | None:
        share = self.shares.get(share_id)
        if share is None or share.status != "active":
            return None
        if grantee_user_id is not None and share.grantee_user_id != grantee_user_id:
            return None
        return share

    def list_shares_for_grantee(self, *, grantee_user_id: str) -> list[WorkspaceFolderShare]:
        return [
            share for share in self.shares.values()
            if share.grantee_user_id == grantee_user_id and share.status == "active"
        ]

    def list_shares_for_folder(
        self, *, workspace_id: str, folder_path: str, actor_user_id: str,
    ) -> list[WorkspaceFolderShare]:
        return [
            share for share in self.shares.values()
            if share.workspace_id == workspace_id
            and share.folder_path == folder_path
            and share.status == "active"
        ]

    def upsert_share(
        self,
        *,
        workspace_id: str,
        folder_path: str,
        grantee_user_id: str,
        permission: str,
        created_by_user_id: str,
        share_kind: str = "folder",
        share_mount_name: str | None = None,
        owner_username: str = "owner-1",
    ) -> WorkspaceFolderShare:
        mount_name = share_mount_name or share_mount_name_for_path(
            target_path=folder_path,
            share_kind=share_kind,
        )
        share = WorkspaceFolderShare(
            share_id=f"share-{len(self.shares) + 1}",
            workspace_id=workspace_id,
            folder_path=folder_path,
            grantee_user_id=grantee_user_id,
            permission=permission,
            created_by_user_id=created_by_user_id,
            status="active",
            share_kind=share_kind,
            share_mount_name=mount_name,
            grantee_display_name="Grantee",
            grantee_username="grantee",
            owner_username=owner_username,
            owner_display_name=owner_username.title(),
        )
        self.shares[share.share_id] = share
        return share

    def revoke_share(self, *, workspace_id: str, share_id: str, actor_user_id: str) -> None:
        share = self.shares[share_id]
        self.shares[share_id] = WorkspaceFolderShare(
            share_id=share.share_id,
            workspace_id=share.workspace_id,
            folder_path=share.folder_path,
            grantee_user_id=share.grantee_user_id,
            permission=share.permission,
            created_by_user_id=share.created_by_user_id,
            status="revoked",
            share_kind=share.share_kind,
            share_mount_name=share.share_mount_name,
            grantee_display_name=share.grantee_display_name,
            grantee_username=share.grantee_username,
            owner_username=share.owner_username,
            owner_display_name=share.owner_display_name,
        )


def _principal(*, user_id: str, workspace_id: str, username: str | None = None) -> LocalPrincipal:
    resolved_username = username or user_id
    return LocalPrincipal(
        user_id=user_id,
        username=resolved_username,
        display_name=resolved_username.title(),
        experience_style="balanced",
        is_device_owner=True,
        session_id="session-1",
        workspace_id=workspace_id,
        expires_at=datetime.now(UTC),
    )


def _provision_shared_folder_fixture(
    tmp_path: Path,
) -> tuple[WorkspaceFileService, FakeWorkspaceShareRepository, WorkspaceFolderShare]:
    storage = WorkspaceStorage(tmp_path / "private")
    storage.provision(user_id="owner-1", workspace_id="workspace-owner")
    storage.provision(user_id="grantee-1", workspace_id="workspace-grantee")
    repository = FakeWorkspaceShareRepository()
    service = WorkspaceFileService(repository, storage)  # type: ignore[arg-type]
    manager = WorkspaceFileManagerService(WorkspaceFilesystemStore(storage))
    manager.write_text_file(
        actor=_principal(user_id="owner-1", workspace_id="workspace-owner"),
        file_key="BUSINESS/readme.md",
        content_markdown="shared content",
        overwrite_existing=False,
    )
    manager.create_directory(
        actor=_principal(user_id="owner-1", workspace_id="workspace-owner"),
        payload={"directory": "BUSINESS/assets"},
    )
    share = repository.upsert_share(
        workspace_id="workspace-owner",
        folder_path="BUSINESS",
        grantee_user_id="grantee-1",
        permission="read",
        created_by_user_id="owner-1",
        share_mount_name="BUSINESS",
        owner_username="owner-1",
    )
    return service, repository, share


def test_path_is_within_root() -> None:
    assert path_is_within_root(path="BUSINESS/readme.md", root="BUSINESS")
    assert not path_is_within_root(path="private/secret.md", root="BUSINESS")


def test_every_user_sees_shared_directory_at_workspace_root(tmp_path: Path) -> None:
    service, _repository, _share = _provision_shared_folder_fixture(tmp_path)
    owner_root = service.list_directory(
        principal=_principal(user_id="owner-1", workspace_id="workspace-owner"),
        directory=None,
    )
    grantee_root = service.list_directory(
        principal=_principal(user_id="grantee-1", workspace_id="workspace-grantee"),
        directory=None,
    )
    assert any(entry.path == SHARED_FILES_ROOT for entry in owner_root.entries)
    assert any(entry.path == SHARED_FILES_ROOT for entry in grantee_root.entries)


def test_grantee_navigates_shared_mount_paths(tmp_path: Path) -> None:
    service, _repository, _share = _provision_shared_folder_fixture(tmp_path)
    shared_root = service.list_directory(
        principal=_principal(user_id="grantee-1", workspace_id="workspace-grantee"),
        directory=SHARED_FILES_ROOT,
    )
    assert any(entry.path == "shared/owner-1" for entry in shared_root.entries)

    owner_mounts = service.list_directory(
        principal=_principal(user_id="grantee-1", workspace_id="workspace-grantee"),
        directory="shared/owner-1",
    )
    assert any(entry.path == build_shared_mount_path(owner_username="owner-1", mount_name="BUSINESS") for entry in owner_mounts.entries)

    listing = service.list_directory(
        principal=_principal(user_id="grantee-1", workspace_id="workspace-grantee"),
        directory=build_shared_mount_path(owner_username="owner-1", mount_name="BUSINESS"),
    )
    paths = {entry.path for entry in listing.entries}
    assert build_shared_mount_path(owner_username="owner-1", mount_name="BUSINESS") + "/readme.md" in paths
    assert build_shared_mount_path(owner_username="owner-1", mount_name="BUSINESS") + "/assets" in paths
    assert listing.permission == "read"


def test_read_only_share_blocks_writes(tmp_path: Path) -> None:
    service, _repository, _share = _provision_shared_folder_fixture(tmp_path)
    mount_path = build_shared_mount_path(owner_username="owner-1", mount_name="BUSINESS")
    with pytest.raises(WorkspaceFileForbiddenError):
        service.write_text_file(
            principal=_principal(user_id="grantee-1", workspace_id="workspace-grantee"),
            file_key=f"{mount_path}/new.md",
            content_markdown="nope",
        )


def test_write_share_allows_nested_create(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "private")
    storage.provision(user_id="owner-1", workspace_id="workspace-owner")
    storage.provision(user_id="grantee-1", workspace_id="workspace-grantee")
    repository = FakeWorkspaceShareRepository()
    service = WorkspaceFileService(repository, storage)  # type: ignore[arg-type]
    manager = WorkspaceFileManagerService(WorkspaceFilesystemStore(storage))
    manager.create_directory(
        actor=_principal(user_id="owner-1", workspace_id="workspace-owner"),
        payload={"directory": "collab"},
    )
    repository.upsert_share(
        workspace_id="workspace-owner",
        folder_path="collab",
        grantee_user_id="grantee-1",
        permission="write",
        created_by_user_id="owner-1",
        owner_username="owner-1",
    )
    mount_path = build_shared_mount_path(owner_username="owner-1", mount_name="collab")
    service.write_text_file(
        principal=_principal(user_id="grantee-1", workspace_id="workspace-grantee"),
        file_key=f"{mount_path}/notes/today.md",
        content_markdown="# Shared note",
    )
    read_back = service.read_file(
        principal=_principal(user_id="grantee-1", workspace_id="workspace-grantee"),
        file_key=f"{mount_path}/notes/today.md",
    )
    assert read_back.contentMarkdown == "# Shared note"


def test_file_share_mounts_as_single_file(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "private")
    storage.provision(user_id="owner-1", workspace_id="workspace-owner")
    storage.provision(user_id="grantee-1", workspace_id="workspace-grantee")
    repository = FakeWorkspaceShareRepository()
    service = WorkspaceFileService(repository, storage)  # type: ignore[arg-type]
    manager = WorkspaceFileManagerService(WorkspaceFilesystemStore(storage))
    manager.write_text_file(
        actor=_principal(user_id="owner-1", workspace_id="workspace-owner"),
        file_key="reports/q1-summary.md",
        content_markdown="# Q1 summary",
        overwrite_existing=False,
    )
    repository.upsert_share(
        workspace_id="workspace-owner",
        folder_path="reports/q1-summary.md",
        grantee_user_id="grantee-1",
        permission="read",
        created_by_user_id="owner-1",
        share_kind="file",
        share_mount_name="q1-summary.md",
        owner_username="owner-1",
    )
    mount_path = build_shared_mount_path(owner_username="owner-1", mount_name="q1-summary.md")
    owner_mounts = service.list_directory(
        principal=_principal(user_id="grantee-1", workspace_id="workspace-grantee"),
        directory="shared/owner-1",
    )
    assert any(entry.path == mount_path and entry.kind == "file" for entry in owner_mounts.entries)
    read_back = service.read_file(
        principal=_principal(user_id="grantee-1", workspace_id="workspace-grantee"),
        file_key=mount_path,
    )
    assert read_back.filename == "q1-summary.md"
    assert read_back.contentMarkdown == "# Q1 summary"


def test_share_save_requires_existing_folder(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "private")
    storage.provision(user_id="owner-1", workspace_id="workspace-owner")
    repository = FakeWorkspaceShareRepository()
    service = WorkspaceFileService(repository, storage)  # type: ignore[arg-type]
    with pytest.raises(WorkspaceFileNotFoundError):
        service.save_share(
            principal=_principal(user_id="owner-1", workspace_id="workspace-owner"),
            folder_path="missing",
            grantee_user_id="grantee-1",
            permission="read",
        )


def test_share_save_rejects_workspace_root(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "private")
    storage.provision(user_id="owner-1", workspace_id="workspace-owner")
    repository = FakeWorkspaceShareRepository()
    service = WorkspaceFileService(repository, storage)  # type: ignore[arg-type]
    with pytest.raises(WorkspaceFileBadRequestError):
        service.save_share(
            principal=_principal(user_id="owner-1", workspace_id="workspace-owner"),
            folder_path="",
            grantee_user_id="grantee-1",
            permission="read",
        )


def test_owner_cannot_write_under_shared_prefix(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "private")
    storage.provision(user_id="owner-1", workspace_id="workspace-owner")
    repository = FakeWorkspaceShareRepository()
    service = WorkspaceFileService(repository, storage)  # type: ignore[arg-type]
    with pytest.raises(WorkspaceFileForbiddenError):
        service.create_directory(
            principal=_principal(user_id="owner-1", workspace_id="workspace-owner"),
            directory="shared/injected",
        )


def test_access_resolver_maps_shared_view_paths(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "private")
    storage.provision(user_id="owner-1", workspace_id="workspace-owner")
    repository = FakeWorkspaceShareRepository()
    share = repository.upsert_share(
        workspace_id="workspace-owner",
        folder_path="BUSINESS",
        grantee_user_id="grantee-1",
        permission="write",
        created_by_user_id="owner-1",
        owner_username="owner-1",
    )
    repository.shares[share.share_id] = share
    manager = WorkspaceFileManagerService(WorkspaceFilesystemStore(storage))
    manager.write_text_file(
        actor=_principal(user_id="owner-1", workspace_id="workspace-owner"),
        file_key="BUSINESS/readme.md",
        content_markdown="hello",
        overwrite_existing=False,
    )
    resolver = WorkspaceAccessResolver(
        repository=repository,  # type: ignore[arg-type]
        store=WorkspaceFilesystemStore(storage),
    )
    view_path = build_shared_mount_path(owner_username="owner-1", mount_name="BUSINESS") + "/readme.md"
    access = resolver.resolve(
        principal=_principal(user_id="grantee-1", workspace_id="workspace-grantee"),
        share_id=None,
        view_path=view_path,
    )
    assert resolver.view_path_to_storage(access=access, view_path=view_path) == "BUSINESS/readme.md"
    assert resolver.storage_path_to_view(access=access, storage_path="BUSINESS/readme.md") == view_path
