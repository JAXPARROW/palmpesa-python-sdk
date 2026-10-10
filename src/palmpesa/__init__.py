"""
PalmPesa Python SDK — Payments API v2
=====================================

Sync usage::

    from palmpesa import PalmPesa, generate_transaction_id

    with PalmPesa(api_token="…") as palmpesa:
        payment = palmpesa.payments.request_payment(
            transaction_id=generate_transaction_id("ORDER"),
            amount=10_000,
            phone="0712345678",
            name="Juma Hassan",
            email="juma@example.com",
            callback_url="https://shop.example.com/palmpesa/callback",
        )
        payment = palmpesa.payments.get_payment(payment.order_id)
        if payment.is_paid:
            ...

Async usage::

    from palmpesa import AsyncPalmPesa

    async with AsyncPalmPesa(api_token="…") as palmpesa:
        payment = await palmpesa.payments.request_payment(...)
"""

from __future__ import annotations

from ._version import __version__
from .async_client import AsyncPalmPesa, AsyncPalmPesaClient
from .client import PalmPesa, PalmPesaClient
from .exceptions import (
    AccountFrozenError,
    AuthenticationError,
    ConflictError,
    ForbiddenError,
    NetworkError,
    NotFoundError,
    PalmPesaError,
    RateLimitError,
    RequestTimeoutError,
    ServerError,
    ValidationError,
    WebhookVerificationError,
)
from .models import CallbackEvent, CallbackEventType, FailureReason, Payment, PaymentStatus
from .services.payments import AsyncPaymentService, PaymentService
from .utils import MAX_AMOUNT, MIN_AMOUNT, generate_transaction_id, normalize_phone
from .webhook import (
    EVENT_ID_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    WebhookVerifier,
    compute_signature,
    parse_callback,
)

__all__ = [
    "__version__",
    # Clients
    "PalmPesa",
    "AsyncPalmPesa",
    "PalmPesaClient",
    "AsyncPalmPesaClient",
    # Services (for type hints)
    "PaymentService",
    "AsyncPaymentService",
    # Models
    "Payment",
    "PaymentStatus",
    "FailureReason",
    "CallbackEvent",
    "CallbackEventType",
    # Callbacks
    "WebhookVerifier",
    "parse_callback",
    "compute_signature",
    "EVENT_ID_HEADER",
    "TIMESTAMP_HEADER",
    "SIGNATURE_HEADER",
    # Utilities
    "normalize_phone",
    "generate_transaction_id",
    "MIN_AMOUNT",
    "MAX_AMOUNT",
    # Exceptions
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
