from __future__ import annotations

import inspect
import json
import os
import sys
import argparse
from typing import Any, Callable

from gauge.server import links

from .client import GaugeClient


def _client() -> GaugeClient:
    return GaugeClient()


def search_dashboards(query: str = "") -> list[dict[str, Any]]:
    """Search dashboards by title, tag, folder, or uid."""
    return _client().search_dashboards(query)


def get_dashboard_by_uid(uid: str) -> dict[str, Any]:
    """Get a full dashboard by uid."""
    return _client().dashboard(uid)


def get_dashboard_summary(uid: str) -> dict[str, Any]:
    """Get a compact dashboard summary."""
    return _client().dashboard_summary(uid)


def get_dashboard_property(uid: str, property: str) -> Any:
    """Get a top-level dashboard property such as title, tags, or panels."""
    dashboard = _client().dashboard(uid).get("dashboard", {})
    current: Any = dashboard
    for part in property.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def get_dashboard_panel_queries(uid: str) -> list[dict[str, Any]]:
    """List panel query expressions for a dashboard."""
    panels = _client().dashboard_panels(uid)
    return [
        {
            "panel_id": panel.get("id"),
            "panel_title": panel.get("title"),
            "datasource_uid": panel.get("datasource_uid"),
            "query": panel.get("query"),
        }
        for panel in panels
    ]


def list_datasources() -> list[dict[str, Any]]:
    """List configured datasources."""
    return _client().datasources()


def get_datasource(uid: str) -> dict[str, Any]:
    """Get a datasource by uid."""
    return _client().datasource(uid)


def get_query_examples(datasource_uid: str | None = None) -> list[dict[str, Any]]:
    """Return panel query examples from dashboards."""
    examples = []
    for dashboard in _client().search_dashboards():
        summary = _client().dashboard_summary(str(dashboard["uid"]))
        for panel in summary.get("panels", []):
            if datasource_uid and panel.get("datasource_uid") != datasource_uid:
                continue
            examples.append(
                {
                    "dashboard_uid": dashboard["uid"],
                    "panel_id": panel.get("id"),
                    "datasource_uid": panel.get("datasource_uid"),
                    "query": panel.get("query"),
                }
            )
    return examples


def query_prometheus(query: str, datasource_uid: str | None = None, since: str = "1h", step: str = "5m") -> dict[str, Any]:
    """Run a Prometheus-style query."""
    return _client().query_metrics(query, datasource_uid, since, step)


def list_prometheus_metric_names(datasource_uid: str | None = None) -> dict[str, Any]:
    """List discovered Prometheus metric names."""
    return _client().metric_names(datasource_uid)


def list_prometheus_label_names(datasource_uid: str | None = None) -> dict[str, Any]:
    """List discovered Prometheus label names."""
    return _client().metric_labels(datasource_uid)


def list_prometheus_label_values(label: str, datasource_uid: str | None = None) -> dict[str, Any]:
    """List values for a Prometheus label."""
    return _client().metric_label_values(label, datasource_uid)


def query_loki_logs(query: str, datasource_uid: str | None = None, since: str = "1h", limit: int = 100) -> dict[str, Any]:
    """Run a Loki-style log query."""
    return _client().query_logs(query, datasource_uid, since, limit)


def list_loki_label_names(datasource_uid: str | None = None) -> dict[str, Any]:
    """List discovered Loki label names."""
    return _client().log_labels(datasource_uid)


def list_loki_label_values(label: str, datasource_uid: str | None = None) -> dict[str, Any]:
    """List values for a Loki label."""
    return _client().log_label_values(label, datasource_uid)


def alerting_list_rules(state: str | None = None) -> list[dict[str, Any]]:
    """List alert rules, optionally filtered by state."""
    return _client().alert_rules(state)


def alerting_get_rule(uid: str) -> dict[str, Any]:
    """Get an alert rule by uid."""
    return _client().alert_rule(uid)


def alerting_list_instances(state: str | None = None) -> list[dict[str, Any]]:
    """List alert instances, optionally filtered by state."""
    return _client().alert_instances(state)


def alerting_get_state_history(rule_uid: str) -> list[dict[str, Any]]:
    """Get state history for an alert rule."""
    return _client().alert_history(rule_uid)


