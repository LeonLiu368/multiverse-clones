from __future__ import annotations

from .helpers import ADMIN_TOKEN, TestServer, api


def test_comments_activity_assignment_and_status_mutations() -> None:
    with TestServer() as server:
        status, comment = api(server.url, "/api/0/issues/PAYMENTS-501/comments/", method="POST", payload={"text": "Investigated in PR #1"})
        assert status == 201
        assert comment["text"] == "Investigated in PR #1"
        assigned = api(server.url, "/api/0/issues/PAYMENTS-501/", method="PUT", payload={"assignedTo": {"type": "team", "slug": "payments"}})[1]
        assert assigned["assignedTo"]["slug"] == "payments"
        resolved = api(server.url, "/api/0/issues/PAYMENTS-501/", method="PUT", payload={"status": "resolved", "resolvedInRelease": "payments-api@2026.06.07.2"})[1]
        assert resolved["status"] == "resolved"
        ignored = api(server.url, "/api/0/issues/PAYMENTS-501/", method="PUT", payload={"status": "ignored", "ignoreReason": "not actionable"})[1]
        assert ignored["status"] == "ignored"
        reopened = api(server.url, "/api/0/issues/PAYMENTS-501/", method="PUT", payload={"status": "unresolved"})[1]
        assert reopened["status"] == "unresolved"
        activity = api(server.url, "/api/0/issues/PAYMENTS-501/activity/")[1]
        assert [item["type"] for item in activity] == ["comment", "assign", "resolve", "ignore", "reopen"]
        mutations = api(server.url, "/api/_clone/mutations", token=ADMIN_TOKEN)[1]
        assert [item["action"] for item in mutations] == ["issue.comment", "issue.assign", "issue.resolve", "issue.ignore", "issue.reopen"]
        assert mutations[-1]["before"]["status"] == "ignored"
