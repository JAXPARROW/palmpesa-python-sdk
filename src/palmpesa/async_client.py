"""
Asynchronous PalmPesa API v2 client — the asyncio counterpart of
:class:`~palmpesa.client.PalmPesa`.

Usage::

    async with AsyncPalmPesa(api_token="…") as palmpesa:
        payment = await palmpesa.payments.request_payment(...)
"""

from __future__ import annotations

import asyncio
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
from .services.payments import AsyncPaymentService

_T = TypeVar("_T", bound="AsyncPalmPesa")


class AsyncPalmPesa(BaseClient):
    """
    Asynchronous client for the PalmPesa Payments API v2.

    Takes the same parameters as :class:`~palmpesa.client.PalmPesa`, with
    ``http_client`` being an :class:`httpx.AsyncClient`.
    """

    payments: AsyncPaymentService

    def __init__(
        self,
        api_token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        user_agent: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            api_token,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            user_agent=user_agent,
        )
        self._owns_http = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)
        self.payments = AsyncPaymentService(self)

    # ------------------------------------------------------------------
    # Core request dispatcher
    # ------------------------------------------------------------------

    async def request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Async version of :meth:`palmpesa.client.PalmPesa.request`."""
        attempt = 0
        while True:
            response: httpx.Response | None = None
            try:
                response = await self._http.request(
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
            await asyncio.sleep(delay)
            attempt += 1

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    async def verify_credentials(self) -> None:
        """Async version of :meth:`palmpesa.client.PalmPesa.verify_credentials`."""
        try:
            await self.request("GET", self._payment_path(HEALTHCHECK_ORDER_ID))
        except NotFoundError:
            return

    async def is_healthy(self) -> bool:
        """``True`` if the API is reachable and the token is accepted."""
        try:
            await self.verify_credentials()
        except PalmPesaError:
            return False
        return True

    async def close(self) -> None:
        """Close the HTTP connection pool (only if the SDK created it)."""
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self: _T) -> _T:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()


# Backwards-compatible name from 0.1.x.
AsyncPalmPesaClient = AsyncPalmPesa

__all__ = ["AsyncPalmPesa", "AsyncPalmPesaClient"]