def generate_deeplink(
    kind: str,
    uid: str | None = None,
    panel_id: int | None = None,
    datasource_uid: str | None = None,
    query: str | None = None,
    from_range: str | None = None,
    to_range: str | None = None,
) -> dict[str, str]:
    """Generate dashboard, panel, or explore deeplinks."""
    base_url = _client().base_url
    if kind == "explore":
        if not datasource_uid or query is None:
            raise ValueError("datasource_uid and query are required for explore links")
        return links.explore_link(base_url, datasource_uid, query)
    if not uid:
        raise ValueError("uid is required for dashboard and panel links")
    dashboard = _client().dashboard(uid).get("dashboard", {})
    if kind == "panel":
        if panel_id is None:
            raise ValueError("panel_id is required for panel links")
        return links.panel_link(base_url, dashboard, panel_id, from_range, to_range)
    return links.dashboard_link(base_url, dashboard)


def get_annotations(dashboard_uid: str | None = None, tags: str | None = None) -> list[dict[str, Any]]:
    """List annotations."""
    return _client().annotations(dashboard_uid, tags)


def get_dashboard_variables(uid: str) -> list[dict[str, Any]]:
    """Get dashboard templating variables."""
    return _client().dashboard_variables(uid)


def run_dashboard_panel_query(
    dashboard_uid: str,
    panel_id: int,
    since: str = "1h",
    from_time: str | None = None,
    to_time: str | None = None,
) -> dict[str, Any]:
    """Run the query configured on a dashboard panel."""
    return _client().query_dashboard_panel(dashboard_uid, panel_id, since, from_time, to_time)


def create_annotation(dashboard_uid: str, text: str, panel_id: int | None = None, tags: list[str] | None = None) -> dict[str, Any]:
    """Create an annotation."""
    return _client().create_annotation(dashboard_uid, text, panel_id, tags)


TOOL_NAMES = {
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

WRITE_TOOLS = {"create_annotation"}


TOOLS: dict[str, Callable[..., Any]] = {
    name: obj
    for name, obj in list(globals().items())
    if callable(obj) and not name.startswith("_") and name in TOOL_NAMES
}


def tool_set(disable_write: bool = False) -> dict[str, Callable[..., Any]]:
    if not disable_write:
        return dict(TOOLS)
    return {name: tool for name, tool in TOOLS.items() if name not in WRITE_TOOLS}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mcp-grafana")
    parser.add_argument("--disable-write", action="store_true", help="disable MCP write tools")
    args = parser.parse_args(argv)
    tools = tool_set(disable_write=args.disable_write)
    if os.environ.get("GAUGE_MCP_FORCE_FALLBACK") == "1":
        _run_fallback_mcp(tools)
        return
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        _run_fallback_mcp(tools)
        return

    mcp = FastMCP("gauge-grafana")
    for func in tools.values():
        mcp.tool()(func)
    mcp.run(transport="stdio")


def _run_fallback_mcp(tools: dict[str, Callable[..., Any]] | None = None) -> None:
    active_tools = tools or TOOLS
    while True:
        message = _read_message(sys.stdin.buffer)
        if message is None:
            return
        response = _handle_message(message, active_tools)
        if response is not None:
            _write_message(sys.stdout.buffer, response)


def _handle_message(message: dict[str, Any], tools: dict[str, Callable[..., Any]] | None = None) -> dict[str, Any] | None:
    active_tools = tools or TOOLS
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "mcp-grafana", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": [_tool_descriptor(name, func) for name, func in active_tools.items()]}}
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in active_tools:
            return _rpc_error(request_id, -32602, f"unknown tool: {name}")
        try:
            result = active_tools[str(name)](**arguments)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, sort_keys=True)}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return _rpc_error(request_id, -32000, str(exc))
    if request_id is None:
        return None
    return _rpc_error(request_id, -32601, f"unsupported method: {method}")


def _tool_descriptor(name: str, func: Callable[..., Any]) -> dict[str, Any]:
    signature = inspect.signature(func)
    properties = {}
    required = []
    for param_name, param in signature.parameters.items():
        annotation = "string"
        if param.annotation is int:
            annotation = "integer"
        elif param.annotation in (list[str], list):
            annotation = "array"
        properties[param_name] = {"type": annotation}
        if param.default is inspect.Signature.empty:
            required.append(param_name)
    return {
        "name": name,
        "description": inspect.getdoc(func) or name,
        "inputSchema": {"type": "object", "properties": properties, "required": required},
    }


def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _read_message(stream: Any) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        line_text = line.decode("utf-8").strip()
        if not line_text:
            break
        key, _, value = line_text.partition(":")
        headers[key.lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    return json.loads(stream.read(length).decode("utf-8"))


def _write_message(stream: Any, message: dict[str, Any]) -> None:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body)
    stream.flush()


if __name__ == "__main__":
    main()
