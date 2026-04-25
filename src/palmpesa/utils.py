"""Phone number normalization and order ID helpers."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone


def normalize_phone(phone: str) -> str:
    """
    Normalize a Tanzanian phone number to local 0-prefix format.

    PalmPesa expects the local format (e.g. ``"0693662424"``).

    Examples::

        normalize_phone("+255693662424")  # "0693662424"
        normalize_phone("255693662424")   # "0693662424"
        normalize_phone("0693662424")     # "0693662424"
        normalize_phone("693662424")      # "0693662424"

    Returns an empty string when the input cannot be recognised as a
    valid Tanzanian number.
    """
    if not phone:
        return ""

    digits = re.sub(r"\D", "", str(phone).strip())

    if digits.startswith("255") and len(digits) == 12:
        return "0" + digits[3:]
    if digits.startswith("0") and len(digits) == 10:
        return digits
    if len(digits) == 9:
        return "0" + digits

    return ""


def generate_transaction_id(prefix: str = "TXN") -> str:
    """Generate a unique transaction ID safe for use as ``transaction_id``."""
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S%f")[:-3]
    rand = secrets.token_hex(4)
    return f"{prefix}{ts}{rand}"


__all__ = ["normalize_phone", "generate_transaction_id"]
