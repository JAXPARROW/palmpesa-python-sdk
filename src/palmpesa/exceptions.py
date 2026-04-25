"""
PalmPesa SDK exception hierarchy.

All exceptions inherit from ``PalmPesaError`` so callers can catch the
base class when they don't need to distinguish between error types.
"""

from __future__ import annotations

from typing import Any


class PalmPesaError(Exception):
    """Base exception for all PalmPesa SDK errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"message={str(self)!r}, "
            f"status_code={self.status_code!r})"
        )


class AuthenticationError(PalmPesaError):
    """Raised on HTTP 401 — invalid or missing Bearer token."""


class ForbiddenError(PalmPesaError):
    """Raised on HTTP 403 — token valid but access denied."""


class ValidationError(PalmPesaError):
    """Raised on HTTP 400 — request payload failed server-side validation."""


class InsufficientFundsError(ValidationError):
    """Raised on HTTP 400 when the error indicates insufficient balance."""


class NotFoundError(PalmPesaError):
    """Raised on HTTP 404 — order_id or resource does not exist."""


class ConflictError(PalmPesaError):
    """Raised on HTTP 409 — duplicate transaction_id or order_id."""


class RateLimitError(PalmPesaError):
    """Raised on HTTP 429 — too many requests."""


class ServerError(PalmPesaError):
    """Raised on HTTP 5xx — unexpected server-side error."""


__all__ = [
    "PalmPesaError",
    "AuthenticationError",
    "ForbiddenError",
    "ValidationError",
    "InsufficientFundsError",
    "NotFoundError",
    "ConflictError",
    "RateLimitError",
    "ServerError",
]
