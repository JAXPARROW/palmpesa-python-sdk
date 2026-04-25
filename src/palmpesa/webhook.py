"""
Webhook callback helpers for PalmPesa payment notifications.

PalmPesa sends a POST to the ``callback_url`` you supply in the payment
initiation request.  The callback body looks like::

    {
        "order_id": "PALMPESA…",
        "payment_status": "COMPLETED"   # or "PENDING" / "FAILED"
    }

There is no documented signature or HMAC scheme — simply receive the POST,
parse the body, and act on ``payment_status``.
"""

from __future__ import annotations


PAYMENT_STATUS_COMPLETED = "COMPLETED"
PAYMENT_STATUS_PENDING = "PENDING"
PAYMENT_STATUS_FAILED = "FAILED"

_VALID_STATUSES = {PAYMENT_STATUS_COMPLETED, PAYMENT_STATUS_PENDING, PAYMENT_STATUS_FAILED}


class WebhookEvent:
    """
    Parsed representation of a PalmPesa payment callback payload.

    Args:
        payload: The raw dict received in the callback POST body.

    Attributes:
        order_id:       PalmPesa order identifier.
        payment_status: ``"COMPLETED"``, ``"PENDING"``, or ``"FAILED"``.
        raw:            The original payload dict.
    """

    def __init__(self, payload: dict) -> None:
        self.raw = payload
        self.order_id: str = payload.get("order_id", "")
        self.payment_status: str = payload.get("payment_status", "")

    @property
    def is_completed(self) -> bool:
        return self.payment_status == PAYMENT_STATUS_COMPLETED

    @property
    def is_failed(self) -> bool:
        return self.payment_status == PAYMENT_STATUS_FAILED

    @property
    def is_pending(self) -> bool:
        return self.payment_status == PAYMENT_STATUS_PENDING

    def __repr__(self) -> str:
        return f"WebhookEvent(order_id={self.order_id!r}, payment_status={self.payment_status!r})"


class WebhookValidator:
    """Helper for parsing and basic validation of PalmPesa callback payloads."""

    @staticmethod
    def parse(payload: dict) -> WebhookEvent:
        """
        Parse a raw callback payload into a :class:`WebhookEvent`.

        Args:
            payload: Dict decoded from the callback POST body.

        Returns:
            :class:`WebhookEvent` instance.
        """
        return WebhookEvent(payload)

    @staticmethod
    def is_valid_payload(payload: dict) -> bool:
        """
        Return ``True`` if the payload contains the required callback fields.

        Checks that ``order_id`` is present and ``payment_status`` is one of
        the recognised values (``COMPLETED``, ``PENDING``, ``FAILED``).
        """
        return (
            isinstance(payload, dict)
            and bool(payload.get("order_id"))
            and payload.get("payment_status") in _VALID_STATUSES
        )


__all__ = [
    "WebhookValidator",
    "WebhookEvent",
    "PAYMENT_STATUS_COMPLETED",
    "PAYMENT_STATUS_PENDING",
    "PAYMENT_STATUS_FAILED",
]
