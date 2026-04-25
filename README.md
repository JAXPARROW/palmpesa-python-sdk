# PalmPesa Python SDK

Production-grade Python SDK for the [PalmPesa](https://palmpesa.drmlelwa.co.tz) payment API — supports both **sync** and **async** usage, automatic retries, typed exceptions, and webhook validation.

[![PyPI version](https://img.shields.io/pypi/v/palmpesa-python-sdk.svg)](https://pypi.org/project/palmpesa-python-sdk/)
[![Python versions](https://img.shields.io/pypi/pyversions/palmpesa-python-sdk.svg)](https://pypi.org/project/palmpesa-python-sdk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Features

- **Sync & Async** — `PalmPesa` for blocking code, `AsyncPalmPesa` for asyncio
- **USSD Push payments** — initiate STK prompts and poll order status
- **Auto retries** — exponential backoff on transient 5xx errors
- **Typed exceptions** — structured error hierarchy (never a bare `Exception`)
- **Thread-safe** — share a single client across threads
- **Context manager** — `with` / `async with` for automatic cleanup
- **Webhook validation** — verify and parse incoming payment callbacks
- **PEP 561 compliant** — ships with `py.typed`

---

## Installation

```bash
pip install palmpesa-python-sdk
```

Requires Python 3.10 or newer.

---

## Quick Start

### Synchronous

```python
from palmpesa import PalmPesa

with PalmPesa(api_token="your-api-token") as client:
    # Initiate a USSD push payment (minimum amount: 500 TZS)
    result = client.payments.initiate_mobile_payment(
        amount=1000,
        phone="0693662424",
        transaction_id="TXN-001",
        name="John Doe",
        email="john@example.com",
        callback_url="https://yourapp.com/webhook/palmpesa",
    )
    print(result["order_id"])

    # Check payment status
    status = client.payments.get_order_status(result["order_id"])
    print(status["payment_status"])  # PENDING | COMPLETED | FAILED

    # List transactions
    txns = client.transactions.list_all(page=1, per_page=20)
```

### Asynchronous

```python
import asyncio
from palmpesa import AsyncPalmPesa

async def main():
    async with AsyncPalmPesa(api_token="your-api-token") as client:
        result = await client.payments.initiate_mobile_payment(
            amount=1000,
            phone="0693662424",
            transaction_id="TXN-001",
            name="John Doe",
            email="john@example.com",
            callback_url="https://yourapp.com/webhook/palmpesa",
        )
        status = await client.payments.get_order_status(result["order_id"])

asyncio.run(main())
```

---

## USSD Push Payments

> **Minimum amount: 500 TZS**
>
> The PalmPesa gateway enforces a minimum payment amount of **TZS 500** for USSD push (STK) requests. Amounts below this threshold will be rejected by the API.

### `initiate_mobile_payment`

Sends a USSD STK push prompt to the customer's phone.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `amount` | `int` | Yes | Amount in TZS — **minimum 500** |
| `phone` | `str` | Yes | Customer phone in any Tanzanian format (`"0693662424"`, `"+255693662424"`) |
| `transaction_id` | `str` | Yes | Unique reference for this payment |
| `name` | `str` | Yes | Customer full name |
| `email` | `str` | Yes | Customer email address |
| `callback_url` | `str` | Yes | Publicly reachable URL for payment result callbacks |
| `address` | `str` | No | Customer address (default: `"Dar es Salaam"`) |
| `postcode` | `str` | No | Customer postcode (default: `"11111"`) |

**Returns:** `{"order_id": "...", "message": "..."}`

### `get_order_status`

Poll the result of a previously initiated payment.

| Parameter | Type | Description |
| --- | --- | --- |
| `order_id` | `str` | The `order_id` returned by `initiate_mobile_payment` |

**Returns:** `{"payment_status": "COMPLETED" | "PENDING" | "FAILED", ...}`

---

## Transactions

```python
# Paginated transaction history
txns = client.transactions.list_all(page=1, per_page=50)
```

---

## Webhook Validation

Validate and parse callbacks sent to your webhook endpoint:

```python
from palmpesa import WebhookValidator, PAYMENT_STATUS_COMPLETED

validator = WebhookValidator(secret="your-webhook-secret")

# Flask example
@app.route("/webhook/palmpesa", methods=["POST"])
def handle_webhook():
    event = validator.validate(
        payload=request.data,
        signature=request.headers.get("X-PalmPesa-Signature", ""),
    )
    if event.payment_status == PAYMENT_STATUS_COMPLETED:
        # fulfil order
        ...
    return "", 200
```

---

## Error Handling

```python
from palmpesa import (
    PalmPesa,
    ValidationError,
    InsufficientFundsError,
    AuthenticationError,
    RateLimitError,
    ServerError,
    PalmPesaError,
)

with PalmPesa(api_token="your-api-token") as client:
    try:
        result = client.payments.initiate_mobile_payment(
            amount=1000, phone="0693662424", transaction_id="TXN-001",
            name="John Doe", email="john@example.com",
            callback_url="https://yourapp.com/webhook",
        )
    except ValidationError as e:
        print(f"Bad request: {e}")        # e.g. amount below 500, bad phone
    except InsufficientFundsError as e:
        print(f"Insufficient funds: {e}")
    except AuthenticationError as e:
        print(f"Invalid API token: {e}")
    except RateLimitError as e:
        print(f"Rate limited: {e}")
    except ServerError as e:
        print(f"PalmPesa server error: {e}")
    except PalmPesaError as e:
        print(f"Unexpected error: {e}")
```

### Exception Hierarchy

```text
PalmPesaError
├── AuthenticationError   (HTTP 401)
├── ForbiddenError        (HTTP 403)
├── ValidationError       (HTTP 400 — includes invalid phone, bad payload)
├── InsufficientFundsError(HTTP 400 — insufficient balance)
├── NotFoundError         (HTTP 404)
├── ConflictError         (HTTP 409)
├── RateLimitError        (HTTP 429)
└── ServerError           (HTTP 5xx)
```

---

## Configuration

```python
client = PalmPesa(
    api_token="your-api-token",
    base_url="https://palmpesa.drmlelwa.co.tz",  # override for staging
    timeout=30.0,      # request timeout in seconds
    max_retries=3,     # retry attempts on transient 5xx errors
)
```

---

## Health Check

```python
if client.is_healthy():
    print("API reachable and token valid")
```

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint & format
ruff check src/
black src/
mypy src/
```

---

## License

MIT — see [LICENSE](LICENSE).
