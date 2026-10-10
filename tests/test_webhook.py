"""Tests for callback verification and parsing."""

from __future__ import annotations

import json

import pytest

from palmpesa import (
    CallbackEventType,
    PaymentStatus,
    WebhookVerificationError,
    WebhookVerifier,
    compute_signature,
    parse_callback,
)

SECRET = "whsec_test_secret"
NOW = 1_791_456_091

COMPLETED = {
    "event": "payment.completed",
    "event_id": "82c12c18a92fc6f3bfb61f89bbf0b8f10f7790a3cfe7b0940734eb43eca87eb1",
    "transaction_id": "ORDER-2026-000123",
    "order_id": "PALMPESAV2A20261008120000123EFGH5678",
    "selcom_reference": "0289999288",
    "status": "COMPLETED",
    "amount": 10000,
    "currency": "TZS",
    "channel": "TIGOPESATZ",
    "phone": "255712345678",
    "processed_at": "2026-10-08T12:01:31+03:00",
}


def _body(payload: dict[str, object] | None = None) -> bytes:
    return json.dumps(payload or COMPLETED, separators=(",", ":")).encode()


def _signed_headers(body: bytes, ts: int = NOW, secret: str = SECRET) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-PalmPesa-Event-Id": COMPLETED["event_id"],  # type: ignore[dict-item]
        "X-PalmPesa-Timestamp": str(ts),
        "X-PalmPesa-Signature": compute_signature(secret, ts, body),
    }


class TestComputeSignature:
    def test_matches_documented_scheme(self) -> None:
        import hashlib
        import hmac

        body = b'{"a":1}'
        expected = "sha256=" + hmac.new(SECRET.encode(), b'123.{"a":1}', hashlib.sha256).hexdigest()
        assert compute_signature(SECRET, "123", body) == expected
        assert compute_signature(SECRET, 123, body.decode()) == expected


class TestSignedVerification:
    def test_valid_signature(self) -> None:
        body = _body()
        event = WebhookVerifier(SECRET).verify(body, _signed_headers(body), now=NOW)
        assert event.event is CallbackEventType.PAYMENT_COMPLETED
        assert event.status is PaymentStatus.COMPLETED and event.is_paid
        assert event.amount == 10000
        assert event.selcom_reference == "0289999288"
        assert event.processed_at is not None and event.processed_at.utcoffset() is not None

    def test_headers_case_insensitive(self) -> None:
        body = _body()
        headers = {k.lower(): v for k, v in _signed_headers(body).items()}
        WebhookVerifier(SECRET).verify(body, headers, now=NOW)

    def test_uppercase_hex_accepted(self) -> None:
        body = _body()
        headers = _signed_headers(body)
        headers["X-PalmPesa-Signature"] = "sha256=" + headers["X-PalmPesa-Signature"][7:].upper()
        WebhookVerifier(SECRET).verify(body, headers, now=NOW)

    def test_tampered_body_rejected(self) -> None:
        body = _body()
        headers = _signed_headers(body)
        tampered = _body({**COMPLETED, "amount": 1})
        with pytest.raises(WebhookVerificationError, match="signature"):
            WebhookVerifier(SECRET).verify(tampered, headers, now=NOW)

    def test_wrong_secret_rejected(self) -> None:
        body = _body()
        with pytest.raises(WebhookVerificationError):
            WebhookVerifier(SECRET).verify(body, _signed_headers(body, secret="other"), now=NOW)

    def test_stale_timestamp_rejected(self) -> None:
        body = _body()
        headers = _signed_headers(body, ts=NOW - 301)
        with pytest.raises(WebhookVerificationError, match="tolerance"):
            WebhookVerifier(SECRET).verify(body, headers, now=NOW)

    def test_future_timestamp_rejected(self) -> None:
        body = _body()
        with pytest.raises(WebhookVerificationError):
            WebhookVerifier(SECRET).verify(body, _signed_headers(body, ts=NOW + 301), now=NOW)

    def test_within_tolerance_accepted(self) -> None:
        body = _body()
        WebhookVerifier(SECRET).verify(body, _signed_headers(body, ts=NOW - 300), now=NOW)

    def test_missing_headers_rejected(self) -> None:
        with pytest.raises(WebhookVerificationError, match="Missing"):
            WebhookVerifier(SECRET).verify(_body(), {}, now=NOW)

    def test_non_numeric_timestamp_rejected(self) -> None:
        body = _body()
        headers = _signed_headers(body)
        headers["X-PalmPesa-Timestamp"] = "abc"
        with pytest.raises(WebhookVerificationError, match="Timestamp"):
            WebhookVerifier(SECRET).verify(body, headers, now=NOW)

    def test_event_id_header_mismatch_rejected(self) -> None:
        body = _body()
        headers = _signed_headers(body)
        headers["X-PalmPesa-Event-Id"] = "different"
        with pytest.raises(WebhookVerificationError, match="Event-Id"):
            WebhookVerifier(SECRET).verify(body, headers, now=NOW)

    def test_str_body_accepted(self) -> None:
        body = _body()
        WebhookVerifier(SECRET).verify(body.decode(), _signed_headers(body), now=NOW)


class TestUnsigned:
    def test_verifier_without_secret_parses(self) -> None:
        verifier = WebhookVerifier()
        assert verifier.signing_enabled is False
        event = verifier.verify(_body(), {"X-PalmPesa-Event-Id": COMPLETED["event_id"]})  # type: ignore[dict-item]
        assert event.order_id == COMPLETED["order_id"]

    @pytest.mark.parametrize(
        ("event_name", "status", "event_type"),
        [
            ("payment.cancelled", "CANCELLED", CallbackEventType.PAYMENT_CANCELLED),
            ("payment.rejected", "REJECTED", CallbackEventType.PAYMENT_REJECTED),
            (
                "payment.initiation_failed",
                "INITIATION_FAILED",
                CallbackEventType.PAYMENT_INITIATION_FAILED,
            ),
            ("payment.expired", "EXPIRED", CallbackEventType.PAYMENT_EXPIRED),
        ],
    )
    def test_non_paid_events(
        self, event_name: str, status: str, event_type: CallbackEventType
    ) -> None:
        event = parse_callback({**COMPLETED, "event": event_name, "status": status})
        assert event.event is event_type
        assert event.is_final and not event.is_paid

    def test_unknown_event_and_status_are_safe(self) -> None:
        event = parse_callback({**COMPLETED, "event": "payment.refunded", "status": "REFUNDED"})
        assert event.event is CallbackEventType.UNKNOWN
        assert event.status is PaymentStatus.UNKNOWN
        assert not event.is_paid and not event.is_final
        assert event.raw["status"] == "REFUNDED"

    def test_invalid_json(self) -> None:
        with pytest.raises(WebhookVerificationError, match="JSON"):
            parse_callback(b"not json")

    def test_non_object(self) -> None:
        with pytest.raises(WebhookVerificationError, match="object"):
            parse_callback(b"[1,2]")

    def test_missing_fields(self) -> None:
        with pytest.raises(WebhookVerificationError, match="event_id"):
            parse_callback({k: v for k, v in COMPLETED.items() if k != "event_id"})


class TestConfig:
    def test_empty_secret_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebhookVerifier("")

    def test_bad_tolerance_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebhookVerifier(SECRET, tolerance_seconds=0)
