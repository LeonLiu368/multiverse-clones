from __future__ import annotations

import json
import os
import select
import subprocess
from pathlib import Path
from typing import Any

from gauge.cli import mcp_server

from .helpers import TOKEN, TestServer


REPO = Path(__file__).resolve().parents[1]


def test_mcp_required_tools_registered() -> None:
    required = {
        "search_dashboards",
        "get_dashboard_by_uid",
        "get_dashboard_summary",
        "get_dashboard_property",
        "get_dashboard_panel_queries",
        "get_dashboard_variables",
        "run_dashboard_panel_query",
        "list_datasources",
        "get_datasource",
        "get_query_examples",
        "query_prometheus",
        "list_prometheus_metric_names",
        "list_prometheus_label_names",
        "list_prometheus_label_values",
        "query_loki_logs",
        "list_loki_label_names",
        "list_loki_label_values",
        "alerting_list_rules",
        "alerting_get_rule",
        "alerting_list_instances",
        "alerting_get_state_history",
        "generate_deeplink",
        "get_annotations",
        "create_annotation",
    }
    assert required == set(mcp_server.TOOLS)


def test_mcp_smoke_calls(monkeypatch) -> None:
    with TestServer() as server:
        monkeypatch.setenv("GRAFANA_URL", server.url)
        monkeypatch.setenv("GRAFANA_TOKEN", TOKEN)
        assert mcp_server.search_dashboards("payment")[0]["uid"] == "dash-payment-webhooks"
        assert mcp_server.get_dashboard_summary("dash-payment-webhooks")["panel_count"] == 2
        metric = mcp_server.query_prometheus('sum by (status_code)(increase(payment_gateway_responses_total{service="payments",route="webhook"}[5m]))', "prom-payments")
        assert metric["data"]["result"][0]["metric"]["status_code"] == "425"
        logs = mcp_server.query_loki_logs('{service="payments"} |= "lock_conflict"', "loki-payments")
        assert "lock_conflict" in logs["data"]["entries"][0]["line"]
        assert mcp_server.alerting_list_rules("firing")[0]["uid"] == "alert-payment-retry-burn"
        assert mcp_server.alerting_list_instances("firing")[0]["rule_uid"] == "alert-payment-retry-burn"
        assert mcp_server.alerting_get_state_history("alert-payment-retry-burn")[0]["to"] == "firing"
        assert mcp_server.get_dashboard_variables("dash-payment-webhooks")[0]["name"] == "service"
        panel = mcp_server.run_dashboard_panel_query("dash-payment-webhooks", 1, "10m")
        assert panel["result"]["data"]["result"][0]["values"] == [["2026-06-07T11:55:00Z", 31]]
        annotation = mcp_server.create_annotation("dash-payment-webhooks", "mcp smoke", 1, ["smoke"])
        assert annotation["text"] == "mcp smoke"


def test_mcp_disable_write_filters_write_tools() -> None:
    readonly = mcp_server.tool_set(disable_write=True)
    assert "create_annotation" not in readonly
    assert "search_dashboards" in readonly
    response = mcp_server._handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        readonly,
    )
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert "create_annotation" not in names
    blocked = mcp_server._handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "create_annotation", "arguments": {"dashboard_uid": "dash", "text": "nope"}},
        },
        readonly,
    )
    assert blocked["error"]["code"] == -32602


def test_mcp_grafana_subprocess_stdio_smoke() -> None:
    with TestServer() as server:
        session = McpSession(["bin/mcp-grafana"], server.url)
        try:
            init = session.request("initialize", {})
            assert init["result"]["serverInfo"]["name"] == "mcp-grafana"
            session.notify("notifications/initialized", {})

            listed = session.request("tools/list", {})
            names = {tool["name"] for tool in listed["result"]["tools"]}
            assert "search_dashboards" in names
            assert "create_annotation" in names

            called = session.request(
                "tools/call",
                {"name": "search_dashboards", "arguments": {"query": "payment"}},
            )
            payload = json.loads(called["result"]["content"][0]["text"])
            assert payload[0]["uid"] == "dash-payment-webhooks"
        finally:
            session.close()


def test_mcp_grafana_subprocess_disable_write_smoke() -> None:
    with TestServer() as server:
        session = McpSession(["bin/mcp-grafana", "--disable-write"], server.url)
        try:
            session.request("initialize", {})
            session.notify("notifications/initialized", {})
            listed = session.request("tools/list", {})
            names = {tool["name"] for tool in listed["result"]["tools"]}
            assert "search_dashboards" in names
            assert "create_annotation" not in names
        finally:
            session.close()


class McpSession:
    def __init__(self, command: list[str], server_url: str):
        env = os.environ.copy()
        env.update(
            {
                "GRAFANA_URL": server_url,
                "GRAFANA_TOKEN": TOKEN,
                "GAUGE_MCP_FORCE_FALLBACK": "1",
                "PYTHONPATH": str(REPO),
            }
        )
        self._next_id = 1
        self._stdout_buffer = b""
        self.process = subprocess.Popen(
            command,
            cwd=str(REPO),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        response = self._read()
        assert response.get("id") == request_id
        assert "error" not in response, response
        return response

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    def _write(self, message: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        body = json.dumps(message, separators=(",", ":")).encode("utf-8")
        self.process.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body)
        self.process.stdin.flush()

    def _read(self) -> dict[str, Any]:
        header_blob = self._read_until(b"\r\n\r\n").decode("utf-8")
        headers: dict[str, str] = {}
        for line_text in header_blob.split("\r\n"):
            if not line_text:
                continue
            key, _, value = line_text.partition(":")
            headers[key.lower()] = value.strip()
        length = int(headers["content-length"])
        payload = self._read_exact(length)
        return json.loads(payload.decode("utf-8"))

    def _read_until(self, marker: bytes) -> bytes:
        while marker not in self._stdout_buffer:
            self._fill_stdout()
        index = self._stdout_buffer.index(marker) + len(marker)
        payload = self._stdout_buffer[:index]
        self._stdout_buffer = self._stdout_buffer[index:]
        return payload

    def _read_exact(self, length: int) -> bytes:
        while len(self._stdout_buffer) < length:
            self._fill_stdout()
        payload = self._stdout_buffer[:length]
        self._stdout_buffer = self._stdout_buffer[length:]
        return payload

    def _fill_stdout(self) -> None:
        assert self.process.stdout is not None
        ready, _, _ = select.select([self.process.stdout.fileno()], [], [], 10)
        if not ready:
            self.close()
            raise AssertionError(f"timed out waiting for mcp-grafana response: {self._stderr()}")
        chunk = os.read(self.process.stdout.fileno(), 4096)
        if not chunk:
            raise AssertionError(f"mcp-grafana exited before response: {self._stderr()}")
        self._stdout_buffer += chunk

    def _stderr(self) -> str:
        if self.process.stderr is None:
            return ""
        data = self.process.stderr.read()
        return data.decode("utf-8", errors="replace")
