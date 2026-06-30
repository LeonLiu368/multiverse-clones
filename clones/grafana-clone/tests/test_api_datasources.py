from __future__ import annotations

from .test_api_dashboards import request
from .helpers import TestServer


def test_datasource_list_get_health_shape() -> None:
    with TestServer() as server:
        _, datasources = request(server.url, "/api/datasources")
        assert {item["uid"] for item in datasources} == {"prom-payments", "loki-payments"}
        _, datasource = request(server.url, "/api/datasources/uid/prom-payments")
        assert datasource["type"] == "prometheus"
        assert datasource["health"] == "ok"
