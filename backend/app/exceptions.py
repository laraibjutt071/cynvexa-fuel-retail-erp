class AppError(Exception):
    """Base for domain errors that are safe to show to the client as-is."""

    status_code: int = 400

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class ValidationFailedError(AppError):
    status_code = 422


class AuthenticationError(AppError):
    status_code = 401


class ServiceUnavailableError(AppError):
    status_code = 503


class PermissionDeniedError(AppError):
    status_code = 403

    def __init__(self, detail: str = "You do not have permission to perform this action."):
        super().__init__(detail)
