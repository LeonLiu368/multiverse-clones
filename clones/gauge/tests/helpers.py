from __future__ import annotations

import copy
import json
import os
import socket
import subprocess
import sys
import threading
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from gauge.server.app import make_handler
from gauge.server.state import GaugeStore


TOKEN = "test-token-acme-eval"
ADMIN_TOKEN = "test-admin-token-acme-eval"


BASE_STATE: dict[str, Any] = {
    "meta": {"workspace": "acme", "now": "2026-06-07T12:00:00Z"},
    "users": [{"id": 1, "login": "agent", "name": "Agent User", "role": "Editor"}],
    "datasources": [
        {"uid": "prom-payments", "name": "Payments Prometheus", "type": "prometheus", "mode": "embedded", "health": "ok"},
        {"uid": "loki-payments", "name": "Payments Loki", "type": "loki", "mode": "embedded", "health": "ok"},
    ],
    "dashboards": [
        {
            "uid": "dash-payment-webhooks",
            "title": "Payment Webhook Reliability",
            "folder": "Payments",
            "tags": ["payments", "webhooks", "oncall"],
            "variables": [
                {"name": "service", "label": "Service", "query": "payments", "current": {"text": "payments", "value": "payments"}}
            ],
            "panels": [
                {
                    "id": 1,
                    "title": "Gateway responses by status",
                    "type": "timeseries",
                    "datasource_uid": "prom-payments",
                    "query": "sum by (status_code)(increase(payment_gateway_responses_total{service=\"payments\"}[5m]))",
                },
                {
                    "id": 2,
                    "title": "Payment lock conflict logs",
                    "type": "logs",
                    "datasource_uid": "loki-payments",
                    "query": "{service=\"payments\"} |= \"lock_conflict\"",
                },
            ],
        }
    ],
    "alerts": [
        {
            "uid": "alert-payment-retry-burn",
            "name": "Payment webhook retry error budget burn",
            "state": "firing",
            "health": "ok",
            "dashboard_uid": "dash-payment-webhooks",
            "panel_id": 1,
            "query": "sum(rate(payment_webhook_failures_total[5m]))",
            "labels": {"service": "payments", "severity": "page"},
        },
        {
            "uid": "alert-payment-ok",
            "name": "Payment webhook ok",
            "state": "normal",
            "health": "ok",
            "dashboard_uid": "dash-payment-webhooks",
            "panel_id": 1,
            "query": "sum(rate(payment_webhook_success_total[5m]))",
            "labels": {"service": "payments"},
        },
    ],
    "metrics": {
        "queries": {
            "sum by (status_code)(increase(payment_gateway_responses_total{service=\"payments\"}[5m]))": {
                "resultType": "matrix",
                "series": [
                    {
                        "metric": {"status_code": "425"},
                        "values": [["2026-06-07T10:00:00Z", 3], ["2026-06-07T11:55:00Z", 31]],
                    },
                    {"metric": {"status_code": "409"}, "values": [["2026-06-07T11:55:00Z", 18]]},
                ],
            },
            "sum by (status_code)(increase(payment_gateway_responses_total{service=\"payments\",route=\"webhook\"}[5m]))": {
                "resultType": "matrix",
                "series": [
                    {
                        "metric": {"status_code": "425", "service": "payments"},
                        "values": [["2026-06-07T10:00:00Z", 3], ["2026-06-07T11:55:00Z", 31]],
                    },
                    {"metric": {"status_code": "409", "service": "payments"}, "values": [["2026-06-07T11:55:00Z", 18]]},
                ],
            },
            "sum(rate(payment_webhook_failures_total[5m]))": {
                "resultType": "matrix",
                "series": [{"metric": {"service": "payments"}, "values": [["2026-06-07T11:55:00Z", 0.12]]}],
            },
        }
    },
    "logs": {
        "queries": {
            "{service=\"payments\"} |= \"lock_conflict\"": {
                "entries": [
                    {
                        "ts": "2026-06-07T11:57:10Z",
                        "labels": {"service": "payments", "level": "warn"},
                        "line": "gateway 409 lock_conflict idempotent=true event=evt_001",
                    }
                ]
            },
            "{service=\"payments\",level=\"warn\"} |= \"retry\"": {
                "entries": [
                    {
                        "ts": "2026-06-07T11:58:02Z",
                        "labels": {"service": "payments", "level": "warn"},
                        "line": "retry scheduled for lock_conflict event=evt_001 delay_ms=250",
                    }
                ]
            },
        }
    },
    "alert_instances": [
        {
            "uid": "inst-payment-retry-burn-payments-page",
            "rule_uid": "alert-payment-retry-burn",
            "state": "firing",
            "labels": {"service": "payments", "severity": "page"},
            "startsAt": "2026-06-07T11:54:00Z",
        },
        {
            "uid": "inst-payment-ok",
            "rule_uid": "alert-payment-ok",
            "state": "normal",
            "labels": {"service": "payments"},
            "startsAt": "2026-06-07T11:00:00Z",
        },
    ],
    "alert_state_history": [
        {
            "rule_uid": "alert-payment-retry-burn",
            "from": "normal",
            "to": "firing",
            "ts": "2026-06-07T11:54:00Z",
            "reason": "retry burn crossed page threshold",
        }
    ],
    "annotations": [],
    "mutation_log": [],
}


def fresh_state() -> dict[str, Any]:
    return copy.deepcopy(BASE_STATE)


class TestServer:
    __test__ = False

    def __init__(self, state: dict[str, Any] | None = None):
        self.store = GaugeStore(state or fresh_state())
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.store))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self._old_env: dict[str, str | None] = {}

    def __enter__(self) -> "TestServer":
        self._set_env("GAUGE_ENABLE_ADMIN_API", "1")
        self._set_env("GAUGE_ADMIN_TOKEN", ADMIN_TOKEN)
        self.thread.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _set_env(self, key: str, value: str) -> None:
        if key not in self._old_env:
            self._old_env[key] = os.environ.get(key)
        os.environ[key] = value


def run_gcx(server_url: str, args: list[str], use_server_alias: bool = False) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update({"GRAFANA_TOKEN": TOKEN, "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
    if use_server_alias:
        env.pop("GRAFANA_URL", None)
        env["GRAFANA_SERVER"] = server_url
    else:
        env["GRAFANA_URL"] = server_url
    return subprocess.run([sys.executable, "-m", "gauge.cli.gcx", *args], env=env, text=True, capture_output=True, timeout=15)


def json_out(result: subprocess.CompletedProcess[str]) -> Any:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)
