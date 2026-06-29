from __future__ import annotations

from gauge.cli.client import GaugeClient

from .helpers import TestServer, json_out, run_gcx


def test_gcx_smoke_all_command_groups() -> None:
    with TestServer() as server:
        commands = [
            ["config", "check", "--json"],
            ["whoami", "--json"],
            ["dashboards", "list", "--json"],
            ["dashboards", "search", "payment", "--json"],
            ["dashboards", "get", "dash-payment-webhooks", "--json"],
            ["dashboards", "summary", "dash-payment-webhooks", "--json"],
            ["dashboards", "panels", "dash-payment-webhooks", "--json"],
            ["dashboards", "query-panel", "dash-payment-webhooks", "1", "--since", "10m", "--json"],
            ["dashboards", "variables", "dash-payment-webhooks", "--json"],
            ["datasources", "list", "--json"],
            ["datasources", "get", "prom-payments", "--json"],
            ["datasources", "health", "prom-payments", "--json"],
            ["metrics", "query", "-d", "prom-payments", 'sum by (status_code)(increase(payment_gateway_responses_total{service="payments",route="webhook"}[5m]))', "--since", "1h", "--step", "5m", "--json"],
            ["metrics", "labels", "-d", "prom-payments", "--json"],
            ["metrics", "label-values", "-d", "prom-payments", "status_code", "--json"],
            ["logs", "query", "-d", "loki-payments", '{service="payments"} |= "lock_conflict"', "--since", "1h", "--limit", "20", "--json"],
            ["logs", "labels", "-d", "loki-payments", "--json"],
            ["logs", "label-values", "-d", "loki-payments", "level", "--json"],
            ["alert", "rules", "list", "--state", "firing", "--json"],
            ["alert", "rules", "get", "alert-payment-retry-burn", "--json"],
            ["alert", "instances", "list", "--state", "firing", "--json"],
            ["alert", "history", "alert-payment-retry-burn", "--json"],
            ["annotations", "list", "--dashboard", "dash-payment-webhooks", "--json"],
            ["annotations", "create", "--dashboard", "dash-payment-webhooks", "--panel", "1", "--text", "cli smoke", "--tags", "smoke,CLI", "--json"],
            ["links", "dashboard", "dash-payment-webhooks", "--json"],
            ["links", "panel", "dash-payment-webhooks", "1", "--from", "now-1h", "--to", "now", "--json"],
            ["links", "explore", "-d", "prom-payments", "--query", "up", "--json"],
        ]
        for command in commands:
            result = run_gcx(server.url, command)
            assert result.returncode == 0, command + [result.stderr]
            assert result.stdout.strip().startswith("{") or result.stdout.strip().startswith("[")
        assert json_out(run_gcx(server.url, ["alert", "rules", "list", "--state", "firing", "--json"]))[0]["state"] == "firing"


def test_gcx_accepts_grafana_url_and_server_alias() -> None:
    with TestServer() as server:
        assert json_out(run_gcx(server.url, ["whoami", "--json"]))["login"] == "agent"
        assert json_out(run_gcx(server.url, ["whoami", "--json"], use_server_alias=True))["login"] == "agent"


def test_grafana_url_precedes_grafana_server(monkeypatch) -> None:
    monkeypatch.setenv("GRAFANA_URL", "http://url.example")
    monkeypatch.setenv("GRAFANA_SERVER", "http://server.example")
    assert GaugeClient().base_url == "http://url.example"
