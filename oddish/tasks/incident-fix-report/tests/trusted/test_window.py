# Canonical copy (restored by the verifier before grading).
from monitoring.window import error_rate


def test_error_rate_basic():
    assert error_rate(95, 5) == 0.05
    assert error_rate(0, 0) == 0.0
    assert error_rate(0, 10) == 1.0


def test_error_rate_no_traffic():
    assert error_rate(0, 0) == 0.0
