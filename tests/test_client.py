"""Tests for the sync and async PalmPesa v2 clients."""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest
import respx

from palmpesa import (
    AccountFrozenError,
    AsyncPalmPesa,
    AuthenticationError,
    ConflictError,
    FailureReason,
    ForbiddenError,
    NetworkError,
    NotFoundError,
    PalmPesa,
    PalmPesaClient,
    PalmPesaError,
    PaymentStatus,
    RateLimitError,
    RequestTimeoutError,
    ServerError,
    ValidationError,
    __version__,
)

from .conftest import (
    BASE,
    ORDER_ID,
    PAYMENT_KWARGS,
    PAYMENTS_URL,
    accepted_body,
    status_body,
)

# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_requires_token(self) -> None:
        with pytest.raises(ValueError):
            PalmPesa(api_token="")
        with pytest.raises(ValueError):
            PalmPesa(api_token="   ")

    def test_rejects_plain_http(self) -> None:
        with pytest.raises(ValueError):
            PalmPesa(api_token="t", base_url="http://palmpesa.co.tz")

    def test_allows_http_localhost(self) -> None:
        with PalmPesa(api_token="t", base_url="http://localhost:8000/") as pp:
            assert pp.base_url == "http://localhost:8000"

    def test_rejects_negative_retries(self) -> None:
        with pytest.raises(ValueError):
            PalmPesa(api_token="t", max_retries=-1)

    def test_repr_hides_token(self) -> None:
        with PalmPesa(api_token="super-secret-token") as pp:
            assert "super-secret-token" not in repr(pp)

    def test_legacy_alias(self) -> None:
        assert PalmPesaClient is PalmPesa

    def test_external_http_client_not_closed(self) -> None:
        http = httpx.Client()
        with PalmPesa(api_token="t", http_client=http):
            pass
        assert not http.is_closed
        http.close()


# ---------------------------------------------------------------------------
# request_payment
# ---------------------------------------------------------------------------


@respx.mock
def test_request_payment_success_and_payload() -> None:
    route = respx.post(PAYMENTS_URL).mock(return_value=httpx.Response(202, json=accepted_body()))
    with PalmPesa(api_token="test-token") as pp:
        payment = pp.payments.request_payment(**PAYMENT_KWARGS, buyer_remarks="Order 123")

    assert payment.order_id == ORDER_ID
    assert payment.status is PaymentStatus.INITIATING
    assert payment.message == "Payment accepted."
    assert payment.amount == 10000
    assert not payment.is_final and not payment.is_paid

    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer test-token"
    assert request.headers["Accept"] == "application/json"
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["User-Agent"].startswith(f"palmpesa-python-sdk/{__version__}")
    assert json.loads(request.content) == {
        "transaction_id": "ORDER-2026-000123",
        "amount": 10000,
        "currency": "TZS",
        "phone": "255712345678",
        "name": "Juma Hassan",
        "email": "juma@example.com",
        "callback_url": "https://shop.example.com/palmpesa/callback",
        "buyer_remarks": "Order 123",
    }


@respx.mock
def test_request_payment_accepts_integral_decimal() -> None:
    route = respx.post(PAYMENTS_URL).mock(return_value=httpx.Response(202, json=accepted_body()))
    with PalmPesa(api_token="t") as pp:
        pp.payments.request_payment(**{**PAYMENT_KWARGS, "amount": Decimal("10000.00")})
    assert json.loads(route.calls.last.request.content)["amount"] == 10000


@respx.mock
def test_local_validation_never_sends() -> None:
    route = respx.post(PAYMENTS_URL)
    with PalmPesa(api_token="t") as pp:
        with pytest.raises(ValidationError) as exc_info:
            pp.payments.request_payment(**{**PAYMENT_KWARGS, "amount": 50})
    assert exc_info.value.status_code is None
    assert "amount" in exc_info.value.errors
    assert not route.called


