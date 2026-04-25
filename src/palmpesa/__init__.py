"""
PalmPesa Python SDK
===================

Sync usage::

    from palmpesa import PalmPesa

    with PalmPesa(api_token="…") as palmpesa:
        result = palmpesa.payments.initiate_mobile_payment(
            amount=5000,
            phone="0693662424",
            transaction_id="TXN001",
            name="John Doe",
            email="john@example.com",
            callback_url="https://yourapp.com/webhook",
        )
        status = palmpesa.payments.get_order_status(result["order_id"])
        transactions = palmpesa.transactions.list_all(page=1, per_page=20)

Async usage::

    from palmpesa import AsyncPalmPesa

    async with AsyncPalmPesa(api_token="…") as palmpesa:
        result = await palmpesa.payments.initiate_mobile_payment(
            amount=5000,
            phone="0693662424",
            transaction_id="TXN001",
            name="John Doe",
            email="john@example.com",
            callback_url="https://yourapp.com/webhook",
        )
"""

from __future__ import annotations

from ._version import __version__
from .client import PalmPesaClient
from .async_client import AsyncPalmPesaClient
from .webhook import (
    WebhookValidator,
    WebhookEvent,
    PAYMENT_STATUS_COMPLETED,
    PAYMENT_STATUS_PENDING,
    PAYMENT_STATUS_FAILED,
)
from .exceptions import (
    PalmPesaError,
    AuthenticationError,
    ForbiddenError,
    ValidationError,
    InsufficientFundsError,
    NotFoundError,
    ConflictError,
    RateLimitError,
    ServerError,
)
from .services.payments import PaymentService, AsyncPaymentService
from .services.transactions import TransactionService, AsyncTransactionService
from .utils import normalize_phone, generate_transaction_id


class PalmPesa(PalmPesaClient):
    """
    Synchronous PalmPesa client with all service namespaces attached.

    Attributes:
        payments:     :class:`~palmpesa.services.payments.PaymentService`
        transactions: :class:`~palmpesa.services.transactions.TransactionService`
    """

    def __init__(
        self,
        api_token: str,
        base_url: str = "https://palmpesa.drmlelwa.co.tz",
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(api_token, base_url, timeout, max_retries)
        self.payments = PaymentService(self)
        self.transactions = TransactionService(self)


class AsyncPalmPesa(AsyncPalmPesaClient):
    """
    Asynchronous PalmPesa client with all service namespaces attached.

    Attributes:
        payments:     :class:`~palmpesa.services.payments.AsyncPaymentService`
        transactions: :class:`~palmpesa.services.transactions.AsyncTransactionService`
    """

    def __init__(
        self,
        api_token: str,
        base_url: str = "https://palmpesa.drmlelwa.co.tz",
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(api_token, base_url, timeout, max_retries)
        self.payments = AsyncPaymentService(self)
        self.transactions = AsyncTransactionService(self)


__version__ = __version__

__all__ = [
    # Main clients
    "PalmPesa",
    "AsyncPalmPesa",
    # Base clients (for subclassing)
    "PalmPesaClient",
    "AsyncPalmPesaClient",
    # Webhook
    "WebhookValidator",
    "WebhookEvent",
    "PAYMENT_STATUS_COMPLETED",
    "PAYMENT_STATUS_PENDING",
    "PAYMENT_STATUS_FAILED",
    # Utilities
    "normalize_phone",
    "generate_transaction_id",
    # Exceptions
    "PalmPesaError",
    "AuthenticationError",
    "ForbiddenError",
    "ValidationError",
    "InsufficientFundsError",
    "NotFoundError",
    "ConflictError",
    "RateLimitError",
    "ServerError",
    # Services (for type hints)
    "PaymentService",
    "AsyncPaymentService",
    "TransactionService",
    "AsyncTransactionService",
    # Version
    "__version__",
]
