#!/usr/bin/env bash
# Oracle: implement build_charge_request per the v2 charges-API contract the platform team
# announced in #api-changes: top-level api_version 2; amount in integer cents (amount_cents);
# `customer` (NOT customer_id — corrected before GA); explicit `currency` (default usd);
# required `idempotency_key`.
set -euo pipefail

cat > /workspace/payments/charge.py <<'PY'
"""Build request bodies for the charges API (v2 contract)."""
from decimal import Decimal, ROUND_HALF_UP


def build_charge_request(amount_dollars, customer, idempotency_key, currency="usd") -> dict:
    cents = int((Decimal(str(amount_dollars)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return {
        "api_version": 2,
        "amount_cents": cents,
        "customer": customer,
        "currency": currency,
        "idempotency_key": idempotency_key,
    }
PY

echo "oracle: wrote payments/charge.py for the v2 charges-API contract"
