"""Host folders: admin grants, user folders, and server-side resolution for agents.

Device locations (what Vault can see) come from install-time configuration.
Grants and folders are database rows. Every request re-reads them and re-runs
the path checks, so removing access takes effect on the next request.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from app.vault_runtime.folders.errors import (
    DriveDisconnectedError,
    FolderAdminRequiredError,
    FolderError,
    FolderExistsError,
    FolderInvalidRequestError,
    FolderNameTakenError,
    FolderNotAccessibleError,
    FolderUnavailableError,
    FolderWriteNotAllowedError,
)
from app.vault_runtime.folders.models import (
    PERMISSIONS,
    DeviceLocation,
    FolderAccess,
    FolderGrant,
    UserFolder,
)
from app.vault_runtime.folders.paths import join_relative, last_segment, normalize_relative, resolve_inside
from app.vault_runtime.folders.repository import FolderRepository
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.workspace_files.local_paths import parse_local_view_path

VAULT_FOLDER_NAME = "ReSono Vault"
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")
_QUICK_HOME_FOLDERS = ("Desktop", "Downloads")


def _require_permission(value: str) -> str:
    if value not in PERMISSIONS:
        raise FolderInvalidRequestError("Choose 'Can view' or 'Can view and edit'.")
    return value


def normalize_folder_name(name: str) -> str:
    normalized = " ".join(str(name or "").split())
    if not _NAME_PATTERN.fullmatch(normalized) or normalized.endswith("."):
        raise FolderInvalidRequestError(
            "Folder names can use letters, numbers, spaces, dots, dashes and underscores (up to 64)."
        )
    return normalized


def suggest_folder_name(raw: str, fallback: str = "Folder") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 ._-]+", "-", str(raw or "")).strip(" .-_")
    cleaned = " ".join(cleaned.split())[:64].rstrip(" .")
    return cleaned if cleaned and _NAME_PATTERN.fullmatch(cleaned) else fallback


class FolderService:
    def __init__(
        self,
        *,
        repository: FolderRepository,
        locations: tuple[DeviceLocation, ...],
        documents_folder: str | None = None,
    ) -> None:
        self._repository = repository
        self._locations = {location.id: location for location in locations}
        self._order = [location.id for location in locations]
        self._documents_folder = documents_folder or None

    # Availability

    @property
    def available(self) -> bool:
        return bool(self._locations)

    def is_available_for(self, *, principal: LocalPrincipal) -> bool:
        if not self.available:
            return False
        return bool(self._repository.list_grants(user_id=principal.user_id))

    # Labels

    def _location(self, location_id: str) -> DeviceLocation:
        location = self._locations.get(location_id)
        if location is None:
            raise FolderUnavailableError("This folder is no longer available.")
        return location

    @staticmethod
    def _label(location: DeviceLocation, relative: str) -> str:
        if location.kind in {"home", "drives"}:
            return relative or location.label
        return f"{location.label}/{relative}" if relative else location.label

    def _grant_label(self, grant: FolderGrant) -> str:
        location = self._locations.get(grant.location_id)
        if location is None:
            return grant.relative_path or grant.location_id
        return self._label(location, grant.relative_path)

    # Status

    def _check_directory(self, location: DeviceLocation, path: Path) -> None:
        if not location.path.is_dir():
            raise DriveDisconnectedError("This drive isn't connected. Reconnect it and try again.")
        if not path.exists():
            if location.kind in {"drives", "drive"}:
                raise DriveDisconnectedError("This drive isn't connected. Reconnect it and try again.")
            raise FolderUnavailableError("This folder is no longer on the computer.")
        if not path.is_dir():
            raise FolderUnavailableError("This folder is no longer on the computer.")
        if not os.access(path, os.R_OK | os.X_OK):
            raise FolderNotAccessibleError("Vault doesn't have permission to open this folder on the computer.")

    def _grant_root(self, grant: FolderGrant) -> tuple[DeviceLocation, Path]:
        location = self._location(grant.location_id)
        root = resolve_inside(location.path, grant.relative_path)
        self._check_directory(location, root)
        return location, root

    def _folder_root(self, folder: UserFolder, grant: FolderGrant) -> Path:
        location, grant_root = self._grant_root(grant)
        root = resolve_inside(grant_root, folder.relative_path, allow_hidden=grant.include_hidden)
        self._check_directory(location, root)
        return root

    @staticmethod
    def _status(check) -> tuple[str, str | None]:
        try:
            check()
        except DriveDisconnectedError as exc:
            return "drive_disconnected", str(exc)
        except FolderNotAccessibleError as exc:
            return "not_accessible", str(exc)
        except FolderError as exc:
            return "unavailable", str(exc)
        return "ok", None

    # Browsing (directories only; hidden entries and symlinks are never shown)

    @staticmethod
    def _child_directories(path: Path, relative: str, show_hidden: bool = False) -> list[dict[str, str]]:
        try:
            children = list(path.iterdir())
        except PermissionError as exc:
            raise FolderNotAccessibleError(
                "Vault doesn't have permission to open this folder on the computer."
            ) from exc
        directories = []
        for child in children:
            if (child.name.startswith(".") and not show_hidden) or child.is_symlink():
                continue
            try:
                if not child.is_dir():
                    continue
            except OSError:
                continue
            directories.append({"name": child.name, "path": join_relative(relative, child.name)})
        directories.sort(key=lambda item: item["name"].casefold())
        return directories

    @staticmethod
    def _breadcrumbs(root_label: str, relative: str) -> list[dict[str, str]]:
        crumbs = [{"label": root_label, "path": ""}]
        current = ""
        for part in relative.split("/") if relative else []:
            current = join_relative(current, part)
            crumbs.append({"label": part, "path": current})
        return crumbs

    def _browse(self, *, location: DeviceLocation, base: Path, root_label: str, path: str | None,
                can_create: bool, show_hidden: bool = False) -> dict[str, Any]:
        relative = normalize_relative(path, allow_hidden=show_hidden)
        target = resolve_inside(base, relative, allow_hidden=show_hidden)
        self._check_directory(location, target)
        return {
            "path": relative,
            "breadcrumbs": self._breadcrumbs(root_label, relative),
            "directories": self._child_directories(target, relative, show_hidden),
            "canCreate": can_create and os.access(target, os.W_OK),
        }

    # Admin

    @staticmethod
    def _require_admin(principal: LocalPrincipal) -> None:
        if not principal.is_device_owner:
            raise FolderAdminRequiredError("Only the master account can manage folder access.")

    def admin_locations(self, *, principal: LocalPrincipal) -> dict[str, Any]:
        self._require_admin(principal)
        locations = []
        places: list[dict[str, str]] = []
        for location_id in self._order:
            location = self._locations[location_id]
            status, message = self._status(lambda location=location: self._check_directory(location, location.path))
            locations.append({
                "locationId": location.id, "label": location.label, "kind": location.kind,
                "status": status, "statusMessage": message,
            })
            if status != "ok":
                continue
            places.append({"label": location.label, "locationId": location.id, "path": "", "kind": location.kind})
            if location.kind == "home":
                for relative in ([self._documents_folder] if self._documents_folder else []) + list(_QUICK_HOME_FOLDERS):
                    try:
                        candidate = resolve_inside(location.path, relative)
                    except FolderError:
                        continue
                    if candidate.is_dir():
                        places.append({
                            "label": last_segment(relative) or relative, "locationId": location.id,
                            "path": normalize_relative(relative), "kind": "folder",
                        })
            elif location.kind == "drives":
                for drive in self._child_directories(location.path, ""):
                    places.append({
                        "label": drive["name"], "locationId": location.id,
                        "path": drive["path"], "kind": "drive",
                    })
        return {"available": self.available, "locations": locations, "places": places}

    def admin_browse(self, *, principal: LocalPrincipal, location_id: str, path: str | None) -> dict[str, Any]:
        self._require_admin(principal)
        location = self._location(location_id)
        return {
            "locationId": location.id,
            **self._browse(location=location, base=location.path, root_label=location.label,
                           path=path, can_create=True),
        }

    def _grant_payload(self, grant: FolderGrant, folder_count: int = 0) -> dict[str, Any]:
        status, message = self._status(lambda: self._grant_root(grant))
        return {
            "grantId": grant.grant_id,
            "label": self._grant_label(grant),
            "locationId": grant.location_id,
            "path": grant.relative_path,
            "maxPermission": grant.max_permission,
            "includeHidden": grant.include_hidden,
            "folderCount": folder_count,
            "status": status,
            "statusMessage": message,
        }

    def list_user_access(self, *, principal: LocalPrincipal, user_id: str) -> list[dict[str, Any]]:
        self._require_admin(principal)
        grants = self._repository.list_grants(user_id=user_id)
        counts = self._repository.folder_counts(grant_ids=[grant.grant_id for grant in grants])
        return [self._grant_payload(grant, counts.get(grant.grant_id, 0)) for grant in grants]

    def give_access(
        self, *, principal: LocalPrincipal, user_id: str, location_id: str, path: str | None, max_permission: str,
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        self._require_admin(principal)
        _require_permission(max_permission)
        location = self._location(location_id)
        relative = normalize_relative(path)
        self._check_directory(location, resolve_inside(location.path, relative))
        grant = self._repository.upsert_grant(
            user_id=user_id, location_id=location.id, relative_path=relative,
            max_permission=max_permission, created_by=principal.user_id, include_hidden=include_hidden,
        )
        return self._grant_payload(grant)

    def _admin_grant(self, principal: LocalPrincipal, grant_id: str) -> FolderGrant:
        self._require_admin(principal)
        grant = self._repository.get_grant(grant_id=grant_id)
        if grant is None:
            raise FolderUnavailableError("That access was not found.")
        return grant

    def set_access_permission(self, *, principal: LocalPrincipal, grant_id: str, max_permission: str) -> dict[str, Any]:
        self._admin_grant(principal, grant_id)
        grant = self._repository.set_grant_permission(
            grant_id=grant_id, max_permission=_require_permission(max_permission),
        )
        return self._grant_payload(grant)

    def set_access_hidden(self, *, principal: LocalPrincipal, grant_id: str, include_hidden: bool) -> dict[str, Any]:
        """Master account: show or hide hidden files for this access and every folder inside it."""
        self._admin_grant(principal, grant_id)
        grant = self._repository.set_grant_hidden(grant_id=grant_id, include_hidden=bool(include_hidden))
        counts = self._repository.folder_counts(grant_ids=[grant.grant_id])
        return self._grant_payload(grant, counts.get(grant.grant_id, 0))

    def remove_access(self, *, principal: LocalPrincipal, grant_id: str) -> None:
        self._admin_grant(principal, grant_id)
        self._repository.delete_grant(grant_id=grant_id)

    # User

    def _user_grant(self, principal: LocalPrincipal, grant_id: str) -> FolderGrant:
        grant = self._repository.get_grant(grant_id=grant_id)
        if grant is None or grant.user_id != principal.user_id:
            raise FolderUnavailableError("This folder is no longer available.")
        return grant

    def _folder_payload(
        self, folder: UserFolder, grants: dict[str, FolderGrant], *, is_admin: bool = False,
    ) -> dict[str, Any]:
        grant = grants.get(folder.grant_id)
        location_label = ""
        max_permission = "read"
        if grant is not None:
            max_permission = grant.max_permission
            location = self._locations.get(grant.location_id)
            relative = join_relative(grant.relative_path, folder.relative_path)
            location_label = self._label(location, relative) if location else relative
            status, message = self._status(lambda: self._folder_root(folder, grant))
        else:
            status, message = "unavailable", "This folder is no longer available."
        return {
            "folderId": folder.folder_id,
            "name": folder.name,
            "path": f"local/{folder.name}",
            "location": location_label,
            "permission": folder.permission,
            "maxPermission": max_permission,
            "createdByVault": folder.created_vault,
            # Hidden files: on when switched on for this folder or for the access it is inside.
            "includeHidden": folder.include_hidden or bool(grant and grant.include_hidden),
            "hiddenFromAccess": bool(grant and grant.include_hidden),
            "canChangeHidden": self._can_change_hidden(folder, is_admin),
            "status": status,
            "statusMessage": message,
        }

    @staticmethod
    def _can_change_hidden(folder: UserFolder, is_admin: bool) -> bool:
        """The master account always can; others only on folders they made in Vault."""
        return is_admin or folder.created_vault

    def list_folders(self, *, principal: LocalPrincipal) -> dict[str, Any]:
        if not self.available:
            return {"available": False, "hasAccess": False, "canAddAnywhere": False, "folders": []}
        grants = {grant.grant_id: grant for grant in self._repository.list_grants(user_id=principal.user_id)}
        folders = self._repository.list_folders(user_id=principal.user_id)
        # The master account can add any folder Vault can see; everyone else adds inside their access.
        return {
            "available": True,
            "hasAccess": bool(grants) or principal.is_device_owner,
            "canAddAnywhere": principal.is_device_owner,
            "folders": [
                self._folder_payload(folder, grants, is_admin=principal.is_device_owner) for folder in folders
            ],
        }

    def places(self, *, principal: LocalPrincipal) -> list[dict[str, Any]]:
        if not self.available:
            return []
        return [
            {
                "grantId": grant.grant_id,
                "label": self._grant_label(grant),
                "canWrite": grant.max_permission == "write",
                "status": payload["status"],
                "statusMessage": payload["statusMessage"],
            }
            for grant in self._repository.list_grants(user_id=principal.user_id)
            for payload in [self._grant_payload(grant)]
        ]

    def browse(self, *, principal: LocalPrincipal, grant_id: str, path: str | None) -> dict[str, Any]:
        grant = self._user_grant(principal, grant_id)
        location, grant_root = self._grant_root(grant)
        return {
            "grantId": grant.grant_id,
            **self._browse(location=location, base=grant_root, root_label=self._grant_label(grant),
                           path=path, can_create=grant.max_permission == "write",
                           show_hidden=grant.include_hidden),
        }

    def resolve_access_path(self, *, principal: LocalPrincipal, grant_id: str, path: str | None) -> Path:
        """A directory inside folder access the device owner gave this person (what the folder
        picker shows), refusing anything outside it."""
        grant = self._user_grant(principal, grant_id)
        location, grant_root = self._grant_root(grant)
        target = resolve_inside(grant_root, path, allow_hidden=grant.include_hidden)
        self._check_directory(location, target)
        return target

    def add_folder(
        self,
        *,
        principal: LocalPrincipal,
        grant_id: str,
        path: str | None,
        name: str,
        permission: str,
        create: bool = False,
        new_folder_name: str | None = None,
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        grant = self._user_grant(principal, grant_id)
        if include_hidden and not (create or principal.is_device_owner):
            raise FolderAdminRequiredError(
                "Only the master account can show hidden files in a folder you didn't make in Vault."
            )
        allow = grant.include_hidden
        _require_permission(permission)
        if permission == "write" and grant.max_permission != "write":
            raise FolderWriteNotAllowedError("You can only view this folder.")
        folder_name = normalize_folder_name(name)
        location, grant_root = self._grant_root(grant)
        relative = normalize_relative(path, allow_hidden=allow)
        created = False
        if create:
            if grant.max_permission != "write":
                raise FolderWriteNotAllowedError("You can't make new folders here.")
            directory_name = normalize_folder_name(new_folder_name or folder_name)
            parent = resolve_inside(grant_root, relative, allow_hidden=allow)
            self._check_directory(location, parent)
            relative = join_relative(relative, directory_name)
            target = resolve_inside(grant_root, relative, allow_hidden=allow)
            if self._repository.get_folder_by_name(user_id=principal.user_id, name=folder_name) is not None:
                raise FolderNameTakenError(f"You already have a folder named '{folder_name}'.")
            try:
                target.mkdir()
            except FileExistsError as exc:
                raise FolderExistsError("A folder with that name is already here.") from exc
            except PermissionError as exc:
                raise FolderNotAccessibleError(
                    "Vault doesn't have permission to make a folder here on the computer."
                ) from exc
            created = True
        target = resolve_inside(grant_root, relative, allow_hidden=allow)
        self._check_directory(location, target)
        try:
            folder = self._repository.insert_folder(
                user_id=principal.user_id, grant_id=grant.grant_id, relative_path=relative,
                name=folder_name, permission=permission, created_vault=created,
                include_hidden=bool(include_hidden),
            )
        except FolderNameTakenError:
            if created:
                try:
                    target.rmdir()
                except OSError:
                    pass
            raise
        return self._folder_payload(folder, {grant.grant_id: grant}, is_admin=principal.is_device_owner)

    def set_folder_permission(self, *, principal: LocalPrincipal, folder_id: str, permission: str) -> dict[str, Any]:
        folder = self._repository.get_folder(user_id=principal.user_id, folder_id=folder_id)
        if folder is None:
            raise FolderUnavailableError("This folder is no longer available.")
        grant = self._user_grant(principal, folder.grant_id)
        _require_permission(permission)
        if permission == "write" and grant.max_permission != "write":
            raise FolderWriteNotAllowedError("You can only view this folder.")
        updated = self._repository.set_folder_permission(
            user_id=principal.user_id, folder_id=folder_id, permission=permission,
        )
        return self._folder_payload(updated, {grant.grant_id: grant}, is_admin=principal.is_device_owner)

    def set_folder_hidden(self, *, principal: LocalPrincipal, folder_id: str, include_hidden: bool) -> dict[str, Any]:
        """Show or hide hidden files in this folder and everything inside it."""
        folder = self._repository.get_folder(user_id=principal.user_id, folder_id=folder_id)
        if folder is None:
            raise FolderUnavailableError("This folder is no longer available.")
        if not self._can_change_hidden(folder, principal.is_device_owner):
            raise FolderAdminRequiredError(
                "Only the master account can show hidden files in a folder you didn't make in Vault."
            )
        grant = self._user_grant(principal, folder.grant_id)
        updated = self._repository.set_folder_hidden(
            user_id=principal.user_id, folder_id=folder_id, include_hidden=bool(include_hidden),
        )
        return self._folder_payload(updated, {grant.grant_id: grant}, is_admin=principal.is_device_owner)

    def remove_folder(self, *, principal: LocalPrincipal, folder_id: str) -> None:
        """Removes access only. Files on disk are never touched."""
        folder = self._repository.get_folder(user_id=principal.user_id, folder_id=folder_id)
        self._repository.delete_folder(user_id=principal.user_id, folder_id=folder_id)
        # The master account's access is created with each folder it adds; drop it with the last folder.
        if principal.is_device_owner and folder is not None:
            if not any(other.grant_id == folder.grant_id for other in self._repository.list_folders(user_id=principal.user_id)):
                try:
                    self._repository.delete_grant(grant_id=folder.grant_id)
                except FolderUnavailableError:
                    pass

    def get_folder(self, *, principal: LocalPrincipal, folder_id: str) -> UserFolder | None:
        return self._repository.get_folder(user_id=principal.user_id, folder_id=folder_id)

    # Setup wizard (admin gives access to themselves and adds the folder in one step)

    def _unique_name(self, principal: LocalPrincipal, base: str) -> str:
        name = suggest_folder_name(base)
        candidate, counter = name, 2
        while self._repository.get_folder_by_name(user_id=principal.user_id, name=candidate) is not None:
            suffix = f" {counter}"
            candidate = f"{name[:64 - len(suffix)]}{suffix}"
            counter += 1
        return candidate

    def _home_location(self) -> DeviceLocation | None:
        return next((location for location in self._locations.values() if location.kind == "home"), None)

    def setup_vault_folder(self, *, principal: LocalPrincipal) -> dict[str, Any]:
        self._require_admin(principal)
        home = self._home_location()
        if home is None:
            raise FolderUnavailableError("Folders aren't set up on this computer.")
        documents = normalize_relative(self._documents_folder or "Documents")
        relative = join_relative(documents, VAULT_FOLDER_NAME)
        target = resolve_inside(home.path, relative)
        created = not target.exists()
        try:
            target.mkdir(parents=True, exist_ok=True)
        except PermissionError as exc:
            raise FolderNotAccessibleError(
                "Vault doesn't have permission to make a folder in Documents on the computer."
            ) from exc
        target = resolve_inside(home.path, relative)
        self._check_directory(home, target)
        grant = self._repository.upsert_grant(
            user_id=principal.user_id, location_id=home.id, relative_path=relative,
            max_permission="write", created_by=principal.user_id,
        )
        existing = next(
            (folder for folder in self._repository.list_folders(user_id=principal.user_id)
             if folder.grant_id == grant.grant_id and folder.relative_path == ""),
            None,
        )
        folder = existing or self._repository.insert_folder(
            user_id=principal.user_id, grant_id=grant.grant_id, relative_path="",
            name=self._unique_name(principal, VAULT_FOLDER_NAME), permission="write", created_vault=created,
        )
        return self._folder_payload(folder, {grant.grant_id: grant}, is_admin=True)

    def admin_add_folder(
        self,
        *,
        principal: LocalPrincipal,
        location_id: str,
        path: str | None,
        permission: str,
        name: str | None = None,
        create: bool = False,
        new_folder_name: str | None = None,
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        """Master account: add any folder Vault can see (or make one) to their own folders.

        Gives the admin access to that folder in the same step, so their folder rows behave
        like everyone else's.
        """
        self._require_admin(principal)
        _require_permission(permission)
        location = self._location(location_id)
        relative = normalize_relative(path)
        parent = resolve_inside(location.path, relative)
        self._check_directory(location, parent)
        folder_name = normalize_folder_name(name) if name else None
        created = False
        if create:
            directory_name = normalize_folder_name(new_folder_name or name or "")
            relative = join_relative(relative, directory_name)
            target = resolve_inside(location.path, relative)
            if folder_name and self._repository.get_folder_by_name(user_id=principal.user_id, name=folder_name):
                raise FolderNameTakenError(f"You already have a folder named '{folder_name}'.")
            try:
                target.mkdir()
            except FileExistsError as exc:
                raise FolderExistsError("A folder with that name is already here.") from exc
            except PermissionError as exc:
                raise FolderNotAccessibleError(
                    "Vault doesn't have permission to make a folder here on the computer."
                ) from exc
            created = True
        target = resolve_inside(location.path, relative)
        self._check_directory(location, target)
        grant = self._repository.upsert_grant(
            user_id=principal.user_id, location_id=location.id, relative_path=relative,
            max_permission="write", created_by=principal.user_id,
        )
        try:
            folder = self._repository.insert_folder(
                user_id=principal.user_id, grant_id=grant.grant_id, relative_path="",
                name=folder_name or self._unique_name(principal, last_segment(relative) or location.label),
                permission=permission, created_vault=created, include_hidden=bool(include_hidden),
            )
        except FolderNameTakenError:
            if created:
                try:
                    target.rmdir()
                except OSError:
                    pass
            raise
        return self._folder_payload(folder, {grant.grant_id: grant}, is_admin=True)

    def setup_add(
        self, *, principal: LocalPrincipal, location_id: str, path: str | None, permission: str,
    ) -> dict[str, Any]:
        """Setup wizard: add a folder with an automatic name."""
        return self.admin_add_folder(principal=principal, location_id=location_id, path=path, permission=permission)

    # Runtime: local/{name}/... for workspace tools

    def folders_for(self, *, principal: LocalPrincipal) -> list[UserFolder]:
        if not self.available:
            return []
        return self._repository.list_folders(user_id=principal.user_id)

    def resolve(self, *, principal: LocalPrincipal, view_path: str) -> FolderAccess:
        parsed = parse_local_view_path(view_path)
        if parsed is None or not parsed.mount_name:
            raise FolderUnavailableError("Choose one of your folders first.")
        if not self.available:
            raise FolderUnavailableError("Folders aren't set up on this computer.")
        folder = self._repository.get_folder_by_name(user_id=principal.user_id, name=parsed.mount_name)
        if folder is None:
            raise FolderUnavailableError("This folder is no longer available.")
        grant = self._repository.get_grant(grant_id=folder.grant_id)
        if grant is None or grant.user_id != principal.user_id:
            raise FolderUnavailableError("This folder is no longer available.")
        root = self._folder_root(folder, grant)
        include_hidden = grant.include_hidden or folder.include_hidden
        relative = normalize_relative(parsed.remainder, allow_hidden=include_hidden)
        resolve_inside(root, relative, allow_hidden=include_hidden)
        return FolderAccess(folder=folder, root=root, relative_path=relative, include_hidden=include_hidden)

    def agent_descriptors(self, *, principal: LocalPrincipal) -> list[dict[str, Any]]:
        return [
            {"path": f"local/{folder.name}", "mountName": folder.name, "permission": folder.permission}
            for folder in self.folders_for(principal=principal)
        ]
