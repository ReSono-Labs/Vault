"""Shared test helpers moved out of test modules (TST-01)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from app.vault_runtime.folders.errors import FolderNameTakenError, FolderUnavailableError
from app.vault_runtime.folders.models import FolderGrant, UserFolder
from app.vault_runtime.local_identity.models import LocalPrincipal


class MemoryFolderRepository:
    """In-memory stand-in with the same rules as FolderRepository."""

    def __init__(self, users: set[str]) -> None:
        self.users = users
        self.grants: dict[str, FolderGrant] = {}
        self.folders: dict[str, UserFolder] = {}

    def list_grants(self, *, user_id):
        return [grant for grant in self.grants.values() if grant.user_id == user_id]

    def get_grant(self, *, grant_id):
        return self.grants.get(grant_id)

    def upsert_grant(self, *, user_id, location_id, relative_path, max_permission, created_by, include_hidden=None):
        if user_id not in self.users:
            raise FolderUnavailableError("That person was not found.")
        for grant in self.grants.values():
            if (grant.user_id, grant.location_id, grant.relative_path) == (user_id, location_id, relative_path):
                if include_hidden is not None:
                    self.set_grant_hidden(grant_id=grant.grant_id, include_hidden=include_hidden)
                return self.set_grant_permission(grant_id=grant.grant_id, max_permission=max_permission)
        grant = FolderGrant(str(uuid4()), user_id, location_id, relative_path, max_permission, datetime.now(UTC),
                            bool(include_hidden))
        self.grants[grant.grant_id] = grant
        return grant

    def set_grant_permission(self, *, grant_id, max_permission):
        grant = replace(self.grants[grant_id], max_permission=max_permission)
        self.grants[grant_id] = grant
        if max_permission == "read":
            for folder in list(self.folders.values()):
                if folder.grant_id == grant_id:
                    self.folders[folder.folder_id] = replace(folder, permission="read")
        return grant

    def set_grant_hidden(self, *, grant_id, include_hidden):
        grant = replace(self.grants[grant_id], include_hidden=include_hidden)
        self.grants[grant_id] = grant
        return grant

    def delete_grant(self, *, grant_id):
        if self.grants.pop(grant_id, None) is None:
            raise FolderUnavailableError("That access was not found.")
        self.folders = {key: value for key, value in self.folders.items() if value.grant_id != grant_id}

    def folder_counts(self, *, grant_ids):
        return {grant_id: sum(1 for f in self.folders.values() if f.grant_id == grant_id) for grant_id in grant_ids}

    def list_folders(self, *, user_id):
        return sorted((f for f in self.folders.values() if f.user_id == user_id), key=lambda f: f.name.casefold())

    def get_folder(self, *, user_id, folder_id):
        folder = self.folders.get(folder_id)
        return folder if folder and folder.user_id == user_id else None

    def get_folder_by_name(self, *, user_id, name):
        return next((f for f in self.folders.values()
                     if f.user_id == user_id and f.name.casefold() == name.casefold()), None)

    def insert_folder(self, *, user_id, grant_id, relative_path, name, permission, created_vault, include_hidden=False):
        if self.get_folder_by_name(user_id=user_id, name=name):
            raise FolderNameTakenError(f"You already have a folder named '{name}'.")
        folder = UserFolder(str(uuid4()), user_id, grant_id, relative_path, name, permission,
                            created_vault, datetime.now(UTC), include_hidden)
        self.folders[folder.folder_id] = folder
        return folder

    def set_folder_permission(self, *, user_id, folder_id, permission):
        folder = replace(self.folders[folder_id], permission=permission)
        self.folders[folder_id] = folder
        return folder

    def set_folder_hidden(self, *, user_id, folder_id, include_hidden):
        folder = replace(self.folders[folder_id], include_hidden=include_hidden)
        self.folders[folder_id] = folder
        return folder

    def delete_folder(self, *, user_id, folder_id):
        if self.get_folder(user_id=user_id, folder_id=folder_id) is None:
            raise FolderUnavailableError("This folder is no longer available.")
        del self.folders[folder_id]


def _principal(user_id: str, *, admin: bool = False) -> LocalPrincipal:
    return LocalPrincipal(
        user_id=user_id, username=user_id, display_name=user_id, experience_style="balanced",
        is_device_owner=admin, session_id="s", workspace_id=f"ws-{user_id}", expires_at=datetime.now(UTC),
    )
