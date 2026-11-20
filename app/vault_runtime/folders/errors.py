from __future__ import annotations

from app.vault_runtime.workspace_files.errors import WorkspaceFileError


class FolderError(WorkspaceFileError):
    """Folder errors share the workspace error type so workspace routes and tools report them."""

    code = "folder_error"
    status = 400


class FolderUnavailableError(FolderError):
    code = "folder_unavailable"
    status = 404


class DriveDisconnectedError(FolderError):
    code = "drive_disconnected"
    status = 409


class FolderNotAccessibleError(FolderError):
    code = "not_accessible"
    status = 409


class FolderWriteNotAllowedError(FolderError):
    code = "write_not_allowed"
    status = 403


class FolderOutsideAccessError(FolderError):
    code = "outside_access"
    status = 400


class FolderHiddenPathError(FolderError):
    code = "hidden_path"
    status = 400


class FolderNameTakenError(FolderError):
    code = "name_taken"
    status = 409


class FolderExistsError(FolderError):
    code = "folder_exists"
    status = 409


class FolderAdminRequiredError(FolderError):
    code = "admin_required"
    status = 403


class FolderInvalidRequestError(FolderError):
    code = "invalid_request"
    status = 400
