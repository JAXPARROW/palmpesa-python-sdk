"""
Callback (webhook) verification for PalmPesa API v2.

PalmPesa POSTs to your ``callback_url`` when a payment reaches a final
status. If PalmPesa issued you a signing secret, each callback carries::

    X-PalmPesa-Event-Id:  <same as event_id in the body>
    X-PalmPesa-Timestamp: <unix seconds>
    X-PalmPesa-Signature: sha256=<hex HMAC-SHA256(timestamp + "." + raw_body, secret)>

Flask example::

    verifier = WebhookVerifier(signing_secret=os.environ["PALMPESA_SIGNING_SECRET"])

    @app.post("/palmpesa/callback")
    def palmpesa_callback():
        try:
            event = verifier.verify(request.get_data(), request.headers)
        except WebhookVerificationError:
            return "", 401
        if already_processed(event.event_id):
            return {"received": True}, 200
        if event.is_paid:
            fulfil(event)          # after matching order_id / amount / currency
        return {"received": True}, 200

Always pass the **raw** request bytes — re-serialised JSON will not match
the signature. Respond 2xx within 10 seconds; PalmPesa retries up to 5 times.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from typing import Any

from .exceptions import WebhookVerificationError
from .models import CallbackEvent

EVENT_ID_HEADER = "X-PalmPesa-Event-Id"
TIMESTAMP_HEADER = "X-PalmPesa-Timestamp"
SIGNATURE_HEADER = "X-PalmPesa-Signature"
DEFAULT_TOLERANCE_SECONDS = 300

_SIGNATURE_PREFIX = "sha256="
_REQUIRED_FIELDS = ("event", "event_id", "transaction_id", "order_id", "status")


def compute_signature(signing_secret: str, timestamp: str | int, body: bytes | str) -> str:
    """Return the expected ``X-PalmPesa-Signature`` value for a callback."""
    raw = body.encode() if isinstance(body, str) else body
    signed = str(timestamp).encode() + b"." + raw
    digest = hmac.new(signing_secret.encode(), signed, hashlib.sha256).hexdigest()
    return _SIGNATURE_PREFIX + digest


class WebhookVerifier:
    """
    Verify and parse PalmPesa callbacks.

    Args:
        signing_secret: Secret issued by PalmPesa. When ``None`` callbacks are
            only parsed and checked for shape — confirm the outcome with
            ``payments.get_payment(order_id)`` before fulfilling.
        tolerance_seconds: Maximum clock skew / replay window (default 300).
    """

    def __init__(
        self,
        signing_secret: str | None = None,
        *,
        tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    ) -> None:
        if signing_secret is not None and not signing_secret:
            raise ValueError("signing_secret must be a non-empty string or None")
        if tolerance_seconds <= 0:
            raise ValueError("tolerance_seconds must be > 0")
        self._secret = signing_secret
        self.tolerance_seconds = tolerance_seconds

    @property
    def signing_enabled(self) -> bool:
        return self._secret is not None

    def verify(
        self,
        body: bytes | str,
        headers: Mapping[str, str],
        *,
        now: float | None = None,
    ) -> CallbackEvent:
        """
        Verify the signature (if signing is enabled) and parse the callback.

        Args:
            body:    Raw request body exactly as received.
            headers: Request headers (any mapping; lookup is case-insensitive).
            now:     Override the current Unix time (testing).

        Raises:
            WebhookVerificationError: bad/missing signature, stale timestamp,
                event-id mismatch or malformed body.
        """
        raw = body.encode() if isinstance(body, str) else bytes(body)
        lowered = {str(k).lower(): str(v) for k, v in headers.items()}

        if self._secret is not None:
            self._check_signature(self._secret, raw, lowered, now)

        event = parse_callback(raw)

        header_event_id = lowered.get(EVENT_ID_HEADER.lower())
        if header_event_id and not hmac.compare_digest(header_event_id, event.event_id):
            raise WebhookVerificationError("X-PalmPesa-Event-Id does not match body event_id")
        return event

    def _check_signature(
        self, secret: str, raw: bytes, headers: Mapping[str, str], now: float | None
    ) -> None:
        timestamp = headers.get(TIMESTAMP_HEADER.lower(), "").strip()
        received = headers.get(SIGNATURE_HEADER.lower(), "").strip()
        if not timestamp or not received:
            raise WebhookVerificationError("Missing X-PalmPesa-Timestamp or X-PalmPesa-Signature")
        if not timestamp.isdigit():
            raise WebhookVerificationError("Invalid X-PalmPesa-Timestamp")

        current = time.time() if now is None else now
        if abs(current - int(timestamp)) > self.tolerance_seconds:
            raise WebhookVerificationError("Callback timestamp outside tolerance window")

        expected = compute_signature(secret, timestamp, raw)
        if not hmac.compare_digest(expected.lower(), received.lower()):
            raise WebhookVerificationError("Invalid callback signature")


def parse_callback(body: bytes | str | Mapping[str, Any]) -> CallbackEvent:
    """
    Parse a callback body **without** verifying a signature.

    Use only when PalmPesa has not issued you a signing secret, and confirm
    the outcome with ``payments.get_payment(order_id)`` before fulfilling.

    Raises:
        WebhookVerificationError: body is not a JSON object or lacks required fields.
    """
    if isinstance(body, Mapping):
        data: Any = dict(body)
    else:
        try:
            data = json.loads(body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise WebhookVerificationError("Callback body is not valid JSON") from exc

    if not isinstance(data, dict):
        raise WebhookVerificationError("Callback body must be a JSON object")
    missing = [f for f in _REQUIRED_FIELDS if not data.get(f)]
    if missing:
        raise WebhookVerificationError(f"Callback missing required fields: {', '.join(missing)}")
    return CallbackEvent.from_payload(data)


__all__ = [
    "WebhookVerifier",
    "parse_callback",
    "compute_signature",
    "EVENT_ID_HEADER",
    "TIMESTAMP_HEADER",
    "SIGNATURE_HEADER",
    "DEFAULT_TOLERANCE_SECONDS",
]
