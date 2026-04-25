"""
Transaction list service.

Sync:  ``TransactionService``      — attach to :class:`~palmpesa.client.PalmPesaClient`.
Async: ``AsyncTransactionService`` — attach to :class:`~palmpesa.async_client.AsyncPalmPesaClient`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..client import PalmPesaClient
    from ..async_client import AsyncPalmPesaClient


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

class TransactionService:
    """Synchronous transaction listing methods."""

    def __init__(self, client: "PalmPesaClient") -> None:
        self._c = client

    def list_all(
        self,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        """
        Retrieve a paginated list of transactions.

        **GET** ``/api/transactions``

        Args:
            page:     Page number (1-based, default: 1).
            per_page: Results per page (default: 20).

        Returns:
            Dict with transaction records and pagination metadata.
        """
        return self._c.request(
            "GET",
            "/api/transactions",
            params={"page": page, "per_page": per_page},
        )


# ---------------------------------------------------------------------------
# Async
# ---------------------------------------------------------------------------

class AsyncTransactionService:
    """Asynchronous transaction listing methods (mirrors :class:`TransactionService`)."""

    def __init__(self, client: "AsyncPalmPesaClient") -> None:
        self._c = client

    async def list_all(
        self,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        return await self._c.request(
            "GET",
            "/api/transactions",
            params={"page": page, "per_page": per_page},
        )


__all__ = ["TransactionService", "AsyncTransactionService"]
