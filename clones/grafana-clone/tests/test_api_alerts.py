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


def _get(url: str, path: str):
    import json, urllib.request
    from .helpers import TOKEN
    req = urllib.request.Request(url + path, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())


def test_real_grafana_alerting_paths() -> None:
    """Reliability: alert rules must be reachable at the REAL Grafana paths, not only the
    clone-native /api/alert-rules alias."""
    from .helpers import TestServer
    with TestServer() as server:
        prov = _get(server.url, "/api/v1/provisioning/alert-rules")
        assert isinstance(prov, list) and prov, "provisioning path must return rules"
        prom = _get(server.url, "/api/prometheus/grafana/api/v1/rules")
        assert prom["status"] == "success" and "groups" in prom["data"]
