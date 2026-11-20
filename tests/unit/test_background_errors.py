"""BG-10: the shared background errors are the same classes through the old and new import paths."""
from app.vault_runtime.background_agent import errors, repository


def test_repository_reexports_are_the_error_module_classes():
    assert repository.BackgroundRunAuthorizationError is errors.BackgroundRunAuthorizationError
    assert repository.BackgroundRunConflictError is errors.BackgroundRunConflictError
    assert repository.BackgroundRunAdmissionBusy is errors.BackgroundRunAdmissionBusy
    assert issubclass(errors.BackgroundRunAdmissionBusy, errors.BackgroundRunConflictError)