@respx.mock
def test_user_agent_suffix() -> None:
    route = respx.post(PAYMENTS_URL).mock(return_value=httpx.Response(202, json=accepted_body()))
    with PalmPesa(api_token="t", user_agent="nanobill/1.0") as pp:
        pp.payments.request_payment(**PAYMENT_KWARGS)
    assert route.calls.last.request.headers["User-Agent"].endswith(" nanobill/1.0")


# ---------------------------------------------------------------------------
# get_payment / wait_for_final_status
# ---------------------------------------------------------------------------


@respx.mock
def test_get_payment_completed() -> None:
    respx.get(f"{PAYMENTS_URL}/{ORDER_ID}").mock(
        return_value=httpx.Response(
            200,
            json=status_body(status="COMPLETED", reference="0289999288", channel="TIGOPESATZ"),
        )
    )
    with PalmPesa(api_token="t") as pp:
        payment = pp.payments.get_payment(ORDER_ID)
    assert payment.is_paid and payment.is_final
    assert payment.reference == "0289999288"
    assert payment.channel == "TIGOPESATZ"
    assert payment.updated_at is not None


@respx.mock
def test_get_payment_initiation_failed_reason() -> None:
    respx.get(f"{PAYMENTS_URL}/{ORDER_ID}").mock(
        return_value=httpx.Response(
            200, json=status_body(status="INITIATION_FAILED", failure_reason="PROVIDER_UNAVAILABLE")
        )
    )
    with PalmPesa(api_token="t") as pp:
        payment = pp.payments.get_payment(ORDER_ID)
    assert payment.status is PaymentStatus.INITIATION_FAILED
    assert payment.failure_reason is FailureReason.PROVIDER_UNAVAILABLE
    assert payment.is_final and not payment.is_paid


@respx.mock
def test_get_payment_url_encodes_order_id() -> None:
    route = respx.get(f"{PAYMENTS_URL}/a%2Fb").mock(
        return_value=httpx.Response(200, json=status_body(order_id="a/b"))
    )
    with PalmPesa(api_token="t") as pp:
        pp.payments.get_payment("a/b")
    assert route.called


def test_get_payment_requires_order_id() -> None:
    with PalmPesa(api_token="t") as pp:
        with pytest.raises(ValidationError):
            pp.payments.get_payment("  ")


@respx.mock
def test_get_payment_not_found() -> None:
    respx.get(f"{PAYMENTS_URL}/{ORDER_ID}").mock(
        return_value=httpx.Response(
            404, json={"message": "Payment not found.", "order_id": ORDER_ID}
        )
    )
    with PalmPesa(api_token="t") as pp:
        with pytest.raises(NotFoundError) as exc_info:
            pp.payments.get_payment(ORDER_ID)
    assert exc_info.value.message == "Payment not found."
    assert exc_info.value.status_code == 404


@respx.mock
def test_wait_for_final_status_polls_until_final() -> None:
    route = respx.get(f"{PAYMENTS_URL}/{ORDER_ID}").mock(
        side_effect=[
            httpx.Response(200, json=status_body(status="PENDING")),
            httpx.Response(200, json=status_body(status="AMBIGUOUS")),
            httpx.Response(200, json=status_body(status="CANCELLED")),
        ]
    )
    with PalmPesa(api_token="t") as pp:
        payment = pp.payments.wait_for_final_status(ORDER_ID, timeout=60, poll_interval=1)
    assert payment.status is PaymentStatus.CANCELLED
    assert route.call_count == 3


@respx.mock
def test_wait_for_final_status_timeout_returns_last() -> None:
    respx.get(f"{PAYMENTS_URL}/{ORDER_ID}").mock(
        return_value=httpx.Response(200, json=status_body(status="PENDING"))
    )
    with PalmPesa(api_token="t") as pp:
        payment = pp.payments.wait_for_final_status(ORDER_ID, timeout=0, poll_interval=1)
    assert payment.status is PaymentStatus.PENDING and not payment.is_final


