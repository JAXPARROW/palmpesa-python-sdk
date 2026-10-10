#!/usr/bin/env python3
"""
Live smoke test against the real PalmPesa API v2.

    export PALMPESA_API_TOKEN=...

    # Safe — never creates a payment:
    python examples/live_check.py

    # REAL payment: pushes a prompt and charges the phone if approved.
    python examples/live_check.py pay --phone 0712345678 --amount 100 \
        --callback-url https://webhook.site/<id> --yes

Safe checks:
  1. bad token            → AuthenticationError (401)
  2. real token           → verify_credentials() (404 on a sentinel order)
  3. unknown order_id     → NotFoundError (404)
  4. invalid POST payload → ValidationError (422) — sent raw, bypassing local
     validation, with amount/phone/callback all invalid so it cannot charge.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any

import httpx

from palmpesa import (
    AuthenticationError,
    NotFoundError,
    PalmPesa,
    PalmPesaError,
    ValidationError,
    generate_transaction_id,
)
from palmpesa._base import PAYMENTS_PATH

_IPV4_ONLY = False


def _client(token: str, base_url: str, **kwargs: Any) -> PalmPesa:
    http = None
    if _IPV4_ONLY:
        # Bind to 0.0.0.0 so connections go over IPv4 (hosts with broken IPv6).
        http = httpx.Client(transport=httpx.HTTPTransport(local_address="0.0.0.0"), timeout=30)
    return PalmPesa(api_token=token, base_url=base_url, http_client=http, **kwargs)


def _ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def _fail(msg: str) -> None:
    print(f"  FAIL  {msg}")


def safe_checks(token: str, base_url: str) -> bool:
    passed = True

    print("1. Invalid token is rejected")
    with _client("invalid-token-sdk-check", base_url, max_retries=0) as bad:
        try:
            bad.verify_credentials()
            _fail("invalid token was accepted")
            passed = False
        except AuthenticationError as e:
            _ok(f"AuthenticationError {e.status_code}: {e.message}")

    with _client(token, base_url) as pp:
        print("2. Real token is accepted")
        try:
            pp.verify_credentials()
            _ok("verify_credentials()")
        except PalmPesaError as e:
            _fail(f"{type(e).__name__} {e.status_code}: {e.message} {e.response}")
            return False

        print("3. Unknown order_id → 404")
        try:
            pp.payments.get_payment("PALMPESAV2A20260101000000000NOTFOUND")
            _fail("expected NotFoundError")
            passed = False
        except NotFoundError as e:
            _ok(f"NotFoundError: {e.message}")

        print("4. Invalid payload → 422 (no charge possible)")
        try:
            pp.request(
                "POST",
                PAYMENTS_PATH,
                json={
                    "transaction_id": generate_transaction_id("SDKCHECK"),
                    "amount": 1,
                    "currency": "TZS",
                    "phone": "000",
                    "name": "SDK Check",
                    "email": "not-an-email",
                    "callback_url": "http://localhost/cb",
                },
            )
            _fail("server accepted an invalid payload!")
            passed = False
        except ValidationError as e:
            _ok(f"ValidationError {e.status_code}: fields={sorted(e.errors)}")

    return passed


def real_payment(token: str, base_url: str, args: argparse.Namespace) -> bool:
    with _client(token, base_url) as pp:
        tid = generate_transaction_id("SDKLIVE")
        print(f"Requesting {args.amount} TZS from {args.phone} (transaction_id={tid})")
        payment = pp.payments.request_payment(
            transaction_id=tid,
            amount=args.amount,
            phone=args.phone,
            name="SDK Live Test",
            email=args.email,
            callback_url=args.callback_url,
            buyer_remarks="PalmPesa SDK live test",
            merchant_remarks="palmpesa-python-sdk live_check",
        )
        print(f"  accepted: {payment}")

        print("Idempotent retry with the same transaction_id …")
        again = pp.payments.request_payment(
            transaction_id=tid,
            amount=args.amount,
            phone=args.phone,
            name="SDK Live Test",
            email=args.email,
            callback_url=args.callback_url,
            buyer_remarks="PalmPesa SDK live test",
            merchant_remarks="palmpesa-python-sdk live_check",
        )
        same = again.order_id == payment.order_id
        (_ok if same else _fail)(f"same order_id returned: {again.order_id}")

        print("Approve the prompt on the phone; polling up to 3 minutes …")
        final = pp.payments.wait_for_final_status(payment.order_id, timeout=180, poll_interval=5)
        print(f"  final: {final}")
        return same and final.is_final


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("mode", nargs="?", choices=["safe", "pay"], default="safe")
    parser.add_argument(
        "--base-url", default=os.environ.get("PALMPESA_BASE_URL", "https://palmpesa.co.tz")
    )
    parser.add_argument("--phone")
    parser.add_argument("--amount", type=int, default=100)
    parser.add_argument("--email", default="sdk-test@example.com")
    parser.add_argument("--callback-url")
    parser.add_argument("--yes", action="store_true", help="confirm a REAL charge")
    parser.add_argument("--ipv4", action="store_true", help="force IPv4 (broken IPv6 hosts)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)
    token = os.environ.get("PALMPESA_API_TOKEN")
    if not token:
        print("Set PALMPESA_API_TOKEN", file=sys.stderr)
        return 2

    global _IPV4_ONLY
    _IPV4_ONLY = args.ipv4

    try:
        if args.mode == "safe":
            return 0 if safe_checks(token, args.base_url) else 1

        if not (args.phone and args.callback_url and args.yes):
            print(
                "pay mode needs --phone, --callback-url and --yes (this is a REAL charge)",
                file=sys.stderr,
            )
            return 2
        return 0 if real_payment(token, args.base_url, args) else 1
    except PalmPesaError as e:
        print(f"  ERROR {e!r}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
