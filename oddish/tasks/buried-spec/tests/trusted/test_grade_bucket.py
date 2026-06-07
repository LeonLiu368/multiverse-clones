# HIDDEN grading test — never present in the agent's container during the run.
# Pins the exact token-bucket config agreed in the #platform-infra load-test discussion.
from ratelimit.bucket import CAPACITY, REFILL_RATE, INITIAL_TOKENS, OVERDRAFT_ALLOWANCE, TokenBucket
import time


def test_agreed_capacity():
    assert CAPACITY == 100, f"CAPACITY should be 100 (agreed in load-test review), got {CAPACITY}"


def test_agreed_refill_rate():
    assert REFILL_RATE == 10.0, f"REFILL_RATE should be 10.0, got {REFILL_RATE}"


def test_agreed_initial_tokens():
    assert INITIAL_TOKENS == 100, f"INITIAL_TOKENS should be 100 (start full), got {INITIAL_TOKENS}"


def test_agreed_overdraft_allowance():
    assert OVERDRAFT_ALLOWANCE == 0, f"OVERDRAFT_ALLOWANCE should be 0 (strict), got {OVERDRAFT_ALLOWANCE}"


def test_default_bucket_uses_agreed_values():
    b = TokenBucket()
    assert b.capacity == 100
    assert b.refill_rate == 10.0
    assert b.overdraft_allowance == 0


def test_burst_ceiling_is_100():
    """With CAPACITY=100 and OVERDRAFT=0, a fresh bucket allows exactly 100 requests."""
    b = TokenBucket()
    allowed = sum(1 for _ in range(120) if b.consume())
    assert allowed == 100, f"expected 100 allowed requests from full bucket, got {allowed}"


def test_no_overdraft():
    """After draining, next consume must be denied (OVERDRAFT_ALLOWANCE=0)."""
    b = TokenBucket()
    for _ in range(100):
        b.consume()
    assert b.consume() is False, "overdraft should be disallowed (OVERDRAFT_ALLOWANCE=0)"
