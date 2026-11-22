class AppError(Exception):
    """A business error shown to the user. ``status`` is the HTTP code for the API."""

    status = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    status = 404


class UnauthorizedError(AppError):
    status = 401


class ForbiddenError(AppError):
    status = 403
