"""Tests for WebhookValidator and WebhookEvent."""

from __future__ import annotations

from palmpesa import (
    WebhookValidator,
    WebhookEvent,
    PAYMENT_STATUS_COMPLETED,
    PAYMENT_STATUS_PENDING,
    PAYMENT_STATUS_FAILED,
)


class TestWebhookEvent:
    def _make(self, status: str) -> WebhookEvent:
        return WebhookEvent({"order_id": "PALMPESAORD001", "payment_status": status})

    def test_is_completed(self):
        assert self._make(PAYMENT_STATUS_COMPLETED).is_completed is True

    def test_is_failed(self):
        assert self._make(PAYMENT_STATUS_FAILED).is_failed is True

    def test_is_pending(self):
        assert self._make(PAYMENT_STATUS_PENDING).is_pending is True

    def test_order_id_parsed(self):
        event = self._make(PAYMENT_STATUS_COMPLETED)
        assert event.order_id == "PALMPESAORD001"

    def test_raw_preserved(self):
        payload = {"order_id": "X", "payment_status": "COMPLETED", "extra": "data"}
        event = WebhookEvent(payload)
        assert event.raw == payload

    def test_repr(self):
        event = self._make(PAYMENT_STATUS_COMPLETED)
        assert "PALMPESAORD001" in repr(event)
        assert "COMPLETED" in repr(event)


class TestWebhookValidator:
    def test_parse_returns_event(self):
        payload = {"order_id": "ORD001", "payment_status": "COMPLETED"}
        event = WebhookValidator.parse(payload)
        assert isinstance(event, WebhookEvent)
        assert event.order_id == "ORD001"

    def test_is_valid_payload_complete(self):
        assert WebhookValidator.is_valid_payload(
            {"order_id": "ORD001", "payment_status": "COMPLETED"}
        ) is True

    def test_is_valid_payload_pending(self):
        assert WebhookValidator.is_valid_payload(
            {"order_id": "ORD001", "payment_status": "PENDING"}
        ) is True

    def test_is_valid_payload_failed(self):
        assert WebhookValidator.is_valid_payload(
            {"order_id": "ORD001", "payment_status": "FAILED"}
        ) is True

    def test_is_valid_payload_missing_order_id(self):
        assert WebhookValidator.is_valid_payload({"payment_status": "COMPLETED"}) is False

    def test_is_valid_payload_unknown_status(self):
        assert WebhookValidator.is_valid_payload(
            {"order_id": "ORD001", "payment_status": "UNKNOWN"}
        ) is False

    def test_is_valid_payload_empty(self):
        assert WebhookValidator.is_valid_payload({}) is False
