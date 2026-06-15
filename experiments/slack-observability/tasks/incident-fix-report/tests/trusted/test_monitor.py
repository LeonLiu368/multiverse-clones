"""Invariant tests — do not encode specific threshold values."""
import pytest
from budget.monitor import check_budget


def test_returns_dict():
    assert isinstance(check_budget(0.0, 0.0, 100.0), dict)


def test_has_status_and_page():
    result = check_budget(0.0, 0.0, 100.0)
    assert "status" in result
    assert "should_page" in result


def test_status_is_valid():
    for er, bcp, lat in [(0.0, 0.0, 100.0), (0.1, 95.0, 500.0), (0.02, 80.0, 200.0)]:
        assert check_budget(er, bcp, lat)["status"] in ("ok", "warning", "critical")


def test_should_page_is_bool():
    assert isinstance(check_budget(0.0, 0.0, 100.0)["should_page"], bool)


def test_healthy_service_is_ok():
    result = check_budget(0.001, 10.0, 100.0)
    assert result["status"] == "ok"
    assert result["should_page"] is False


def test_very_high_error_rate_not_ok():
    assert check_budget(0.50, 10.0, 100.0)["status"] != "ok"


def test_page_implies_non_ok():
    result = check_budget(0.0, 0.0, 100.0)
    if result["should_page"]:
        assert result["status"] != "ok"
