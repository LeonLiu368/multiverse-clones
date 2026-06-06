# These cover the (working) money helpers and should stay GREEN.
from billing.money import format_cents, parse_dollars


def test_format_cents_basic():
    assert format_cents(12345) == "$123.45"
    assert format_cents(5) == "$0.05"
    assert format_cents(0) == "$0.00"


def test_format_cents_negative():
    assert format_cents(-2500) == "-$25.00"


def test_parse_dollars_roundtrip():
    for s, cents in [("$123.45", 12345), ("0.05", 5), ("$250", 25000), ("9.9", 990)]:
        assert parse_dollars(s) == cents
