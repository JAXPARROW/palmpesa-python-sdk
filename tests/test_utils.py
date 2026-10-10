"""Tests for phone normalisation, ID generation, payload validation and models."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import pytest

from palmpesa import (
    Payment,
    PaymentStatus,
    ValidationError,
    generate_transaction_id,
    normalize_phone,
)
from palmpesa._base import parse_retry_after, retry_delay
from palmpesa.utils import build_payment_payload, validate_callback_url, validate_transaction_id

from .conftest import PAYMENT_KWARGS, payment_data

# ---------------------------------------------------------------------------
# normalize_phone
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0712345678", "255712345678"),
        ("712345678", "255712345678"),
        ("255712345678", "255712345678"),
        ("+255712345678", "255712345678"),
        ("+255 712 345 678", "255712345678"),
        ("0612-345-678", "255612345678"),
    ],
)
def test_normalize_phone(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "123", "0812345678", "254712345678", "25571234567", "abc"])
def test_normalize_phone_invalid(raw: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        normalize_phone(raw)
    assert "phone" in exc_info.value.errors


# ---------------------------------------------------------------------------
# generate_transaction_id
# ---------------------------------------------------------------------------


def test_generate_transaction_id_valid_and_unique() -> None:
    ids = {generate_transaction_id("ORDER") for _ in range(200)}
    assert len(ids) == 200
    for tid in ids:
        assert tid.startswith("ORDER-")
        assert validate_transaction_id(tid) == tid


def test_generate_transaction_id_empty_prefix() -> None:
    assert validate_transaction_id(generate_transaction_id(""))


def test_generate_transaction_id_bad_prefix() -> None:
    with pytest.raises(ValueError):
        generate_transaction_id("bad prefix!")


# ---------------------------------------------------------------------------
# build_payment_payload
# ---------------------------------------------------------------------------


def _build(**overrides: Any) -> dict[str, Any]:
    return build_payment_payload(**{**PAYMENT_KWARGS, **overrides})


def test_payload_omits_unset_remarks() -> None:
    payload = _build()
    assert "buyer_remarks" not in payload and "merchant_remarks" not in payload


def test_payload_strips_whitespace() -> None:
    payload = _build(name="  Juma  ", email=" juma@example.com ")
    assert payload["name"] == "Juma" and payload["email"] == "juma@example.com"


@pytest.mark.parametrize("amount", [100, 100_000_000, Decimal("500")])
def test_amount_bounds_ok(amount: Any) -> None:
    assert _build(amount=amount)["amount"] == int(amount)


@pytest.mark.parametrize("amount", [99, 100_000_001, 0, -5, 1000.0, "1000", True, Decimal("100.5")])
def test_amount_invalid(amount: Any) -> None:
    with pytest.raises(ValidationError) as exc_info:
        _build(amount=amount)
    assert "amount" in exc_info.value.errors


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("transaction_id", ""),
        ("transaction_id", "has space"),
        ("transaction_id", "x" * 192),
        ("transaction_id", "bad/slash"),
        ("currency", "USD"),
        ("name", "   "),
        ("name", "x" * 256),
        ("email", ""),
        ("email", "not-an-email"),
        ("buyer_remarks", "x" * 256),
        ("merchant_remarks", "x" * 256),
    ],
)
def test_field_invalid(field: str, value: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        _build(**{field: value})
    assert field in exc_info.value.errors


def test_transaction_id_max_length_ok() -> None:
    assert _build(transaction_id="A" * 191)["transaction_id"] == "A" * 191


@pytest.mark.parametrize(
    "url",
    [
        "http://shop.example.com/cb",
        "https://localhost/cb",
        "https://api.localhost/cb",
        "https://127.0.0.1/cb",
        "https://10.0.0.5/cb",
        "https://192.168.1.10/cb",
        "https://[::1]/cb",
        "/relative/cb",
        "https://example.com/" + "x" * 2048,
        "",
    ],
)
def test_callback_url_invalid(url: str) -> None:
    with pytest.raises(ValidationError):
        validate_callback_url(url)


@pytest.mark.parametrize(
    "url", ["https://shop.example.com/palmpesa/callback?x=1", "https://41.59.1.10/cb"]
)
def test_callback_url_valid(url: str) -> None:
    assert validate_callback_url(url) == url


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def test_payment_from_api_tolerates_string_amount_and_unknown_status() -> None:
    payment = Payment.from_api(payment_data(amount="2500.00", status="something_new"))
    assert payment.amount == 2500
    assert payment.status is PaymentStatus.UNKNOWN
    assert payment.raw["status"] == "something_new"


def test_status_case_insensitive() -> None:
    assert PaymentStatus("completed") is PaymentStatus.COMPLETED


@pytest.mark.parametrize(
    ("status", "final"),
    [
        ("INITIATING", False),
        ("PENDING", False),
        ("AMBIGUOUS", False),
        ("COMPLETED", True),
        ("CANCELLED", True),
        ("REJECTED", True),
        ("INITIATION_FAILED", True),
        ("EXPIRED", True),
    ],
)
def test_status_finality(status: str, final: bool) -> None:
    assert PaymentStatus(status).is_final is final
    assert PaymentStatus(status).is_paid is (status == "COMPLETED")


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


def test_retry_delay_backoff_bounds() -> None:
    for attempt in range(6):
        delay = retry_delay(attempt)
        ceiling = min(8.0, 0.5 * 2**attempt)
        assert ceiling / 2 <= delay <= ceiling


def test_retry_delay_honours_retry_after_with_cap() -> None:
    assert retry_delay(0, httpx.Response(429, headers={"Retry-After": "3"})) == 3.0
    assert retry_delay(0, httpx.Response(429, headers={"Retry-After": "3600"})) == 60.0


def test_parse_retry_after_http_date_in_past() -> None:
    response = httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"})
    assert parse_retry_after(response) == 0.0


def test_parse_retry_after_garbage() -> None:
    assert parse_retry_after(httpx.Response(429, headers={"Retry-After": "soon"})) is None
