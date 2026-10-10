"""
Synchronous PalmPesa API v2 client.

Usage::

    with PalmPesa(api_token="…") as palmpesa:
        payment = palmpesa.payments.request_payment(...)

For asyncio see :mod:`palmpesa.async_client`.
"""

from __future__ import annotations

import time
from typing import Any, TypeVar

import httpx

from ._base import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    HEALTHCHECK_ORDER_ID,
    RETRY_STATUSES,
    BaseClient,
    log_retry,
    parse_response,
    retry_delay,
)
from .exceptions import NetworkError, NotFoundError, PalmPesaError, RequestTimeoutError
from .services.payments import PaymentService

_T = TypeVar("_T", bound="PalmPesa")


class PalmPesa(BaseClient):
    """
    Synchronous client for the PalmPesa Payments API v2.

    Parameters
    ----------
    api_token:
        Bearer token from the PalmPesa dashboard. Keep it server-side.
    base_url:
        API host (default ``https://palmpesa.co.tz``).
    timeout:
        Seconds, or an :class:`httpx.Timeout` (default 30).
    max_retries:
        Extra attempts after the first on network errors, timeouts, 429 and
        5xx (default 2). Retrying ``request_payment`` is safe because PalmPesa
        de-duplicates on ``transaction_id``.
    user_agent:
        Optional suffix appended to the SDK's ``User-Agent``.
    http_client:
        Bring your own :class:`httpx.Client` (proxies, custom TLS, …). The SDK
        will not close a client it did not create.

    The instance is thread-safe; share one per process.
    """

    payments: PaymentService

    def __init__(
        self,
        api_token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        user_agent: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        super().__init__(
            api_token,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            user_agent=user_agent,
        )
        self._owns_http = http_client is None
        self._http = http_client or httpx.Client(timeout=timeout, follow_redirects=False)
        self.payments = PaymentService(self)

    # ------------------------------------------------------------------
    # Core request dispatcher
    # ------------------------------------------------------------------

    def request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Send an authenticated request, retrying transient failures.

        Returns the parsed JSON body; raises a
        :class:`~palmpesa.exceptions.PalmPesaError` subclass otherwise.
        """
        attempt = 0
        while True:
            response: httpx.Response | None = None
            try:
                response = self._http.request(
                    method, self._url(path), json=json, headers=self._headers
                )
            except httpx.TimeoutException as exc:
                if attempt >= self.max_retries:
                    raise RequestTimeoutError(f"PalmPesa request timed out: {exc}") from exc
                reason = "timeout"
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    raise NetworkError(f"PalmPesa network error: {exc}") from exc
                reason = type(exc).__name__
            else:
                if response.status_code not in RETRY_STATUSES or attempt >= self.max_retries:
                    return parse_response(response)
                reason = f"HTTP {response.status_code}"

            delay = retry_delay(attempt, response)
            log_retry(method, path, attempt, self.max_retries, reason, delay)
            time.sleep(delay)
            attempt += 1

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def verify_credentials(self) -> None:
        """
        Confirm the API is reachable and the token is accepted.

        Looks up a non-existent order (expects 404), so no payment is created.

        Raises:
            AuthenticationError / ForbiddenError / NetworkError / …
        """
        try:
            self.request("GET", self._payment_path(HEALTHCHECK_ORDER_ID))
        except NotFoundError:
            return

    def is_healthy(self) -> bool:
        """``True`` if the API is reachable and the token is accepted."""
        try:
            self.verify_credentials()
        except PalmPesaError:
            return False
        return True

    def close(self) -> None:
        """Close the HTTP connection pool (only if the SDK created it)."""
        if self._owns_http:
            self._http.close()

    def __enter__(self: _T) -> _T:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


# Backwards-compatible name from 0.1.x.
PalmPesaClient = PalmPesa

__all__ = ["PalmPesa", "PalmPesaClient"]
