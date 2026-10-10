"""
PalmPesa SDK exception hierarchy.

All exceptions inherit from ``PalmPesaError`` so callers can catch the
base class when they don't need to distinguish between error types.

Errors raised *before* a request is sent (local validation, bad config)
have ``status_code=None``.
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
        *,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response = response
        self.code = code

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"status_code={self.status_code!r}, "
            f"code={self.code!r})"
        )


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


class NetworkError(PalmPesaError):
    """The request could not be completed (DNS, connection refused, TLS, …).

    For ``request_payment`` it is safe to retry with the **same**
    ``transaction_id`` — PalmPesa returns the original payment instead of
    charging twice.
    """


class RequestTimeoutError(NetworkError):
    """The request timed out. The payment may or may not have been accepted;
    retry with the same ``transaction_id`` to find out."""


# ---------------------------------------------------------------------------
# HTTP status errors
# ---------------------------------------------------------------------------


class AuthenticationError(PalmPesaError):
    """HTTP 401 — missing, invalid or revoked API token."""


class ForbiddenError(PalmPesaError):
    """HTTP 403 — token valid but the account may not use the API
    (e.g. awaiting admin approval)."""


class AccountFrozenError(ForbiddenError):
    """HTTP 403 with ``code == "ACCOUNT_FROZEN"``."""


class ValidationError(PalmPesaError):
    """HTTP 400/422, or a payload rejected locally before sending.

    ``errors`` maps field names to messages, e.g.
    ``{"callback_url": ["The callback URL must be a publicly reachable HTTPS URL."]}``.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: dict[str, Any] | None = None,
        *,
        code: str | None = None,
        errors: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(message, status_code, response, code=code)
        self.errors: dict[str, list[str]] = errors or {}


class NotFoundError(PalmPesaError):
    """HTTP 404 — ``order_id`` unknown or belongs to another account."""


class ConflictError(PalmPesaError):
    """HTTP 409 — ``transaction_id`` already used with different payment details.

    Generate a new ``transaction_id`` for a genuinely new payment.
    """


class RateLimitError(PalmPesaError):
    """HTTP 429 — too many requests. ``retry_after`` is in seconds when known."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: dict[str, Any] | None = None,
        *,
        code: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, status_code, response, code=code)
        self.retry_after = retry_after


class ServerError(PalmPesaError):
    """HTTP 5xx — PalmPesa server error. Safe to retry with the same ``transaction_id``."""


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


class WebhookVerificationError(PalmPesaError):
    """A callback failed signature/timestamp verification or is malformed.

    Respond with HTTP 401/400 and do **not** act on the payload.
    """


__all__ = [
    "PalmPesaError",
    "NetworkError",
    "RequestTimeoutError",
    "AuthenticationError",
    "ForbiddenError",
    "AccountFrozenError",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "RateLimitError",
    "ServerError",
    "WebhookVerificationError",
]
