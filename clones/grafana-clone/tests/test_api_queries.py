from __future__ import annotations

import json
import urllib.request

from .helpers import TOKEN, TestServer


def post(url: str, payload: dict):
    req = urllib.request.Request(
        url + "/api/ds/query",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def first_data(response):
    return response["results"]["A"]["data"]


def test_metric_query_exact_match() -> None:
    with TestServer() as server:
        data = first_data(
            post(
                server.url,
                {
                    "queries": [
                        {
                            "refId": "A",
                            "queryType": "metrics",
                            "datasource": {"uid": "prom-payments"},
                            "expr": 'sum by (status_code)(increase(payment_gateway_responses_total{service="payments",route="webhook"}[5m]))',
                        }
                    ]
                },
            )
        )
        assert data["match"] == "exact"
        assert data["data"]["result"][0]["metric"]["status_code"] == "425"


def test_metric_query_normalized_match() -> None:
    with TestServer() as server:
        data = first_data(
            post(
                server.url,
                {
                    "queries": [
                        {
                            "refId": "A",
                            "queryType": "metrics",
                            "expr": 'sum by ( status_code ) ( increase ( payment_gateway_responses_total{ route = "webhook", service = "payments" } [ 5m ] ) )',
                        }
                    ]
                },
            )
        )
        assert data["match"] == "normalized"


def test_metric_labels_and_values() -> None:
    with TestServer() as server:
        labels = first_data(post(server.url, {"queries": [{"refId": "A", "queryType": "metric_labels"}]}))
        assert "status_code" in labels["labels"]
        values = first_data(post(server.url, {"queries": [{"refId": "A", "queryType": "metric_label_values", "label": "status_code"}]}))
        assert values["values"] == ["409", "425"]


def test_metric_time_filtering() -> None:
    expr = 'sum by (status_code)(increase(payment_gateway_responses_total{service="payments",route="webhook"}[5m]))'
    with TestServer() as server:
        included = first_data(post(server.url, {"queries": [{"refId": "A", "queryType": "metrics", "expr": expr, "since": "10m"}]}))
        assert included["data"]["result"][0]["values"] == [["2026-06-07T11:55:00Z", 31]]
        excluded = first_data(
            post(server.url, {"queries": [{"refId": "A", "queryType": "metrics", "expr": expr, "from": "2026-06-07T11:56:00Z", "to": "2026-06-07T12:00:00Z"}]})
        )
        assert excluded["data"]["result"][0]["values"] == []


def test_log_query_exact_and_simple_filter() -> None:
    with TestServer() as server:
        exact = first_data(post(server.url, {"queries": [{"refId": "A", "queryType": "logs", "expr": '{service="payments"} |= "lock_conflict"'}]}))
        assert exact["match"] == "exact"
        filtered = first_data(post(server.url, {"queries": [{"refId": "A", "queryType": "logs", "expr": '{service="payments",level="warn"} |= "retry"'}]}))
        assert filtered["data"]["entries"][0]["line"].startswith("retry scheduled")


def test_log_time_filtering() -> None:
    with TestServer() as server:
        excluded = first_data(
            post(
                server.url,
                {
                    "queries": [
                        {
                            "refId": "A",
                            "queryType": "logs",
                            "expr": '{service="payments"} |= "lock_conflict"',
                            "from": "2026-06-07T11:58:00Z",
                            "to": "2026-06-07T12:00:00Z",
                        }
                    ]
                },
            )
        )
        assert excluded["data"]["entries"] == []


def test_log_labels_and_values() -> None:
    with TestServer() as server:
        labels = first_data(post(server.url, {"queries": [{"refId": "A", "queryType": "log_labels"}]}))
        assert labels["labels"] == ["level", "service"]
        values = first_data(post(server.url, {"queries": [{"refId": "A", "queryType": "log_label_values", "label": "level"}]}))
        assert values["values"] == ["warn"]


def test_ds_query_returns_real_grafana_frames() -> None:
    """Reliability: /api/ds/query must populate real Grafana dataframes (schema.fields +
    data.values), not just the clone-native `data` block."""
    with TestServer() as server:
        resp = post(
            server.url,
            {
                "queries": [
                    {
                        "refId": "A",
                        "queryType": "metrics",
                        "datasource": {"uid": "prom-payments"},
                        "expr": 'sum by (status_code)(increase(payment_gateway_responses_total{service="payments",route="webhook"}[5m]))',
                    }
                ]
            },
        )
        frames = resp["results"]["A"]["frames"]
        assert frames, "frames must be populated"
        fields = frames[0]["schema"]["fields"]
        assert [f["name"] for f in fields][0] == "Time" and fields[0]["type"] == "time"
        # data.values is column-oriented: [times, values]
        times, values = frames[0]["data"]["values"]
        assert len(times) == len(values) and times and values
        # native data block still present (back-compat for gcx/mcp)
        assert resp["results"]["A"]["data"]["data"]["result"]
