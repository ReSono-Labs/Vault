from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


@dataclass(slots=True)
class WorkspaceFileEntry:
    kind: str
    name: str
    path: str
    sizeBytes: int | None = None
    childCount: int | None = None
    mimeType: str | None = None
    editable: bool | None = None
    projectionVersion: int | None = None
    updatedAt: datetime | None = None
    shared: bool = False
    shareId: str | None = None
    sharedFrom: str | None = None
    permission: str | None = None
    linked: bool = False
    pathArea: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["updatedAt"] = _iso(self.updatedAt)
        if not self.shared:
            payload.pop("shareId", None)
            payload.pop("sharedFrom", None)
            if not self.linked:
                payload.pop("permission", None)
        if not self.linked:
            payload.pop("linked", None)
        if not self.pathArea:
            payload.pop("pathArea", None)
        return {key: value for key, value in payload.items() if value is not None or key in {"kind", "name", "path"}}


@dataclass(slots=True)
class WorkspaceFileDirectory:
    currentDirectory: str
    parentDirectory: str | None
    entries: list[WorkspaceFileEntry]
    shareId: str | None = None
    permission: str | None = None
    pathArea: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "currentDirectory": self.currentDirectory,
            "parentDirectory": self.parentDirectory,
            "entries": [entry.to_dict() for entry in self.entries],
            **({"shareId": self.shareId} if self.shareId else {}),
            **({"permission": self.permission} if self.permission else {}),
            **({"pathArea": self.pathArea} if self.pathArea else {}),
        }


@dataclass(slots=True)
class WorkspaceFileRead:
    fileKey: str
    filename: str
    contentMarkdown: str
    sizeBytes: int
    mimeType: str | None
    editable: bool
    projectionVersion: int
    updatedAt: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "fileKey": self.fileKey,
            "filename": self.filename,
            "contentMarkdown": self.contentMarkdown,
            "sizeBytes": self.sizeBytes,
            "mimeType": self.mimeType,
            "editable": self.editable,
            "projectionVersion": self.projectionVersion,
            "updatedAt": _iso(self.updatedAt),
        }


@dataclass(slots=True)
class WorkspaceFileMutation:
    status: str
    message: str
    affectedCount: int
    path: str | None = None
    destinationPath: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class WorkspaceFolderShareView:
    shareId: str
    folderPath: str
    granteeUserId: str
    granteeDisplayName: str
    granteeUsername: str
    permission: str
    shareKind: str = "folder"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
