"""Tests for sync and async PalmPesa clients."""

from __future__ import annotations

import pytest
import httpx
import respx

from palmpesa import PalmPesa, AsyncPalmPesa
from palmpesa.exceptions import (
    AuthenticationError,
    ValidationError,
    NotFoundError,
    ServerError,
)
from palmpesa.utils import normalize_phone, generate_transaction_id

BASE = "https://palmpesa.drmlelwa.co.tz"


# ---------------------------------------------------------------------------
# normalize_phone
# ---------------------------------------------------------------------------

class TestNormalizePhone:
    def test_local_format_passthrough(self):
        assert normalize_phone("0693662424") == "0693662424"

    def test_255_prefix(self):
        assert normalize_phone("255693662424") == "0693662424"

    def test_plus_255_prefix(self):
        assert normalize_phone("+255693662424") == "0693662424"

    def test_nine_digits(self):
        assert normalize_phone("693662424") == "0693662424"

    def test_invalid_returns_empty(self):
        assert normalize_phone("123") == ""

    def test_empty_returns_empty(self):
        assert normalize_phone("") == ""


# ---------------------------------------------------------------------------
# generate_transaction_id
# ---------------------------------------------------------------------------

class TestGenerateTransactionId:
    def test_default_prefix(self):
        txn_id = generate_transaction_id()
        assert txn_id.startswith("TXN")
        assert len(txn_id) > 3

    def test_custom_prefix(self):
        txn_id = generate_transaction_id("ORD")
        assert txn_id.startswith("ORD")

    def test_unique(self):
        ids = {generate_transaction_id() for _ in range(50)}
        assert len(ids) == 50


# ---------------------------------------------------------------------------
# Sync client
# ---------------------------------------------------------------------------

@respx.mock
def test_initiate_mobile_payment_success():
    respx.post(f"{BASE}/api/palmpesa/initiate").mock(
        return_value=httpx.Response(
            200, json={"order_id": "PALMPESAORD001", "message": "Payment initiated"}
        )
    )
    with PalmPesa(api_token="test-token") as pp:
        result = pp.payments.initiate_mobile_payment(
            amount=5000,
            phone="0693662424",
            transaction_id="TXN001",
            name="John Doe",
            email="john@example.com",
            callback_url="https://example.com/webhook",
        )
    assert result["order_id"] == "PALMPESAORD001"


@respx.mock
def test_get_order_status():
    respx.post(f"{BASE}/api/order-status").mock(
        return_value=httpx.Response(
            200, json={"order_id": "PALMPESAORD001", "payment_status": "COMPLETED"}
        )
    )
    with PalmPesa(api_token="test-token") as pp:
        result = pp.payments.get_order_status("PALMPESAORD001")
    assert result["payment_status"] == "COMPLETED"


@respx.mock
def test_list_transactions():
    respx.get(f"{BASE}/api/transactions").mock(
        return_value=httpx.Response(200, json={"data": [], "total": 0})
    )
    with PalmPesa(api_token="test-token") as pp:
        result = pp.transactions.list_all(page=1, per_page=20)
    assert "data" in result


def test_initiate_invalid_phone():
    with PalmPesa(api_token="test-token") as pp:
        with pytest.raises(ValidationError):
            pp.payments.initiate_mobile_payment(
                amount=1000,
                phone="INVALID",
                transaction_id="TXN002",
                name="Jane",
                email="jane@example.com",
                callback_url="https://example.com/webhook",
            )


@respx.mock
def test_auth_error_raises():
    respx.post(f"{BASE}/api/palmpesa/initiate").mock(
        return_value=httpx.Response(401, json={"message": "Unauthenticated"})
    )
    with PalmPesa(api_token="bad-token") as pp:
        with pytest.raises(AuthenticationError):
            pp.payments.initiate_mobile_payment(
                amount=1000,
                phone="0693662424",
                transaction_id="TXN003",
                name="Jane",
                email="jane@example.com",
                callback_url="https://example.com/webhook",
            )


@respx.mock
def test_server_error_raises():
    respx.post(f"{BASE}/api/palmpesa/initiate").mock(
        return_value=httpx.Response(500, json={"message": "Internal Server Error"})
    )
    with PalmPesa(api_token="test-token", max_retries=1) as pp:
        with pytest.raises(ServerError):
            pp.payments.initiate_mobile_payment(
                amount=1000,
                phone="0693662424",
                transaction_id="TXN004",
                name="Jane",
                email="jane@example.com",
                callback_url="https://example.com/webhook",
            )


@respx.mock
def test_is_healthy_true():
    respx.get(f"{BASE}/api/transactions").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    with PalmPesa(api_token="test-token") as pp:
        assert pp.is_healthy() is True


@respx.mock
def test_is_healthy_false_on_auth_error():
    respx.get(f"{BASE}/api/transactions").mock(
        return_value=httpx.Response(401, json={"message": "Unauthenticated"})
    )
    with PalmPesa(api_token="bad-token") as pp:
        assert pp.is_healthy() is False


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_async_initiate_mobile_payment():
    respx.post(f"{BASE}/api/palmpesa/initiate").mock(
        return_value=httpx.Response(
            200, json={"order_id": "PALMPESAORD002", "message": "Payment initiated"}
        )
    )
    async with AsyncPalmPesa(api_token="test-token") as pp:
        result = await pp.payments.initiate_mobile_payment(
            amount=3000,
            phone="+255712345678",
            transaction_id="TXNASYNC001",
            name="Alice",
            email="alice@example.com",
            callback_url="https://example.com/webhook",
        )
    assert result["order_id"] == "PALMPESAORD002"


@pytest.mark.asyncio
@respx.mock
async def test_async_list_transactions():
    respx.get(f"{BASE}/api/transactions").mock(
        return_value=httpx.Response(200, json={"data": [{"id": 1}], "total": 1})
    )
    async with AsyncPalmPesa(api_token="test-token") as pp:
        result = await pp.transactions.list_all()
    assert result["total"] == 1


@pytest.mark.asyncio
@respx.mock
async def test_async_is_healthy():
    respx.get(f"{BASE}/api/transactions").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    async with AsyncPalmPesa(api_token="test-token") as pp:
        assert await pp.is_healthy() is True
