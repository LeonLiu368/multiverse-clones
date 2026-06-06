# Invariant tests for should_page. They do NOT encode the agreed thresholds / consecutive-
# breach counts (those come from the incident postmortem). They currently FAIL (unimplemented).
import pytest

from monitoring.alerts import should_page


def test_returns_bool():
    assert isinstance(should_page(0.10, 5), bool)


@pytest.mark.parametrize("breaches", [0, 1, 3, 10])
def test_zero_error_rate_never_pages(breaches):
    assert should_page(0.0, breaches) is False


def test_monotonic_in_breaches():
    # If it pages at some breach count, it still pages with more consecutive breaches.
    for rate in (0.06, 0.30, 0.5):
        paged = False
        for b in range(0, 12):
            p = should_page(rate, b)
            if paged:
                assert p, (rate, b)
            paged = paged or p
