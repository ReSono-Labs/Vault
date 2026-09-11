class AppError(Exception):
    status_code = 500
    code = "internal_error"
    message = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        target: str | None = None,
        details: dict | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.target = target
        self.details = details
        super().__init__(self.message)


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Authentication is required."


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Too many requests. Try again later."


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"
    message = "The request is invalid."


class InvalidTokenError(UnauthorizedError):
    code = "invalid_token"
    message = "The access token is invalid or expired."


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    message = "You are not allowed to perform this action."


class AccountLockedError(AppError):
    status_code = 423
    code = "account_locked"
    message = "The account is locked."


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "The requested resource was not found."


class MaskedNotFoundError(NotFoundError):
    code = "resource_not_found"
    message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "The request conflicts with the current resource state."


class GoneError(AppError):
    status_code = 410
    code = "gone"
    message = "The requested action is no longer available."
