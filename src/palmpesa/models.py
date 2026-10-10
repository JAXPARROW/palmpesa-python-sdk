"""
Typed models for PalmPesa API v2 payments and callbacks.

Every model keeps the untouched server payload in ``raw`` so fields added
by PalmPesa later are never lost.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any


class PaymentStatus(str, Enum):
    """Lifecycle status of a v2 payment.

    Only :attr:`COMPLETED` means money was received. ``EXPIRED`` is final in
    practice, but a late confirmation can still turn it into ``COMPLETED``.
    """

    INITIATING = "INITIATING"
    """Accepted; the prompt has not been sent yet."""
    PENDING = "PENDING"
    """Prompt sent; waiting for the customer."""
    AMBIGUOUS = "AMBIGUOUS"
    """Network timeout; PalmPesa is confirming the outcome. Do not resend."""
    COMPLETED = "COMPLETED"
    """Money received — the only status that means paid."""
    CANCELLED = "CANCELLED"
    """The customer cancelled or did not approve."""
    REJECTED = "REJECTED"
    """The mobile-money network rejected the payment."""
    INITIATION_FAILED = "INITIATION_FAILED"
    """The prompt could not be sent (see ``failure_reason``); nothing charged."""
    EXPIRED = "EXPIRED"
    """Not paid within about an hour."""
    UNKNOWN = "UNKNOWN"
    """A status this SDK version does not recognise. Treat as not final, not paid."""

    @classmethod
    def _missing_(cls, value: object) -> PaymentStatus:
        if isinstance(value, str):
            upper = value.strip().upper()
            for member in cls:
                if member.value == upper:
                    return member
        return cls.UNKNOWN

    @property
    def is_final(self) -> bool:
        return self in _FINAL_STATUSES

    @property
    def is_paid(self) -> bool:
        return self is PaymentStatus.COMPLETED


_FINAL_STATUSES = frozenset(
    {
        PaymentStatus.COMPLETED,
        PaymentStatus.CANCELLED,
        PaymentStatus.REJECTED,
        PaymentStatus.INITIATION_FAILED,
        PaymentStatus.EXPIRED,
    }
)


class FailureReason(str, Enum):
    """Why a payment ended in ``INITIATION_FAILED``."""

    SELCOM_REJECTED_ORDER = "SELCOM_REJECTED_ORDER"
    SELCOM_REJECTED_PUSH = "SELCOM_REJECTED_PUSH"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _missing_(cls, value: object) -> FailureReason:
        return cls.UNKNOWN


class CallbackEventType(str, Enum):
    """``event`` field of a callback."""

    PAYMENT_COMPLETED = "payment.completed"
    PAYMENT_CANCELLED = "payment.cancelled"
    PAYMENT_REJECTED = "payment.rejected"
    PAYMENT_INITIATION_FAILED = "payment.initiation_failed"
    PAYMENT_EXPIRED = "payment.expired"
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value: object) -> CallbackEventType:
        return cls.UNKNOWN


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Payment:
    """A v2 payment, as returned by request-payment and payment-status calls."""

    transaction_id: str
    order_id: str
    status: PaymentStatus
    amount: int
    currency: str
    failure_reason: FailureReason | None = None
    reference: str | None = None
    """Mobile-money network reference (Selcom reference) once known."""
    channel: str | None = None
    """Mobile-money channel, e.g. ``"TIGOPESATZ"``, once known."""
    created_at: datetime | None = None
    """Naive datetime exactly as PalmPesa reports it (no timezone supplied)."""
    updated_at: datetime | None = None
    status_url: str | None = None
    message: str | None = None
    """Top-level ``message`` from the response, e.g. ``"Payment accepted."``."""
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def is_final(self) -> bool:
        return self.status.is_final

    @property
    def is_paid(self) -> bool:
        return self.status.is_paid

    @classmethod
    def from_api(cls, data: Mapping[str, Any], *, message: str | None = None) -> Payment:
        failure = data.get("failure_reason")
        return cls(
            transaction_id=str(data.get("transaction_id") or ""),
            order_id=str(data.get("order_id") or ""),
            status=PaymentStatus(data.get("status") or "UNKNOWN"),
            amount=_to_int(data.get("amount")),
            currency=str(data.get("currency") or "TZS"),
            failure_reason=FailureReason(failure) if failure else None,
            reference=_opt_str(data.get("reference")),
            channel=_opt_str(data.get("channel")),
            created_at=_parse_datetime(data.get("created_at")),
            updated_at=_parse_datetime(data.get("updated_at")),
            status_url=_opt_str(data.get("status_url")),
            message=message,
            raw=dict(data),
        )


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CallbackEvent:
    """A verified callback that PalmPesa POSTs to your ``callback_url``.

    Deduplicate on :attr:`event_id` and match ``transaction_id``, ``order_id``,
    ``amount`` and ``currency`` against your own records before fulfilling.
    """

    event: CallbackEventType
    event_id: str
    transaction_id: str
    order_id: str
    status: PaymentStatus
    amount: int
    currency: str
    selcom_reference: str | None = None
    channel: str | None = None
    phone: str | None = None
    processed_at: datetime | None = None
    """Timezone-aware when PalmPesa includes an offset (it normally does)."""
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def is_final(self) -> bool:
        return self.status.is_final

    @property
    def is_paid(self) -> bool:
        return self.status.is_paid

    @classmethod
    def from_payload(cls, data: Mapping[str, Any]) -> CallbackEvent:
        return cls(
            event=CallbackEventType(data.get("event")),
            event_id=str(data.get("event_id") or ""),
            transaction_id=str(data.get("transaction_id") or ""),
            order_id=str(data.get("order_id") or ""),
            status=PaymentStatus(data.get("status") or "UNKNOWN"),
            amount=_to_int(data.get("amount")),
            currency=str(data.get("currency") or "TZS"),
            selcom_reference=_opt_str(data.get("selcom_reference")),
            channel=_opt_str(data.get("channel")),
            phone=_opt_str(data.get("phone")),
            processed_at=_parse_datetime(data.get("processed_at")),
            raw=dict(data),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _opt_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _to_int(value: Any) -> int:
    """Coerce an amount (int, ``"10000"``, ``10000.0``) to whole shillings."""
    if value is None or value == "" or isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return 0


def _parse_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        # Handles "2026-10-08 12:00:00" and "2026-10-08T12:01:31+03:00".
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


__all__ = [
    "PaymentStatus",
    "FailureReason",
    "CallbackEventType",
    "Payment",
    "CallbackEvent",
]
