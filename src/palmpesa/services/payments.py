"""
Payments API v2 — request a mobile-money payment and check its status.

Sync:  ``PaymentService``      — available as ``PalmPesa(...).payments``.
Async: ``AsyncPaymentService`` — available as ``AsyncPalmPesa(...).payments``.
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from typing import TYPE_CHECKING

from .._base import PAYMENTS_PATH, BaseClient, unwrap_payment
from ..models import Payment
from ..utils import build_payment_payload

if TYPE_CHECKING:
    from ..async_client import AsyncPalmPesa
    from ..client import PalmPesa

# GET /payments/{order_id} allows 120 requests/minute per account.
_MIN_POLL_INTERVAL = 1.0


def _check_poll_args(timeout: float, poll_interval: float) -> None:
    if timeout < 0:
        raise ValueError("timeout must be >= 0")
    if poll_interval < _MIN_POLL_INTERVAL:
        raise ValueError(f"poll_interval must be >= {_MIN_POLL_INTERVAL}s (rate limit)")


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


class PaymentService:
    """Synchronous Payments API v2 methods."""

    def __init__(self, client: PalmPesa) -> None:
        self._client = client

    def request_payment(
        self,
        *,
        transaction_id: str,
        amount: int | Decimal,
        phone: str,
        name: str,
        email: str,
        callback_url: str,
        buyer_remarks: str | None = None,
        merchant_remarks: str | None = None,
        currency: str = "TZS",
    ) -> Payment:
        """
        Send a mobile-money prompt to the customer's phone.

        **POST** ``/api/v2/async/payments`` → 202 with status ``INITIATING``.
        Acceptance does **not** mean paid — wait for the callback (or poll)
        until :attr:`Payment.is_paid`.

        Calling again with the same ``transaction_id`` and details returns
        the original payment (no second prompt or charge); different details
        raise :class:`~palmpesa.exceptions.ConflictError`.

        Args:
            transaction_id: Your unique payment ID (≤191 chars of
                ``A-Z a-z 0-9 . _ : -``). Store it before calling.
            amount:         Whole TZS, 100 – 100,000,000 (``int`` or integral ``Decimal``).
            phone:          Tanzanian mobile number in any common format.
            name:           Customer name (≤255 chars).
            email:          Customer email.
            callback_url:   Public HTTPS URL that receives the final-status callback.
            buyer_remarks:  Optional note shown to the customer (≤255 chars).
            merchant_remarks: Optional internal note (≤255 chars).
            currency:       Must be ``"TZS"``.

        Raises:
            ValidationError: invalid input (raised locally, before sending) or HTTP 422.
            ConflictError:   ``transaction_id`` reused with different details.
            AuthenticationError, ForbiddenError, RateLimitError, ServerError, NetworkError.
        """
        payload = build_payment_payload(
            transaction_id=transaction_id,
            amount=amount,
            phone=phone,
            name=name,
            email=email,
            callback_url=callback_url,
            currency=currency,
            buyer_remarks=buyer_remarks,
            merchant_remarks=merchant_remarks,
        )
        body = self._client.request("POST", PAYMENTS_PATH, json=payload)
        data, message = unwrap_payment(body)
        return Payment.from_api(data, message=message)

    def get_payment(self, order_id: str) -> Payment:
        """
        Fetch a payment's current status.

        **GET** ``/api/v2/async/payments/{order_id}``

        Raises:
            NotFoundError: unknown ``order_id`` or one owned by another account.
        """
        body = self._client.request("GET", BaseClient._payment_path(order_id))
        data, message = unwrap_payment(body)
        return Payment.from_api(data, message=message)

    def wait_for_final_status(
        self,
        order_id: str,
        *,
        timeout: float = 300.0,
        poll_interval: float = 5.0,
    ) -> Payment:
        """
        Poll :meth:`get_payment` until the payment is final or ``timeout`` elapses.

        Returns the last observed :class:`Payment` — check ``.is_final`` to tell
        a timeout from a final result. Prefer callbacks in production; use this
        for scripts, tests and as a fallback reconciler.
        """
        _check_poll_args(timeout, poll_interval)
        deadline = time.monotonic() + timeout
        while True:
            payment = self.get_payment(order_id)
            remaining = deadline - time.monotonic()
            if payment.is_final or remaining <= 0:
                return payment
            time.sleep(min(poll_interval, remaining))


# ---------------------------------------------------------------------------
# Async
# ---------------------------------------------------------------------------


class AsyncPaymentService:
    """Asynchronous Payments API v2 methods (mirrors :class:`PaymentService`)."""

    def __init__(self, client: AsyncPalmPesa) -> None:
        self._client = client

    async def request_payment(
        self,
        *,
        transaction_id: str,
        amount: int | Decimal,
        phone: str,
        name: str,
        email: str,
        callback_url: str,
        buyer_remarks: str | None = None,
        merchant_remarks: str | None = None,
        currency: str = "TZS",
    ) -> Payment:
        """Async version of :meth:`PaymentService.request_payment`."""
        payload = build_payment_payload(
            transaction_id=transaction_id,
            amount=amount,
            phone=phone,
            name=name,
            email=email,
            callback_url=callback_url,
            currency=currency,
            buyer_remarks=buyer_remarks,
            merchant_remarks=merchant_remarks,
        )
        body = await self._client.request("POST", PAYMENTS_PATH, json=payload)
        data, message = unwrap_payment(body)
        return Payment.from_api(data, message=message)

    async def get_payment(self, order_id: str) -> Payment:
        """Async version of :meth:`PaymentService.get_payment`."""
        body = await self._client.request("GET", BaseClient._payment_path(order_id))
        data, message = unwrap_payment(body)
        return Payment.from_api(data, message=message)

    async def wait_for_final_status(
        self,
        order_id: str,
        *,
        timeout: float = 300.0,
        poll_interval: float = 5.0,
    ) -> Payment:
        """Async version of :meth:`PaymentService.wait_for_final_status`."""
        _check_poll_args(timeout, poll_interval)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            payment = await self.get_payment(order_id)
            remaining = deadline - loop.time()
            if payment.is_final or remaining <= 0:
                return payment
            await asyncio.sleep(min(poll_interval, remaining))


__all__ = ["PaymentService", "AsyncPaymentService"]
