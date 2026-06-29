from __future__ import annotations

from .helpers import TestServer, api


def test_issue_events_latest_event_and_event_get() -> None:
    with TestServer() as server:
        events = api(server.url, "/api/0/issues/PAYMENTS-501/events/")[1]
        assert events[0]["id"] == "evt-1001-latest"
        latest = api(server.url, "/api/0/issues/PAYMENTS-501/events/latest/")[1]
        assert latest["exception"]["type"] == "RuntimeError"
        event = api(server.url, "/api/0/projects/acme/payments-api/events/evt-1001-latest/")[1]
        assert event["id"] == "evt-1001-latest"


def test_stacktrace_breadcrumb_and_tag_extraction_data() -> None:
    with TestServer() as server:
        latest = api(server.url, "/api/0/issues/PAYMENTS-501/events/latest/")[1]
        assert latest["stacktrace"]["frames"][0]["filename"] == "payments/retry_policy.py"
        assert latest["breadcrumbs"][0]["category"] == "gateway.response"
        issue = api(server.url, "/api/0/issues/PAYMENTS-501/")[1]
        assert issue["tags"]["error_type"] == "validation_conflict"
