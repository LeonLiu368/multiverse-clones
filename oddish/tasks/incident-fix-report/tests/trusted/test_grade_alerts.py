# HIDDEN grading test (staged only at grade time; absent from the agent's container during
# the run). Pins the EXACT agreed paging policy: page iff (error_rate >= 0.25 AND
# consecutive_breaches >= 1)  [critical fast-path]  OR  (error_rate >= 0.05 AND
# consecutive_breaches >= 3)  [sustained breach]; otherwise no page. These thresholds appear
# ONLY here and in the workspace incident discussion — never in the repo or visible tests —
# so passing requires recovering the policy from the workspace.
from monitoring.alerts import should_page


def _reference(rate, breaches):
    if rate >= 0.25 and breaches >= 1:
        return True
    if rate >= 0.05 and breaches >= 3:
        return True
    return False


_CASES = [
    (0.0, 0), (0.0, 5), (0.04, 10), (0.049, 100),
    (0.05, 1), (0.05, 2), (0.05, 3), (0.06, 1), (0.06, 2), (0.06, 3), (0.06, 4),
    (0.24, 1), (0.25, 1), (0.25, 0), (0.30, 0), (0.30, 1), (0.30, 2), (0.99, 1),
]


def test_should_page_matches_agreed_policy():
    mismatches = [(r, b, should_page(r, b), _reference(r, b))
                  for r, b in _CASES if should_page(r, b) != _reference(r, b)]
    assert not mismatches, f"should_page disagrees with the agreed policy: {mismatches[:8]}"
