"""Invariant tests — do not encode specific config values."""
import pytest
from ratelimit.bucket import TokenBucket, CAPACITY, REFILL_RATE, INITIAL_TOKENS, OVERDRAFT_ALLOWANCE


def test_instantiates():
    b = TokenBucket()
    assert b is not None


def test_capacity_positive():
    assert CAPACITY > 0


def test_refill_rate_positive():
    assert REFILL_RATE > 0


def test_initial_tokens_at_most_capacity():
    assert INITIAL_TOKENS <= CAPACITY


def test_overdraft_allowance_nonnegative():
    assert OVERDRAFT_ALLOWANCE >= 0


def test_consume_returns_bool():
    b = TokenBucket()
    assert isinstance(b.consume(), bool)


def test_fresh_bucket_allows_at_least_one():
    b = TokenBucket()
    assert b.consume() is True


def test_available_nonneg():
    b = TokenBucket()
    assert b.available() >= 0
