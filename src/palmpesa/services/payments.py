"""
USSD payment services — initiation and order status.

Sync:  ``PaymentService``      — attach to :class:`~palmpesa.client.PalmPesaClient`.
Async: ``AsyncPaymentService`` — attach to :class:`~palmpesa.async_client.AsyncPalmPesaClient`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..exceptions import ValidationError
from ..utils import normalize_phone

if TYPE_CHECKING:
    from ..client import PalmPesaClient
    from ..async_client import AsyncPalmPesaClient


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

class PaymentService:
    """Synchronous USSD payment methods."""

    def __init__(self, client: "PalmPesaClient") -> None:
        self._c = client

    def initiate_mobile_payment(
        self,
        amount: int,
        phone: str,
        transaction_id: str,
        name: str,
        email: str,
        callback_url: str,
        address: str = "Dar es Salaam",
        postcode: str = "11111",
    ) -> dict[str, Any]:
        """
        Initiate a USSD mobile money payment (push STK prompt to customer).

        **POST** ``/api/palmpesa/initiate``

        Args:
            amount:         Amount in TZS (integer).
            phone:          Customer phone — any Tanzanian format accepted
                            (e.g. ``"0693662424"``, ``"+255693662424"``).
            transaction_id: Unique transaction reference for this payment.
            name:           Customer full name.
            email:          Customer email address.
            callback_url:   Publicly reachable URL for the payment callback.
            address:        Customer address (default: ``"Dar es Salaam"``).
            postcode:       Customer postcode (default: ``"11111"``).

        Returns:
            Dict with ``order_id`` and ``message`` fields.

        Raises:
            :class:`~palmpesa.exceptions.ValidationError`:
                When the phone number cannot be normalised.
        """
        normalised = normalize_phone(phone)
        if not normalised:
            raise ValidationError(f"Invalid Tanzanian phone number: {phone!r}")

        payload: dict[str, Any] = {
            "name": name,
            "email": email,
            "phone": normalised,
            "amount": int(amount),
            "transaction_id": transaction_id,
            "address": address,
            "postcode": postcode,
            "callback_url": callback_url,
        }
        return self._c.request("POST", "/api/palmpesa/initiate", json=payload)

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        """
        Check the status of an existing payment order.

        **POST** ``/api/order-status``

        Args:
            order_id: The ``order_id`` returned by :meth:`initiate_mobile_payment`.

        Returns:
            Dict with ``payment_status`` (``PENDING`` | ``COMPLETED`` | ``FAILED``)
            and full transaction details.
        """
        return self._c.request("POST", "/api/order-status", json={"order_id": order_id})


# ---------------------------------------------------------------------------
# Async
# ---------------------------------------------------------------------------

class AsyncPaymentService:
    """Asynchronous USSD payment methods (mirrors :class:`PaymentService`)."""

    def __init__(self, client: "AsyncPalmPesaClient") -> None:
        self._c = client

    async def initiate_mobile_payment(
        self,
        amount: int,
        phone: str,
        transaction_id: str,
        name: str,
        email: str,
        callback_url: str,
        address: str = "Dar es Salaam",
        postcode: str = "11111",
    ) -> dict[str, Any]:
        normalised = normalize_phone(phone)
        if not normalised:
            raise ValidationError(f"Invalid Tanzanian phone number: {phone!r}")

        payload: dict[str, Any] = {
            "name": name,
            "email": email,
            "phone": normalised,
            "amount": int(amount),
            "transaction_id": transaction_id,
            "address": address,
            "postcode": postcode,
            "callback_url": callback_url,
        }
        return await self._c.request("POST", "/api/palmpesa/initiate", json=payload)

    async def get_order_status(self, order_id: str) -> dict[str, Any]:
        return await self._c.request("POST", "/api/order-status", json={"order_id": order_id})


__all__ = ["PaymentService", "AsyncPaymentService"]
