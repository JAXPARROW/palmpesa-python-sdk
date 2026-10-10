from __future__ import annotations

from typing import Any

import pytest

BASE = "https://palmpesa.co.tz"
PAYMENTS_URL = f"{BASE}/api/v2/async/payments"
ORDER_ID = "PALMPESAV2A20261008120000123EFGH5678"


def payment_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "transaction_id": "ORDER-2026-000123",
        "order_id": ORDER_ID,
        "status": "INITIATING",
        "failure_reason": None,
        "amount": 10000,
        "currency": "TZS",
        "reference": None,
        "channel": None,
        "created_at": "2026-10-08 12:00:00",
        "updated_at": "2026-10-08 12:00:00",
        "status_url": f"{PAYMENTS_URL}/{ORDER_ID}",
    }
    data.update(overrides)
    return data


def accepted_body(**overrides: Any) -> dict[str, Any]:
    return {"success": True, "message": "Payment accepted.", "data": payment_data(**overrides)}


def status_body(**overrides: Any) -> dict[str, Any]:
    return {"success": True, "data": payment_data(**overrides)}


PAYMENT_KWARGS: dict[str, Any] = {
    "transaction_id": "ORDER-2026-000123",
    "amount": 10000,
    "phone": "0712345678",
    "name": "Juma Hassan",
    "email": "juma@example.com",
    "callback_url": "https://shop.example.com/palmpesa/callback",
}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make retries and polling instant."""

    async def _async_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("palmpesa.client.time.sleep", lambda _: None)
    monkeypatch.setattr("palmpesa.async_client.asyncio.sleep", _async_sleep)
