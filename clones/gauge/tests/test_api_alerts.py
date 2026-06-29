from __future__ import annotations

from .helpers import TestServer
from .test_api_dashboards import request


def test_alert_rules_list_get_state_filtering() -> None:
    with TestServer() as server:
        _, firing = request(server.url, "/api/alert-rules?state=firing")
        assert len(firing) == 1
        assert firing[0]["uid"] == "alert-payment-retry-burn"
        _, rule = request(server.url, "/api/alert-rules/alert-payment-retry-burn")
        assert rule["state"] == "firing"
        _, instances = request(server.url, "/api/alert-instances?state=firing")
        assert instances[0]["rule_uid"] == "alert-payment-retry-burn"
        _, history = request(server.url, "/api/alert-rules/alert-payment-retry-burn/history")
        assert history[0]["to"] == "firing"
