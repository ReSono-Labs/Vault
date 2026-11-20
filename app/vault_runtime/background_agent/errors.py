"""Errors shared by every background component (coordinator, jobs, actions, approvals, tools)."""


class BackgroundRunAuthorizationError(RuntimeError):
    pass


class BackgroundRunConflictError(RuntimeError):
    pass


class BackgroundRunAdmissionBusy(BackgroundRunConflictError):
    pass
