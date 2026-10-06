"""Tests for rolling-window utilities (should already pass)."""
from budget.window import rolling_error_rate, clamp


def test_zero_traffic_zero_error_rate():
    assert rolling_error_rate([], []) == 0.0


def test_all_success():
    assert rolling_error_rate([10, 20, 30], [0, 0, 0]) == 0.0


def test_all_failures():
    assert rolling_error_rate([0, 0], [5, 5]) == 1.0


def test_mixed():
    assert abs(rolling_error_rate([90], [10]) - 0.1) < 1e-9


def test_clamp_within():
    assert clamp(0.5, 0.0, 1.0) == 0.5


def test_clamp_low():
    assert clamp(-1.0, 0.0, 1.0) == 0.0


def test_clamp_high():
    assert clamp(2.0, 0.0, 1.0) == 1.0
