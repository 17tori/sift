from __future__ import annotations


class AppError(Exception):
    """Domain error with a stable machine-readable code that the Mini App translates."""

    status_code = 400

    def __init__(self, code: str, message: str = "", status_code: int | None = None, **details: object) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.details = details
        if status_code is not None:
            self.status_code = status_code


class NotFound(AppError):
    status_code = 404


class Forbidden(AppError):
    status_code = 403


class QuotaExceeded(AppError):
    status_code = 402


class RateLimited(AppError):
    status_code = 429
