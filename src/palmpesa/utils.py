"""Phone normalisation, transaction-ID generation and request validation."""

from __future__ import annotations

import ipaddress
import re
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from .exceptions import ValidationError

MIN_AMOUNT = 100
MAX_AMOUNT = 100_000_000
SUPPORTED_CURRENCIES = frozenset({"TZS"})
MAX_TRANSACTION_ID_LENGTH = 191
MAX_NAME_LENGTH = 255
MAX_REMARKS_LENGTH = 255
MAX_CALLBACK_URL_LENGTH = 2048

_TRANSACTION_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,191}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_LOCAL_HOSTNAMES = frozenset({"localhost", "localhost.localdomain"})


def normalize_phone(phone: str) -> str:
    """
    Normalise a Tanzanian mobile number to PalmPesa's ``2556XXXXXXXX`` /
    ``2557XXXXXXXX`` format.

    Examples::

        normalize_phone("0712345678")        # "255712345678"
        normalize_phone("712345678")         # "255712345678"
        normalize_phone("+255 712 345 678")  # "255712345678"
        normalize_phone("255612345678")      # "255612345678"

    Raises:
        :class:`~palmpesa.exceptions.ValidationError`: if the input is not a
        Tanzanian mobile number.
    """
    digits = re.sub(r"\D", "", str(phone or ""))

    if len(digits) == 12 and digits.startswith("255"):
        local = digits[3:]
    elif len(digits) == 10 and digits.startswith("0"):
        local = digits[1:]
    elif len(digits) == 9:
        local = digits
    else:
        local = ""

    if len(local) != 9 or local[0] not in "67":
        raise _invalid("phone", f"Invalid Tanzanian mobile number: {phone!r}")
    return "255" + local


def generate_transaction_id(prefix: str = "TXN") -> str:
    """Generate a unique ``transaction_id`` (UTC timestamp + 64 random bits).

    Generate it **once** per payment and store it before calling
    ``request_payment`` so a retry after a timeout reuses the same value.
    """
    if not re.fullmatch(r"[A-Za-z0-9._:-]{0,40}", prefix):
        raise ValueError("prefix may contain only letters, digits, '.', '_', ':' and '-'")
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S%f")
    sep = "-" if prefix else ""
    return f"{prefix}{sep}{ts}-{secrets.token_hex(8)}"


def build_payment_payload(
    *,
    transaction_id: str,
    amount: int | Decimal,
    phone: str,
    name: str,
    email: str,
    callback_url: str,
    currency: str = "TZS",
    buyer_remarks: str | None = None,
    merchant_remarks: str | None = None,
) -> dict[str, Any]:
    """Validate inputs against the v2 rules and build the JSON body.

    Raises :class:`~palmpesa.exceptions.ValidationError` (``status_code=None``)
    before any network call, so bad input never reaches PalmPesa.
    """
    payload: dict[str, Any] = {
        "transaction_id": validate_transaction_id(transaction_id),
        "amount": _validate_amount(amount),
        "currency": _validate_currency(currency),
        "phone": normalize_phone(phone),
        "name": _validate_text("name", name, MAX_NAME_LENGTH, required=True),
        "email": _validate_email(email),
        "callback_url": validate_callback_url(callback_url),
    }
    if buyer_remarks is not None:
        payload["buyer_remarks"] = _validate_text(
            "buyer_remarks", buyer_remarks, MAX_REMARKS_LENGTH
        )
    if merchant_remarks is not None:
        payload["merchant_remarks"] = _validate_text(
            "merchant_remarks", merchant_remarks, MAX_REMARKS_LENGTH
        )
    return payload


def validate_transaction_id(transaction_id: str) -> str:
    if not isinstance(transaction_id, str) or not _TRANSACTION_ID_RE.fullmatch(transaction_id):
        raise _invalid(
            "transaction_id",
            "transaction_id must be 1-191 characters of letters, digits, '.', '_', ':' or '-'",
        )
    return transaction_id


def validate_callback_url(url: str) -> str:
    if not isinstance(url, str) or not url:
        raise _invalid("callback_url", "callback_url is required")
    if len(url) > MAX_CALLBACK_URL_LENGTH:
        raise _invalid("callback_url", f"callback_url exceeds {MAX_CALLBACK_URL_LENGTH} characters")

    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host:
        raise _invalid("callback_url", "callback_url must be an absolute https:// URL")
    if host in _LOCAL_HOSTNAMES or host.endswith(".localhost"):
        raise _invalid("callback_url", "callback_url must be publicly reachable (not localhost)")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not ip.is_global:
            raise _invalid("callback_url", "callback_url must not point to a private/local IP")
    return url


def _validate_amount(amount: int | Decimal) -> int:
    # bool is an int subclass; float is rejected to avoid silent rounding of money.
    if isinstance(amount, bool) or not isinstance(amount, (int, Decimal)):
        raise _invalid("amount", "amount must be an int (whole TZS)")
    if isinstance(amount, Decimal):
        if amount != amount.to_integral_value():
            raise _invalid("amount", "amount must be a whole number of TZS")
        amount = int(amount)
    if not MIN_AMOUNT <= amount <= MAX_AMOUNT:
        raise _invalid("amount", f"amount must be between {MIN_AMOUNT:,} and {MAX_AMOUNT:,} TZS")
    return amount


def _validate_currency(currency: str) -> str:
    if currency not in SUPPORTED_CURRENCIES:
        raise _invalid("currency", f"currency must be one of {sorted(SUPPORTED_CURRENCIES)}")
    return currency


def _validate_email(email: str) -> str:
    email = (email or "").strip()
    if not _EMAIL_RE.fullmatch(email):
        raise _invalid("email", f"A valid email address is required, got {email!r}")
    return email


def _validate_text(field_name: str, value: str, max_len: int, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise _invalid(field_name, f"{field_name} must be a string")
    value = value.strip()
    if required and not value:
        raise _invalid(field_name, f"{field_name} is required")
    if len(value) > max_len:
        raise _invalid(field_name, f"{field_name} must be at most {max_len} characters")
    return value


def _invalid(field_name: str, message: str) -> ValidationError:
    return ValidationError(message, errors={field_name: [message]})


__all__ = [
    "MIN_AMOUNT",
    "MAX_AMOUNT",
    "normalize_phone",
    "generate_transaction_id",
    "build_payment_payload",
    "validate_transaction_id",
    "validate_callback_url",
]