def test_wait_for_final_status_rejects_aggressive_polling() -> None:
    with PalmPesa(api_token="t") as pp:
        with pytest.raises(ValueError):
            pp.payments.wait_for_final_status(ORDER_ID, poll_interval=0.1)


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "body", "exc_type"),
    [
        (401, {"error": "Unauthorized"}, AuthenticationError),
        (401, {"error": "Invalid Token"}, AuthenticationError),
        (403, {"error": "Account verification pending..."}, ForbiddenError),
        (
            403,
            {"success": False, "code": "ACCOUNT_FROZEN", "message": "Frozen"},
            AccountFrozenError,
        ),
        (
            409,
            {"message": "This transaction_id was already used with different payment details."},
            ConflictError,
        ),
        (400, {"message": "Bad request"}, ValidationError),
        (418, {"message": "teapot"}, PalmPesaError),
    ],
)
@respx.mock
def test_error_mapping(status: int, body: dict[str, object], exc_type: type[Exception]) -> None:
    respx.post(PAYMENTS_URL).mock(return_value=httpx.Response(status, json=body))
    with PalmPesa(api_token="t", max_retries=0) as pp:
        with pytest.raises(exc_type) as exc_info:
            pp.payments.request_payment(**PAYMENT_KWARGS)
    assert exc_info.value.status_code == status  # type: ignore[attr-defined]


@respx.mock
def test_auth_error_message_from_error_key() -> None:
    respx.post(PAYMENTS_URL).mock(return_value=httpx.Response(401, json={"error": "Invalid Token"}))
    with PalmPesa(api_token="t") as pp:
        with pytest.raises(AuthenticationError, match="Invalid Token"):
            pp.payments.request_payment(**PAYMENT_KWARGS)


@respx.mock
def test_422_exposes_field_errors() -> None:
    msg = "The callback URL must be a publicly reachable HTTPS URL."
    respx.post(PAYMENTS_URL).mock(
        return_value=httpx.Response(422, json={"message": msg, "errors": {"callback_url": [msg]}})
    )
    with PalmPesa(api_token="t") as pp:
        with pytest.raises(ValidationError) as exc_info:
            pp.payments.request_payment(**PAYMENT_KWARGS)
    assert exc_info.value.errors == {"callback_url": [msg]}
    assert exc_info.value.status_code == 422


@respx.mock
def test_non_json_error_body() -> None:
    respx.post(PAYMENTS_URL).mock(return_value=httpx.Response(502, text="<html>Bad Gateway</html>"))
    with PalmPesa(api_token="t", max_retries=0) as pp:
        with pytest.raises(ServerError) as exc_info:
            pp.payments.request_payment(**PAYMENT_KWARGS)
    assert "502" in exc_info.value.message


@respx.mock
def test_non_json_success_body_raises() -> None:
    respx.post(PAYMENTS_URL).mock(return_value=httpx.Response(200, text="<html>ok</html>"))
    with PalmPesa(api_token="t") as pp:
        with pytest.raises(PalmPesaError, match="non-JSON"):
            pp.payments.request_payment(**PAYMENT_KWARGS)


@respx.mock
def test_success_without_data_raises() -> None:
    respx.post(PAYMENTS_URL).mock(return_value=httpx.Response(202, json={"success": True}))
    with PalmPesa(api_token="t") as pp:
        with pytest.raises(PalmPesaError, match="missing payment data"):
            pp.payments.request_payment(**PAYMENT_KWARGS)


@respx.mock
def test_redirects_are_not_followed() -> None:
    respx.post(PAYMENTS_URL).mock(
        return_value=httpx.Response(302, headers={"Location": "https://evil.example/"})
    )
    with PalmPesa(api_token="t") as pp:
        with pytest.raises(PalmPesaError) as exc_info:
            pp.payments.request_payment(**PAYMENT_KWARGS)
    assert exc_info.value.status_code == 302


