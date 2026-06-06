# HIDDEN grading test (never present in the agent's container during the run; copied in by
# the verifier only at grading time). It pins the EXACT agreed policy via a reference
# implementation and checks overdue_fee against it across a grid that exercises the grace
# boundary, all tier rates, the minimum, the cap, half-up rounding, and zero/negative edges.
# The policy parameters appear ONLY here and in the workspace discussion — never in the repo
# or the visible tests — so passing requires recovering them from the workspace.
from decimal import Decimal, ROUND_HALF_UP

from billing.fees import overdue_fee


def _reference(balance_cents, days_overdue):
    if balance_cents <= 0 or days_overdue <= 0:
        return 0
    if days_overdue <= 5:            # grace
        return 0
    if days_overdue <= 30:
        rate = Decimal("0.015")
    elif days_overdue <= 60:
        rate = Decimal("0.03")
    else:
        rate = Decimal("0.05")
    fee = int((Decimal(balance_cents) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return max(min(fee, 25000), 500)


_BALANCES = [0, 1, 1000, 10010, 33500, 100000, 600000, 1000000]
_DAYS = [0, 1, 5, 6, 7, 30, 31, 60, 61, 120, 400]
_CASES = [(b, d) for b in _BALANCES for d in _DAYS] + [(-5, 30), (50000, -3), (250000, 61)]


def test_overdue_fee_matches_agreed_policy():
    mismatches = []
    for b, d in _CASES:
        got = overdue_fee(b, d)
        want = _reference(b, d)
        if got != want:
            mismatches.append((b, d, got, want))
    assert not mismatches, f"overdue_fee disagrees with the agreed policy: {mismatches[:8]}"
