"""
Transport logic shared by the sync and async clients: configuration,
retry policy and HTTP-status → exception mapping.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from ._version import __version__
from .exceptions import (
    AccountFrozenError,
    AuthenticationError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PalmPesaError,
    RateLimitError,
    ServerError,
    ValidationError,
)

logger = logging.getLogger("palmpesa")

DEFAULT_BASE_URL = "https://palmpesa.co.tz"
PAYMENTS_PATH = "/api/v2/async/payments"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 2

# POST /payments is idempotent on transaction_id (same details → original
# payment, no second charge), so retrying it on these is safe.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_BACKOFF_BASE = 0.5
_BACKOFF_CAP = 8.0
_RETRY_AFTER_CAP = 60.0

# Used by is_healthy(): looking up an order that cannot exist returns 404 when
# the token is valid, and 401/403 otherwise — no payment is ever created.
HEALTHCHECK_ORDER_ID = "PALMPESAV2A00000000000000000SDKHEALTH"

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class BaseClient:
    """Configuration and helpers common to :class:`PalmPesa` and :class:`AsyncPalmPesa`."""

    def __init__(
        self,
        api_token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        user_agent: str | None = None,
    ) -> None:
        if not api_token or not isinstance(api_token, str) or not api_token.strip():
            raise ValueError("api_token is required")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")

        base_url = base_url.rstrip("/")
        parts = urlsplit(base_url)
        if parts.scheme != "https" and not (
            parts.scheme == "http" and (parts.hostname or "") in _LOCAL_HOSTS
        ):
            raise ValueError("base_url must use https:// (http is allowed only for localhost)")

        self._api_token = api_token.strip()
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        ua = f"palmpesa-python-sdk/{__version__}"
        self._headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Accept": "application/json",
            "User-Agent": f"{ua} {user_agent}" if user_agent else ua,
        }

    def __repr__(self) -> str:
        # Never expose the token in logs/tracebacks.
        return f"{type(self).__name__}(base_url={self.base_url!r}, max_retries={self.max_retries})"

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    @staticmethod
    def _payment_path(order_id: str) -> str:
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValidationError("order_id is required", errors={"order_id": ["required"]})
        return f"{PAYMENTS_PATH}/{quote(order_id.strip(), safe='')}"


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


def retry_delay(attempt: int, response: httpx.Response | None = None) -> float:
    """Seconds to wait before retry number ``attempt`` (0-based).

    Honours ``Retry-After`` when present, otherwise exponential backoff with
    jitter so many workers don't retry in lock-step.
    """
    if response is not None:
        retry_after = parse_retry_after(response)
        if retry_after is not None:
            return min(retry_after, _RETRY_AFTER_CAP)
    ceiling: float = min(_BACKOFF_CAP, _BACKOFF_BASE * (2**attempt))
    return float(random.uniform(ceiling / 2, ceiling))


def parse_retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


def log_retry(
    method: str, path: str, attempt: int, max_retries: int, reason: str, delay: float
) -> None:
    logger.warning(
        "PalmPesa %s %s failed (%s); retry %d/%d in %.1fs",
        method,
        path,
        reason,
        attempt + 1,
        max_retries,
        delay,
    )


# ---------------------------------------------------------------------------
# Response handling
# ---------------------------------------------------------------------------


def parse_response(response: httpx.Response) -> dict[str, Any]:
    """Return the JSON body of a successful response or raise a typed error."""
    data = _safe_json(response)

    if response.is_success:
        if not isinstance(data, dict):
            raise PalmPesaError(
                f"Unexpected non-JSON response from PalmPesa (HTTP {response.status_code})",
                status_code=response.status_code,
                response={"body": response.text[:500]},
            )
        if data.get("success") is False:
            raise PalmPesaError(
                _message(data, response),
                status_code=response.status_code,
                response=data,
                code=_opt_code(data),
            )
        return data

    raise error_from_response(response, data)


def error_from_response(response: httpx.Response, data: Any = None) -> PalmPesaError:
    if data is None:
        data = _safe_json(response)
    body: dict[str, Any] = data if isinstance(data, dict) else {"body": response.text[:500]}
    status = response.status_code
    msg = _message(body, response)
    code = _opt_code(body)

    if status in (400, 422):
        errors = body.get("errors")
        return ValidationError(
            msg,
            status,
            body,
            code=code,
            errors=errors if isinstance(errors, dict) else None,
        )
    if status == 401:
        return AuthenticationError(msg, status, body, code=code)
    if status == 403:
        if code == "ACCOUNT_FROZEN":
            return AccountFrozenError(msg, status, body, code=code)
        return ForbiddenError(msg, status, body, code=code)
    if status == 404:
        return NotFoundError(msg, status, body, code=code)
    if status == 409:
        return ConflictError(msg, status, body, code=code)
    if status == 429:
        return RateLimitError(msg, status, body, code=code, retry_after=parse_retry_after(response))
    if status >= 500:
        return ServerError(msg, status, body, code=code)
    return PalmPesaError(msg, status, body, code=code)


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _message(body: dict[str, Any], response: httpx.Response) -> str:
    for key in ("message", "error"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    return f"HTTP {response.status_code} {response.reason_phrase}".strip()


def _opt_code(body: dict[str, Any]) -> str | None:
    code = body.get("code")
    return str(code) if code else None


def unwrap_payment(body: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Extract ``data`` (the payment) and top-level ``message`` from a response."""
    data = body.get("data")
    if not isinstance(data, dict) or not data.get("order_id"):
        raise PalmPesaError("PalmPesa response is missing payment data", response=body)
    message = body.get("message")
    return data, message if isinstance(message, str) else None
