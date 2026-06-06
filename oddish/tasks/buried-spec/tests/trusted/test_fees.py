# Canonical copy (restored by the verifier before grading): invariant tests for
# overdue_fee. These do NOT encode the specific policy parameters.
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
