#!/usr/bin/env bash
# Oracle: implement billing.fees.overdue_fee per the policy the team agreed in the
# #billing-policy discussion (grace 5d; 1.5%/3%/5% tiers for 6-30/31-60/61+; $5 min once a
# fee applies; $250 cap; round half-up to the cent; balance<=0 or days<=0 -> 0).
set -euo pipefail

cat > /workspace/billing/fees.py <<'PY'
"""Overdue-fee calculation (implemented per the team's agreed policy)."""
from decimal import Decimal, ROUND_HALF_UP

_GRACE_DAYS = 5
_MIN_FEE_CENTS = 500
_CAP_CENTS = 25000


def overdue_fee(balance_cents: int, days_overdue: int) -> int:
    if balance_cents <= 0 or days_overdue <= 0:
        return 0
    if days_overdue <= _GRACE_DAYS:
        return 0
    if days_overdue <= 30:
        rate = Decimal("0.015")
    elif days_overdue <= 60:
        rate = Decimal("0.03")
    else:
        rate = Decimal("0.05")
    fee = int((Decimal(balance_cents) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    fee = max(fee, _MIN_FEE_CENTS)
    fee = min(fee, _CAP_CENTS)
    return fee
PY

echo "oracle: wrote billing/fees.py per the agreed policy"
