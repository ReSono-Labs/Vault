from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

LOCATION_KINDS = frozenset({"home", "drives", "drive"})
PERMISSIONS = ("read", "write")


@dataclass(frozen=True, slots=True)
class DeviceLocation:
    """A host directory Vault can see, configured at install time."""

    id: str
    label: str
    path: Path
    kind: str


@dataclass(frozen=True, slots=True)
class FolderGrant:
    """Admin-assigned access for one user to a directory inside a device location."""

    grant_id: str
    user_id: str
    location_id: str
    relative_path: str
    max_permission: str
    created_at: datetime
    # Set by the master account; covers this access and every folder added inside it.
    include_hidden: bool = False


@dataclass(frozen=True, slots=True)
class UserFolder:
    """A directory a user added inside one of their grants; agents see it as local/{name}."""

    folder_id: str
    user_id: str
    grant_id: str
    relative_path: str
    name: str
    permission: str
    created_vault: bool
    created_at: datetime
    # Set by the master account, or by the user on a folder they made in Vault.
    include_hidden: bool = False


@dataclass(frozen=True, slots=True)
class FolderAccess:
    folder: UserFolder
    root: Path
    relative_path: str
    include_hidden: bool = False

    @property
    def can_write(self) -> bool:
        return self.folder.permission == "write"

    @property
    def view_root(self) -> str:
        return f"local/{self.folder.name}"
