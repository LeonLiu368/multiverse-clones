from __future__ import annotations

from .helpers import TestServer, api, fresh_state


def test_absent_query_defaults_to_unresolved() -> None:
    # Real Sentry: omitting `query` entirely means `is:unresolved`, so a listing
    # without a query must exclude the resolved PAYMENTS-487 issue.
    with TestServer() as server:
        status, issues = api(server.url, "/api/0/projects/acme/payments-api/issues/")
        assert status == 200
        short_ids = {item["shortId"] for item in issues}
        assert short_ids == {"PAYMENTS-501"}
        assert all(item["status"] == "unresolved" for item in issues)

        # An explicit empty query broadens back to all issues (honored as-is).
        status, all_issues = api(server.url, "/api/0/projects/acme/payments-api/issues/?query=")
        assert status == 200
        assert {item["shortId"] for item in all_issues} == {"PAYMENTS-501", "PAYMENTS-487"}


def test_sort_freq_orders_by_numeric_count_desc() -> None:
    # Seed two unresolved issues with counts where lexicographic order would be
    # wrong (9 > 100 as strings) to prove the sort is numeric.
    state = fresh_state()
    for issue in state["issues"]:
        issue["status"] = "unresolved"
        issue["substatus"] = "ongoing"
    state["issues"][0]["count"] = 9      # PAYMENTS-501
    state["issues"][1]["count"] = 100    # PAYMENTS-487
    with TestServer(state=state) as server:
        # `freq` is the real Sentry alias for sort=events.
        status, issues = api(server.url, "/api/0/projects/acme/payments-api/issues/?query=&sort=freq")
        assert status == 200
        counts = [item["count"] for item in issues]
        assert counts == [100, 9]
        assert issues[0]["shortId"] == "PAYMENTS-487"


def test_project_and_org_issue_listing_query_and_sorting() -> None:
    with TestServer() as server:
        status, project_issues = api(server.url, "/api/0/projects/acme/payments-api/issues/?query=is:unresolved%20error_type:validation_conflict&sort=lastSeen")
        assert status == 200
        assert [item["shortId"] for item in project_issues] == ["PAYMENTS-501"]
        status, org_issues = api(server.url, "/api/0/organizations/acme/issues/?query=is:resolved%20project:payments-api&sort=users")
        assert status == 200
        assert org_issues[0]["shortId"] == "PAYMENTS-487"


def test_issue_get_by_numeric_and_short_id() -> None:
    with TestServer() as server:
        assert api(server.url, "/api/0/issues/1001/")[1]["shortId"] == "PAYMENTS-501"
        assert api(server.url, "/api/0/issues/PAYMENTS-501/")[1]["id"] == "1001"


def test_suspect_commits_and_ownership_rules() -> None:
    with TestServer() as server:
        commits = api(server.url, "/api/0/issues/PAYMENTS-501/suspect-commits/")[1]
        assert commits[0]["id"] == "abc1234"
        rules = api(server.url, "/api/0/projects/acme/payments-api/ownership/")[1]
        assert rules[0]["owner"] == "team:payments"
