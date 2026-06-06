# Invariant tests for overdue_fee. These hold for ANY correct implementation of the agreed
# policy (they intentionally do NOT encode the specific grace period, tier rates, minimum,
# or cap — those come from the team's agreed policy). They currently FAIL because the
# function is unimplemented; make them pass without breaking test_money.py.
import pytest

from billing.fees import overdue_fee


@pytest.mark.parametrize("balance,days", [(0, 30), (0, 0), (100000, 0), (100000, -10)])
def test_no_fee_when_no_balance_or_not_overdue(balance, days):
    assert overdue_fee(balance, days) == 0


@pytest.mark.parametrize("balance,days", [(100000, 45), (5000, 10), (1, 999), (10000000, 400)])
def test_fee_is_nonnegative_int(balance, days):
    fee = overdue_fee(balance, days)
    assert isinstance(fee, int)
    assert fee >= 0


def test_large_overdue_balance_incurs_some_fee():
    # A big balance that is very overdue must incur a positive fee.
    assert overdue_fee(500000, 120) > 0


def test_nondecreasing_in_days():
    prev = -1
    for d in range(0, 200, 3):
        fee = overdue_fee(100000, d)
        assert fee >= prev
        prev = fee


def test_nondecreasing_in_balance():
    prev = -1
    for b in range(0, 2000000, 25000):
        fee = overdue_fee(b, 90)
        assert fee >= prev
        prev = fee
