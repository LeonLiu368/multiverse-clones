# HIDDEN grading test — never present in the agent's container during the run.
# Pins the exact SLO thresholds agreed in the #sre-oncall review.
import pytest
from budget.monitor import check_budget


@pytest.mark.parametrize("er,bcp,lat,want_status,want_page", [
    # critical: error_rate >= 0.05
    (0.05,  50.0,  100.0, "critical", True),
    (0.06,  50.0,  100.0, "critical", True),
    (0.10,  50.0,  100.0, "critical", True),
    # critical: budget_consumed > 90
    (0.0,   91.0,  100.0, "critical", True),
    (0.0,   99.0,  100.0, "critical", True),
    # warning: error_rate >= 0.01 (and < 0.05) and budget <= 90
    (0.01,  50.0,  100.0, "warning",  False),
    (0.02,  50.0,  100.0, "warning",  False),
    (0.04,  50.0,  100.0, "warning",  False),
    # warning + high latency -> page
    (0.01,  50.0, 1001.0, "warning",  True),
    (0.03,  50.0, 2000.0, "warning",  True),
    # warning: budget_consumed > 75
    (0.0,   76.0,  100.0, "warning",  False),
    (0.0,   80.0,  100.0, "warning",  False),
    # warning + high latency -> page
    (0.0,   76.0, 1500.0, "warning",  True),
    # ok
    (0.005, 50.0,  100.0, "ok",       False),
    (0.0,   30.0,  500.0, "ok",       False),
    # boundary: exactly at warning threshold with low latency -> no page
    (0.009, 75.0, 2000.0, "ok",       False),
    # boundary: latency exactly at threshold is NOT enough (>1000, not >=1000)
    (0.01,  50.0, 1000.0, "warning",  False),
    (0.01,  50.0, 1001.0, "warning",  True),
])
def test_check_budget_agreed_policy(er, bcp, lat, want_status, want_page):
    result = check_budget(er, bcp, lat)
    assert result["status"] == want_status, (
        f"check_budget({er}, {bcp}, {lat}) -> status={result['status']!r}, expected {want_status!r}"
    )
    assert result["should_page"] == want_page, (
        f"check_budget({er}, {bcp}, {lat}) -> should_page={result['should_page']}, expected {want_page}"
    )
