"""R6.2 parity tests: every capability reachable from the CLI (`gcx`) returns the same
underlying data as the matching MCP tool (`mcp-grafana`), proving R3.3.

Both are thin clients of one HTTP API. We run each against the SAME live in-process
server and assert byte-equal JSON (after normalizing ordering), so the CLI and MCP cannot
drift. These run by DEFAULT under `pytest` — no docker, no GAUGE_RUN_DOCKER_SMOKE gate.
"""
from __future__ import annotations

import json
import os
from typing import Any

import pytest

from gauge.cli import mcp_server
from tests.helpers import TOKEN, TestServer, json_out, run_gcx


def _canon(value: Any) -> Any:
    """Round-trip through JSON with sorted keys so dict ordering never matters."""
    return json.loads(json.dumps(value, sort_keys=True))


# (gcx argv, mcp tool name, mcp kwargs) for each parity-covered capability.
PARITY_CASES = [
    (["dashboards", "search", "payment"], "search_dashboards", {"query": "payment"}),
    (["dashboards", "get", "dash-payment-webhooks"], "get_dashboard_by_uid", {"uid": "dash-payment-webhooks"}),
    (["dashboards", "summary", "dash-payment-webhooks"], "get_dashboard_summary", {"uid": "dash-payment-webhooks"}),
    (["dashboards", "variables", "dash-payment-webhooks"], "get_dashboard_variables", {"uid": "dash-payment-webhooks"}),
    (["datasources", "list"], "list_datasources", {}),
    (["datasources", "get", "prom-payments"], "get_datasource", {"uid": "prom-payments"}),
    (
        ["metrics", "query", "-d", "prom-payments", 'sum by (status_code)(increase(payment_gateway_responses_total{service="payments"}[5m]))', "--since", "1h", "--step", "5m"],
        "query_prometheus",
        {"query": 'sum by (status_code)(increase(payment_gateway_responses_total{service="payments"}[5m]))', "datasource_uid": "prom-payments", "since": "1h", "step": "5m"},
    ),
    (
        ["logs", "query", "-d", "loki-payments", '{service="payments"} |= "lock_conflict"', "--since", "1h", "--limit", "100"],
        "query_loki_logs",
        {"query": '{service="payments"} |= "lock_conflict"', "datasource_uid": "loki-payments", "since": "1h", "limit": 100},
    ),
    (["alert", "rules", "list"], "alerting_list_rules", {}),
    (["alert", "rules", "get", "alert-payment-retry-burn"], "alerting_get_rule", {"uid": "alert-payment-retry-burn"}),
    (["alert", "instances", "list", "--state", "firing"], "alerting_list_instances", {"state": "firing"}),
    (["alert", "history", "alert-payment-retry-burn"], "alerting_get_state_history", {"rule_uid": "alert-payment-retry-burn"}),
    (["annotations", "list", "--dashboard", "dash-payment-webhooks"], "get_annotations", {"dashboard_uid": "dash-payment-webhooks"}),
]


@pytest.mark.parametrize("gcx_args, mcp_tool, mcp_kwargs", PARITY_CASES, ids=[c[1] for c in PARITY_CASES])
def test_cli_mcp_parity(gcx_args: list[str], mcp_tool: str, mcp_kwargs: dict[str, Any]) -> None:
    with TestServer() as server:
        cli_value = json_out(run_gcx(server.url, [*gcx_args, "--json"]))

        old = os.environ.get("GRAFANA_URL")
        old_sa = os.environ.get("GRAFANA_SERVICE_ACCOUNT_TOKEN")
        os.environ["GRAFANA_URL"] = server.url
        os.environ["GRAFANA_TOKEN"] = TOKEN
        os.environ.pop("GRAFANA_SERVICE_ACCOUNT_TOKEN", None)
        try:
            mcp_value = mcp_server.TOOLS[mcp_tool](**mcp_kwargs)
        finally:
            if old is None:
                os.environ.pop("GRAFANA_URL", None)
            else:
                os.environ["GRAFANA_URL"] = old
            if old_sa is not None:
                os.environ["GRAFANA_SERVICE_ACCOUNT_TOKEN"] = old_sa

        assert _canon(cli_value) == _canon(mcp_value), f"CLI vs MCP drift for {mcp_tool}"


def test_parity_write_read_roundtrip() -> None:
    """A CLI-created annotation is visible to the MCP read tool (one HTTP API, shared state)."""
    with TestServer() as server:
        created = json_out(
            run_gcx(
                server.url,
                ["annotations", "create", "--dashboard", "dash-payment-webhooks", "--panel", "1", "--text", "parity rt", "--tags", "parity", "--json"],
            )
        )
        assert created["id"] >= 1

        old = os.environ.get("GRAFANA_URL")
        os.environ["GRAFANA_URL"] = server.url
        os.environ["GRAFANA_TOKEN"] = TOKEN
        os.environ.pop("GRAFANA_SERVICE_ACCOUNT_TOKEN", None)
        try:
            via_mcp = mcp_server.TOOLS["get_annotations"](dashboard_uid="dash-payment-webhooks")
        finally:
            if old is None:
                os.environ.pop("GRAFANA_URL", None)
            else:
                os.environ["GRAFANA_URL"] = old

        texts = [a.get("text") for a in via_mcp]
        assert "parity rt" in texts


def test_mcp_disable_write_drops_create_only() -> None:
    """`--disable-write` removes exactly the write tool, leaving read parity intact (R3 control)."""
    full = set(mcp_server.tool_set(disable_write=False))
    ro = set(mcp_server.tool_set(disable_write=True))
    assert full - ro == {"create_annotation"}
    assert "search_dashboards" in ro
