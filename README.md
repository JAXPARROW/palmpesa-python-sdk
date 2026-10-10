# PalmPesa Python SDK

Production-grade Python SDK for the [PalmPesa](https://palmpesa.co.tz) **Payments API v2**: sync and async clients, safe retries keyed on `transaction_id`, typed models, signed-callback verification and a structured exception hierarchy.

[![PyPI version](https://img.shields.io/pypi/v/palmpesa-python-sdk.svg)](https://pypi.org/project/palmpesa-python-sdk/)
[![Python versions](https://img.shields.io/pypi/pyversions/palmpesa-python-sdk.svg)](https://pypi.org/project/palmpesa-python-sdk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> Upgrading from 0.1.x (API v1)? 0.2.0 is a breaking release. See the [migration table](CHANGELOG.md#migrating-from-01x).

API reference: <https://documentation.palmpesa.co.tz/>

---

## Features

- **Sync & async**: `PalmPesa` for blocking code, `AsyncPalmPesa` for asyncio
- **Safe retries**: network errors, timeouts, 429 and 5xx are retried with jittered backoff, including `POST`. PalmPesa treats a repeated `transaction_id` as the same payment, so a retry never charges twice.
- **Typed models**: `Payment`, `PaymentStatus`, `CallbackEvent` with `is_paid` / `is_final`
- **Signed callbacks**: HMAC-SHA256 verification, replay window, event-id checks
- **Local validation**: bad amount, phone, email, `transaction_id` or callback URL is rejected before any network call
- **Typed exceptions**: never a bare `Exception`; 422 field errors exposed
- **Thread-safe**, context managers, PEP 561 (`py.typed`), mypy-strict clean

## Installation

```bash
pip install palmpesa-python-sdk
```

Requires Python 3.10+.

---

## Quick start

```python
from palmpesa import PalmPesa, generate_transaction_id

with PalmPesa(api_token="YOUR_API_TOKEN") as palmpesa:
    # 1. Generate and STORE your transaction_id before calling PalmPesa.
    tid = generate_transaction_id("ORDER")

    # 2. Push the mobile-money prompt. 202 Accepted ≠ paid.
    payment = palmpesa.payments.request_payment(
        transaction_id=tid,
        amount=10_000,                      # whole TZS, 100 – 100,000,000
        phone="0712345678",                 # any TZ format → 255712345678
        name="Juma Hassan",
        email="juma@example.com",
        callback_url="https://shop.example.com/palmpesa/callback",
        buyer_remarks="Payment for order 123",   # optional, shown to customer
    )
    print(payment.order_id, payment.status)      # PALMPESAV2A… PaymentStatus.INITIATING

    # 3. Wait for the callback (preferred) — or check the status:
    payment = palmpesa.payments.get_payment(payment.order_id)
    if payment.is_paid:
        ...  # fulfil
```

### Async

```python
import asyncio
from palmpesa import AsyncPalmPesa

async def main() -> None:
    async with AsyncPalmPesa(api_token="YOUR_API_TOKEN") as palmpesa:
        payment = await palmpesa.payments.request_payment(...)
        final = await palmpesa.payments.wait_for_final_status(payment.order_id, timeout=300)

asyncio.run(main())
```

---

## Payments

### `request_payment(*, transaction_id, amount, phone, name, email, callback_url, buyer_remarks=None, merchant_remarks=None, currency="TZS") -> Payment`

`POST /api/v2/async/payments`. All arguments are keyword-only.

| Argument | Rules |
| --- | --- |
| `transaction_id` | Your unique ID, 1–191 chars of `A-Z a-z 0-9 . _ : -` |
| `amount` | `int` or integral `Decimal`, **100 – 100,000,000** TZS. `float` is rejected |
| `phone` | Tanzanian mobile number (`0712…`, `712…`, `255712…`, `+255 712 …`) |
| `name` | ≤ 255 chars |
| `email` | Valid email (**required** by v2) |
| `callback_url` | Public `https://` URL, not localhost or a private IP, ≤ 2048 chars |
| `buyer_remarks` / `merchant_remarks` | Optional, ≤ 255 chars |

**Retries and duplicates:**

- Same `transaction_id` + same details → the original payment comes back. The customer gets no second prompt and no second charge.
- Same `transaction_id` + different details → `ConflictError` (409).
- Once a payment is final, a new payment needs a **new** `transaction_id`.

### `get_payment(order_id) -> Payment`

`GET /api/v2/async/payments/{order_id}`. Raises `NotFoundError` for unknown orders.

### `wait_for_final_status(order_id, *, timeout=300, poll_interval=5) -> Payment`

Polls until the payment is final or `timeout` elapses, then returns the last state (check `.is_final`). Use it in scripts, tests and reconciliation jobs. In production, rely on callbacks.

### Statuses

| `PaymentStatus` | Final | Meaning |
| --- | --- | --- |
| `INITIATING` | no | Accepted; prompt not sent yet |
| `PENDING` | no | Prompt sent; waiting for the customer |
| `AMBIGUOUS` | no | PalmPesa is confirming the outcome. **Do not resend** |
| `COMPLETED` | yes | Money received: **the only paid status** |
| `CANCELLED` | yes | Customer cancelled / did not approve |
| `REJECTED` | yes | Network rejected the payment |
| `INITIATION_FAILED` | yes | Prompt not sent; see `payment.failure_reason`; nothing charged |
| `EXPIRED` | yes* | Not paid within ~1 h. *A late `COMPLETED` can still follow* |
| `UNKNOWN` | no | Status not known to this SDK version (raw value in `payment.raw`) |

---

## Callbacks

PalmPesa POSTs to `callback_url` when a payment reaches a final status. Requirements:

- Respond **2xx within 10 s**. PalmPesa makes up to 5 attempts in total.
- **Deduplicate on `event_id`.**
- Before fulfilling, match `transaction_id`, `order_id`, `amount` and `currency` against your records.
- Treat `payment.completed` as paid even if it arrives **after** `payment.expired`.

```python
import os
from flask import Flask, request
from palmpesa import WebhookVerifier, WebhookVerificationError

app = Flask(__name__)
verifier = WebhookVerifier(signing_secret=os.environ.get("PALMPESA_SIGNING_SECRET"))

@app.post("/palmpesa/callback")
def palmpesa_callback():
    try:
        event = verifier.verify(request.get_data(), request.headers)   # RAW bytes!
    except WebhookVerificationError:
        return "", 401

    if seen_before(event.event_id):
        return {"received": True}, 200

    order = load_order(event.transaction_id)
    if event.is_paid and order.amount == event.amount and event.currency == "TZS":
        fulfil(order, event)
    return {"received": True}, 200
```

If PalmPesa has issued you a signing secret, `verify()` checks `X-PalmPesa-Signature` (`sha256=` + HMAC of `timestamp.body`), rejects timestamps more than 300 s from now, and checks that `X-PalmPesa-Event-Id` matches the body.

**Without a secret**, `verify()` only parses and checks the shape of the callback. Anyone can POST to your URL, so confirm with `payments.get_payment(event.order_id)` before you fulfil.

---

## Errors

```text
PalmPesaError                 .message .status_code .response .code
├── NetworkError              connection / DNS / TLS (retry with same transaction_id)
│   └── RequestTimeoutError
├── AuthenticationError       401 missing / invalid token
├── ForbiddenError            403 account pending approval
│   └── AccountFrozenError    403 code=ACCOUNT_FROZEN
├── ValidationError           400 / 422, or local validation (.errors: field → [messages])
├── NotFoundError             404 unknown order_id
├── ConflictError             409 transaction_id reused with different details
├── RateLimitError            429 (.retry_after)
├── ServerError               5xx (retry with same transaction_id)
└── WebhookVerificationError  bad callback signature / timestamp / body
```

```python
from palmpesa import ValidationError, ConflictError, PalmPesaError

try:
    payment = palmpesa.payments.request_payment(...)
except ValidationError as e:
    print(e.message, e.errors)        # {"callback_url": ["..."]}
except ConflictError:
    ...                               # generate a new transaction_id
except PalmPesaError as e:
    log.error("PalmPesa failed: %r", e)
```

---

## Configuration

```python
PalmPesa(
    api_token="…",
    base_url="https://palmpesa.co.tz",  # default
    timeout=30.0,                        # seconds or httpx.Timeout
    max_retries=2,                       # extra attempts after the first
    user_agent="myapp/1.0",              # appended to the SDK User-Agent
    http_client=None,                    # bring your own httpx.Client
)
```

Rate limits: `POST` 30/min, `GET` 120/min per account. Share **one** client per process.

```python
palmpesa.verify_credentials()   # raises AuthenticationError / ForbiddenError …
palmpesa.is_healthy()           # bool
```

Logging goes to the `palmpesa` logger (retries are logged at `WARNING`). The token is never logged.

---

## Development

```bash
make install    # pip install -e ".[dev]"
make check      # ruff + black + mypy --strict + pytest with coverage
make live       # safe live checks against the real API (needs PALMPESA_API_TOKEN)
```

`make live` never creates a payment. To run a **real** end-to-end payment to your own phone:

```bash
python examples/live_check.py pay --phone 0712345678 --amount 100 \
    --callback-url https://webhook.site/<id> --yes
```

## License

MIT. See [LICENSE](LICENSE).
