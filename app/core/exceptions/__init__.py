from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "AccountLockedError",
    "AppError",
    "BadRequestError",
    "ConflictError",
    "ForbiddenError",
    "GoneError",
    "InvalidTokenError",
    "MaskedNotFoundError",
    "NotFoundError",
    "RateLimitError",
    "UnauthorizedError",
    "register_exception_handlers",
]

_EXPORTS = {
    "AccountLockedError": ("app.core.exceptions.base", "AccountLockedError"),
    "AppError": ("app.core.exceptions.base", "AppError"),
    "BadRequestError": ("app.core.exceptions.base", "BadRequestError"),
    "ConflictError": ("app.core.exceptions.base", "ConflictError"),
    "ForbiddenError": ("app.core.exceptions.base", "ForbiddenError"),
    "GoneError": ("app.core.exceptions.base", "GoneError"),
    "InvalidTokenError": ("app.core.exceptions.base", "InvalidTokenError"),
    "MaskedNotFoundError": ("app.core.exceptions.base", "MaskedNotFoundError"),
    "NotFoundError": ("app.core.exceptions.base", "NotFoundError"),
    "RateLimitError": ("app.core.exceptions.base", "RateLimitError"),
    "UnauthorizedError": ("app.core.exceptions.base", "UnauthorizedError"),
    "register_exception_handlers": ("app.core.exceptions.handlers", "register_exception_handlers"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, export_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), export_name)
    globals()[name] = value
    return value