# ---------------------------------------------------------------------------
# Retries
# ---------------------------------------------------------------------------


@respx.mock
def test_retries_5xx_then_succeeds_with_identical_body() -> None:
    route = respx.post(PAYMENTS_URL).mock(
        side_effect=[
            httpx.Response(500, json={"message": "Server Error"}),
            httpx.Response(503, json={"message": "Unavailable"}),
            httpx.Response(202, json=accepted_body()),
        ]
    )
    with PalmPesa(api_token="t", max_retries=2) as pp:
        payment = pp.payments.request_payment(**PAYMENT_KWARGS)
    assert payment.order_id == ORDER_ID
    assert route.call_count == 3
    bodies = {call.request.content for call in route.calls}
    assert len(bodies) == 1  # same transaction_id + details → idempotent


@respx.mock
def test_gives_up_after_max_retries() -> None:
    route = respx.post(PAYMENTS_URL).mock(return_value=httpx.Response(500, json={}))
    with PalmPesa(api_token="t", max_retries=2) as pp:
        with pytest.raises(ServerError):
            pp.payments.request_payment(**PAYMENT_KWARGS)
    assert route.call_count == 3


@respx.mock
def test_rate_limit_retry_after() -> None:
    route = respx.get(f"{PAYMENTS_URL}/{ORDER_ID}").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "7"}, json={"message": "Slow"})
    )
    with PalmPesa(api_token="t", max_retries=1) as pp:
        with pytest.raises(RateLimitError) as exc_info:
            pp.payments.get_payment(ORDER_ID)
    assert exc_info.value.retry_after == 7.0
    assert route.call_count == 2


@respx.mock
def test_does_not_retry_4xx() -> None:
    route = respx.post(PAYMENTS_URL).mock(return_value=httpx.Response(409, json={"message": "x"}))
    with PalmPesa(api_token="t", max_retries=3) as pp:
        with pytest.raises(ConflictError):
            pp.payments.request_payment(**PAYMENT_KWARGS)
    assert route.call_count == 1


@respx.mock
def test_network_error_retried_then_raised() -> None:
    route = respx.post(PAYMENTS_URL).mock(side_effect=httpx.ConnectError("dns failure"))
    with PalmPesa(api_token="t", max_retries=1) as pp:
        with pytest.raises(NetworkError):
            pp.payments.request_payment(**PAYMENT_KWARGS)
    assert route.call_count == 2


@respx.mock
def test_timeout_then_success() -> None:
    route = respx.post(PAYMENTS_URL).mock(
        side_effect=[httpx.ReadTimeout("slow"), httpx.Response(202, json=accepted_body())]
    )
    with PalmPesa(api_token="t", max_retries=1) as pp:
        assert pp.payments.request_payment(**PAYMENT_KWARGS).order_id == ORDER_ID
    assert route.call_count == 2


