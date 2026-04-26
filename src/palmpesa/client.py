"""
Synchronous PalmPesa HTTP client.

Handles Bearer-token authentication, retries, and error mapping for all
blocking (sync) API calls.  For async usage see :mod:`palmpesa.async_client`.
"""

from __future__ import annotations

import logging
import time
import threading
from typing import Any
try:
    from typing import Self
except ImportError:
    from typing_extensions import Self

import httpx

from .exceptions import (
    AuthenticationError,
    ConflictError,
    ForbiddenError,
    InsufficientFundsError,
    NotFoundError,
    PalmPesaError,
    RateLimitError,
    ServerError,
    ValidationError,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://palmpesa.drmlelwa.co.tz"
_DEFAULT_TIMEOUT = 30.0
_MAX_RETRIES = 3
_RETRY_STATUSES = {500, 502, 503, 504}
_INSUFFICIENT_FUNDS_PHRASES = {"insufficient balance", "insufficient funds"}


class PalmPesaClient:
    """
    Production-grade synchronous HTTP client for the PalmPesa API.

    Features
    --------
    - Bearer token authentication on every request.
    - Exponential-backoff retries on transient 5xx errors.
    - Structured exception hierarchy — never raises a bare ``Exception``.
    - Context-manager support (``with`` statement).
    - Thread-safe by design (one ``httpx.Client`` per instance).

    Parameters
    ----------
    api_token:
        Your PalmPesa Bearer API token.
    base_url:
        Override the base URL (e.g. for a staging environment).
    timeout:
        Request timeout in seconds (default: 30).
    max_retries:
        Maximum retry attempts on transient server errors (default: 3).
    """

    def __init__(
        self,
        api_token: str,
        base_url: str = _BASE_URL,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        self.api_token = api_token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._lock = threading.Lock()

        self._http = httpx.Client(
            base_url=self.base_url,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=self.timeout,
        )

    # ------------------------------------------------------------------
    # Core request dispatcher
    # ------------------------------------------------------------------

    def request(
        self,
        method: str,
        endpoint: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """
        Execute an authenticated API request with automatic retry on 5xx errors.

        Parameters
        ----------
        method:   HTTP verb (``"GET"``, ``"POST"``).
        endpoint: API path relative to the base URL (leading slash optional).
        json:     Request body dict.
        params:   Query-string parameters.

        Returns
        -------
        Parsed JSON response body.

        Raises
        ------
        :class:`~palmpesa.exceptions.PalmPesaError` or one of its subclasses.
        """
        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        auth_header = {"Authorization": f"Bearer {self.api_token}"}

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self._http.request(
                    method=method,
                    url=path,
                    json=json,
                    params=params,
                    headers=auth_header,
                )
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    _backoff(attempt)
                    continue
                raise PalmPesaError(f"Network error: {exc}") from exc

            if response.status_code in _RETRY_STATUSES and attempt < self.max_retries:
                logger.warning(
                    "Received %d on attempt %d/%d — retrying …",
                    response.status_code,
                    attempt,
                    self.max_retries,
                )
                _backoff(attempt)
                continue

            return _handle_response(response)

        raise PalmPesaError(
            f"Request failed after {self.max_retries} attempts"
        ) from last_exc

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def is_healthy(self) -> bool:
        """
        Check API reachability and token validity.

        Returns ``True`` if the API is reachable and the Bearer token is accepted.
        """
        try:
            self.request("GET", "/api/transactions", params={"page": 1, "per_page": 1})
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------

def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return {"message": response.text}


def _handle_response(response: httpx.Response) -> Any:
    """Map HTTP status codes to structured PalmPesa exceptions."""
    data = _safe_json(response)

    if response.is_success:
        return data

    msg = data.get("message", "Unknown API error") if isinstance(data, dict) else str(data)
    status = response.status_code

    # PalmPesa gateway sometimes wraps a 429 inside a 502 — detect it via details.
    if status >= 500 and isinstance(data, dict):
        details = str(data.get("details", ""))
        if "429" in details or "Too Many Requests" in details:
            raise RateLimitError(msg, status_code=429, response=data)

    if status == 400:
        if any(p in msg.lower() for p in _INSUFFICIENT_FUNDS_PHRASES):
            raise InsufficientFundsError(msg, status_code=status, response=data)
        raise ValidationError(msg, status_code=status, response=data)
    if status == 401:
        raise AuthenticationError(msg, status_code=status, response=data)
    if status == 403:
        raise ForbiddenError(msg, status_code=status, response=data)
    if status == 404:
        raise NotFoundError(msg, status_code=status, response=data)
    if status == 409:
        raise ConflictError(msg, status_code=status, response=data)
    if status == 429:
        raise RateLimitError(msg, status_code=status, response=data)
    if status >= 500:
        raise ServerError(msg, status_code=status, response=data)

    raise PalmPesaError(msg, status_code=status, response=data)


def _backoff(attempt: int) -> None:
    delay = 2 ** (attempt - 1)
    logger.debug("Retrying in %d second(s) …", delay)
    time.sleep(delay)
