class WorkspaceFileError(RuntimeError):
    code = "workspace_file_error"


class WorkspaceFileNotFoundError(WorkspaceFileError):
    code = "not_found"


class WorkspaceFileConflictError(WorkspaceFileError):
    code = "conflict"


class WorkspaceFileForbiddenError(WorkspaceFileError):
    code = "forbidden"


class WorkspaceFileBadRequestError(WorkspaceFileError):
    code = "invalid_request"
