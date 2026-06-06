# Canonical copy (restored by the verifier before grading).
from payments.serialization import dollars_to_cents, dumps_canonical


def test_dollars_to_cents():
    assert dollars_to_cents("12.50") == 1250
    assert dollars_to_cents("0.99") == 99
    assert dollars_to_cents("100") == 10000
    assert dollars_to_cents("0.005") == 1


def test_dumps_canonical_sorted():
    assert dumps_canonical({"b": 1, "a": 2}) == '{"a":2,"b":1}'
