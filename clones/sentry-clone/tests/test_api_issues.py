from __future__ import annotations

from .helpers import TestServer, api


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
