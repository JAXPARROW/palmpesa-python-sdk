# Changelog

## 0.2.0 — PalmPesa API v2

PalmPesa moved to the async Payments API v2 (`https://palmpesa.co.tz/api/v2/async/payments`).
The v1 host `palmpesa.drmlelwa.co.tz` and its endpoints are no longer used.
**This release is breaking.**

### Added
- `payments.request_payment()` → `POST /api/v2/async/payments` (202, status `INITIATING`).
- `payments.get_payment()` → `GET /api/v2/async/payments/{order_id}`.
- `payments.wait_for_final_status()` polling helper (rate-limit aware).
- Typed models: `Payment`, `PaymentStatus` (8 v2 statuses + `UNKNOWN`), `FailureReason`,
  `CallbackEvent`, `CallbackEventType`. `is_final` / `is_paid` helpers; raw payload kept in `.raw`.
- `WebhookVerifier` — HMAC-SHA256 verification of `X-PalmPesa-Signature` over
  `timestamp + "." + raw_body`, 300 s replay window, `X-PalmPesa-Event-Id` consistency check.
  `parse_callback()` for unsigned callbacks; `compute_signature()` helper.
- Local validation mirroring v2 rules (amount 100–100,000,000, `transaction_id` charset/length,
  public HTTPS `callback_url`, field lengths, TZS only) — bad input never reaches the network.
- Exceptions: `NetworkError`, `RequestTimeoutError`, `AccountFrozenError`,
  `WebhookVerificationError`; `ValidationError.errors` (field → messages) from 422 responses;
  `RateLimitError.retry_after`; `.code` on all errors.
- `verify_credentials()`; `is_healthy()` no longer needs a list endpoint.
- `http_client=` to inject your own `httpx.Client` / `httpx.AsyncClient`; `user_agent=` suffix.
- `examples/live_check.py` live smoke test (safe mode never creates a payment).

### Changed
- Retries now cover **POST** too (network errors, timeouts, 429, 5xx) because v2 is
  idempotent on `transaction_id`. Exponential backoff with jitter; honours `Retry-After`.
- `max_retries` now means *extra* attempts after the first (default 2 → 3 attempts total).
- Client options after `api_token` are keyword-only.
- `normalize_phone()` returns `255XXXXXXXXX` (was `0XXXXXXXXX`) and raises `ValidationError`
  on invalid input (was `""`). Only `2556…`/`2557…` mobile numbers are accepted.
- `generate_transaction_id()` format is now `PREFIX-<utc timestamp>-<16 hex>`.
- 400 **and** 422 map to `ValidationError`.
- Redirects are never followed; the API token is never included in `repr()`.

### Removed
- `payments.initiate_mobile_payment()`, `payments.get_order_status()` (v1 endpoints).
- `transactions` service — v2 has no transaction-list endpoint.
- `address` / `postcode` request fields.
- `WebhookValidator`, `WebhookEvent`, `PAYMENT_STATUS_*` constants → use `WebhookVerifier`,
  `CallbackEvent`, `PaymentStatus`.
- `InsufficientFundsError` — v2 does not report it.
- The v1 "429 hidden inside 502" workaround.

### Migrating from 0.1.x

| 0.1.x | 0.2.0 |
| --- | --- |
| `PalmPesa(token, base_url, 30, 3)` | `PalmPesa(token, timeout=30, max_retries=2)` |
| `initiate_mobile_payment(amount=, phone=, transaction_id=, name=, email=, callback_url=)` → `dict["order_id"]` | `request_payment(...same keywords..., buyer_remarks=None)` → `Payment.order_id` |
| `get_order_status(order_id)["data"][0]["payment_status"]` | `get_payment(order_id).status` / `.is_paid` |
| `"COMPLETED" / "PENDING" / "FAILED"` | `PaymentStatus.*`; failures are `CANCELLED`, `REJECTED`, `INITIATION_FAILED`, `EXPIRED` |
| `WebhookValidator.is_valid_payload(dict)` | `WebhookVerifier(secret).verify(raw_body, headers)` |
| callback `payment_status` | callback `status` + `event` + `event_id` (dedupe on it) |
| minimum 500 TZS | minimum 100 TZS |
| `email=""` accepted | a valid email is **required** |

## 0.1.0

- Initial release (PalmPesa v1).
