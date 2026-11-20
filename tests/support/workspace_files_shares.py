"""Shared test helpers moved out of test modules (TST-01)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.workspace_files.repository import WorkspaceFolderShare, share_mount_name_for_path


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