@respx.mock
def test_timeout_exhausted_raises_timeout_error() -> None:
    respx.post(PAYMENTS_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with PalmPesa(api_token="t", max_retries=0) as pp:
        with pytest.raises(RequestTimeoutError):
            pp.payments.request_payment(**PAYMENT_KWARGS)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

HEALTH_ROUTE = f"{PAYMENTS_URL}/PALMPESAV2A00000000000000000SDKHEALTH"


@respx.mock
def test_is_healthy_true_on_404() -> None:
    respx.get(HEALTH_ROUTE).mock(
        return_value=httpx.Response(404, json={"message": "Payment not found."})
    )
    with PalmPesa(api_token="t") as pp:
        assert pp.is_healthy() is True


@respx.mock
def test_is_healthy_false_on_401() -> None:
    respx.get(HEALTH_ROUTE).mock(return_value=httpx.Response(401, json={"error": "Invalid Token"}))
    with PalmPesa(api_token="bad") as pp:
        assert pp.is_healthy() is False
        with pytest.raises(AuthenticationError):
            pp.verify_credentials()


@respx.mock
def test_is_healthy_false_on_network_error() -> None:
    respx.get(HEALTH_ROUTE).mock(side_effect=httpx.ConnectError("down"))
    with PalmPesa(api_token="t", max_retries=0) as pp:
        assert pp.is_healthy() is False


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------


@respx.mock
async def test_async_request_payment() -> None:
    route = respx.post(PAYMENTS_URL).mock(return_value=httpx.Response(202, json=accepted_body()))
    async with AsyncPalmPesa(api_token="t") as pp:
        payment = await pp.payments.request_payment(
            **{**PAYMENT_KWARGS, "phone": "+255 712 345 678"}
        )
    assert payment.order_id == ORDER_ID
    assert json.loads(route.calls.last.request.content)["phone"] == "255712345678"


@respx.mock
async def test_async_retries_then_succeeds() -> None:
    route = respx.post(PAYMENTS_URL).mock(
        side_effect=[httpx.ConnectError("x"), httpx.Response(202, json=accepted_body())]
    )
    async with AsyncPalmPesa(api_token="t", max_retries=1) as pp:
        await pp.payments.request_payment(**PAYMENT_KWARGS)
    assert route.call_count == 2


@respx.mock
async def test_async_get_payment_and_errors() -> None:
    respx.get(f"{PAYMENTS_URL}/{ORDER_ID}").mock(
        return_value=httpx.Response(200, json=status_body(status="EXPIRED"))
    )
    respx.get(f"{PAYMENTS_URL}/MISSING").mock(
        return_value=httpx.Response(404, json={"message": "Payment not found."})
    )
    async with AsyncPalmPesa(api_token="t") as pp:
        payment = await pp.payments.get_payment(ORDER_ID)
        assert payment.status is PaymentStatus.EXPIRED and payment.is_final
        with pytest.raises(NotFoundError):
            await pp.payments.get_payment("MISSING")


@respx.mock
async def test_async_wait_for_final_status() -> None:
    respx.get(f"{PAYMENTS_URL}/{ORDER_ID}").mock(
        side_effect=[
            httpx.Response(200, json=status_body(status="PENDING")),
            httpx.Response(200, json=status_body(status="COMPLETED")),
        ]
    )
    async with AsyncPalmPesa(api_token="t") as pp:
        payment = await pp.payments.wait_for_final_status(ORDER_ID, timeout=60, poll_interval=1)
    assert payment.is_paid


@respx.mock
async def test_async_is_healthy() -> None:
    respx.get(HEALTH_ROUTE).mock(return_value=httpx.Response(404, json={}))
    async with AsyncPalmPesa(api_token="t") as pp:
        assert await pp.is_healthy() is True


def test_base_constant() -> None:
    assert BASE == "https://palmpesa.co.tz"


@respx.mock
async def test_async_timeout_and_5xx_exhaustion() -> None:
    respx.post(PAYMENTS_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    respx.get(f"{PAYMENTS_URL}/{ORDER_ID}").mock(return_value=httpx.Response(503, json={}))
    async with AsyncPalmPesa(api_token="t", max_retries=1) as pp:
        with pytest.raises(RequestTimeoutError):
            await pp.payments.request_payment(**PAYMENT_KWARGS)
        with pytest.raises(ServerError):
            await pp.payments.get_payment(ORDER_ID)


@respx.mock
async def test_async_verify_credentials_raises_on_403() -> None:
    respx.get(HEALTH_ROUTE).mock(
        return_value=httpx.Response(403, json={"error": "Account verification pending..."})
    )
    async with AsyncPalmPesa(api_token="t") as pp:
        assert await pp.is_healthy() is False
        with pytest.raises(ForbiddenError):
            await pp.verify_credentials()
