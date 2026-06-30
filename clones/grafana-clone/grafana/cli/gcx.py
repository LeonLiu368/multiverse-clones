from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Callable

from grafana.server import links

from .client import (
    AuthConfigError,
    BackendUnavailableError,
    GrafanaClient,
    GrafanaClientError,
    NotFoundError,
    UnsupportedCommandError,
)
from .output import emit_json, emit_table, error


class GrafanaArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def _strip_json(argv: list[str]) -> tuple[list[str], bool]:
    as_json = "--json" in argv
    return [arg for arg in argv if arg != "--json"], as_json


def _client() -> GrafanaClient:
    return GrafanaClient()


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    args_without_json, as_json = _strip_json(raw)
    parser = build_parser()
    args = parser.parse_args(args_without_json)
    setattr(args, "json", as_json)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 0
    try:
        value = args.handler(args)
    except (NotFoundError, AuthConfigError, BackendUnavailableError, UnsupportedCommandError, GrafanaClientError) as exc:
        error(str(exc))
        return getattr(exc, "exit_code", 1)
    except KeyboardInterrupt:
        return 1
    if as_json:
        emit_json(value)
    else:
        emit_table(value)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = GrafanaArgumentParser(prog="gcx", description="Grafana-compatible Grafana command-line tool")
    parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="group")

    config = sub.add_parser("config", help="configuration commands")
    config_sub = config.add_subparsers(dest="config_cmd", required=True)
    config_sub.add_parser("check").set_defaults(handler=lambda _args: _client().config_check())

    sub.add_parser("whoami", help="show authenticated user").set_defaults(handler=lambda _args: _client().user())

    dashboards = sub.add_parser("dashboards", help="dashboard commands")
    dash_sub = dashboards.add_subparsers(dest="dashboards_cmd", required=True)
    dash_sub.add_parser("list").set_defaults(handler=lambda _args: _client().search_dashboards())
    dash_search = dash_sub.add_parser("search")
    dash_search.add_argument("query")
    dash_search.set_defaults(handler=lambda args: _client().search_dashboards(args.query))
    dash_get = dash_sub.add_parser("get")
    dash_get.add_argument("uid")
    dash_get.set_defaults(handler=lambda args: _client().dashboard(args.uid))
    dash_summary = dash_sub.add_parser("summary")
    dash_summary.add_argument("uid")
    dash_summary.set_defaults(handler=lambda args: _client().dashboard_summary(args.uid))
    dash_panels = dash_sub.add_parser("panels")
    dash_panels.add_argument("uid")
    dash_panels.set_defaults(handler=lambda args: _client().dashboard_panels(args.uid))
    dash_query_panel = dash_sub.add_parser("query-panel")
    dash_query_panel.add_argument("uid")
    dash_query_panel.add_argument("panel_id", type=int)
    dash_query_panel.add_argument("--since", default="1h")
    dash_query_panel.add_argument("--from", dest="from_time")
    dash_query_panel.add_argument("--to", dest="to_time")
    dash_query_panel.set_defaults(
        handler=lambda args: _client().query_dashboard_panel(args.uid, args.panel_id, args.since, args.from_time, args.to_time)
    )
    dash_variables = dash_sub.add_parser("variables")
    dash_variables.add_argument("uid")
    dash_variables.set_defaults(handler=lambda args: _client().dashboard_variables(args.uid))

    datasources = sub.add_parser("datasources", help="datasource commands")
    ds_sub = datasources.add_subparsers(dest="datasources_cmd", required=True)
    ds_sub.add_parser("list").set_defaults(handler=lambda _args: _client().datasources())
    ds_get = ds_sub.add_parser("get")
    ds_get.add_argument("uid")
    ds_get.set_defaults(handler=lambda args: _client().datasource(args.uid))
    ds_health = ds_sub.add_parser("health")
    ds_health.add_argument("uid")
    ds_health.set_defaults(handler=lambda args: _client().datasource_health(args.uid))

    metrics = sub.add_parser("metrics", help="Prometheus-style metric commands")
    metrics_sub = metrics.add_subparsers(dest="metrics_cmd", required=True)
    metrics_query = metrics_sub.add_parser("query")
    metrics_query.add_argument("-d", "--datasource", dest="datasource_uid")
    metrics_query.add_argument("expr")
    metrics_query.add_argument("--since", default="1h")
    metrics_query.add_argument("--step", default="5m")
    metrics_query.add_argument("--from", dest="from_time")
    metrics_query.add_argument("--to", dest="to_time")
    metrics_query.set_defaults(
        handler=lambda args: _client().query_metrics(args.expr, args.datasource_uid, args.since, args.step, args.from_time, args.to_time)
    )
    metrics_labels = metrics_sub.add_parser("labels")
    metrics_labels.add_argument("-d", "--datasource", dest="datasource_uid")
    metrics_labels.set_defaults(handler=lambda args: _client().metric_labels(args.datasource_uid))
    metrics_values = metrics_sub.add_parser("label-values")
    metrics_values.add_argument("-d", "--datasource", dest="datasource_uid")
    metrics_values.add_argument("label")
    metrics_values.set_defaults(handler=lambda args: _client().metric_label_values(args.label, args.datasource_uid))

    logs = sub.add_parser("logs", help="Loki-style log commands")
    logs_sub = logs.add_subparsers(dest="logs_cmd", required=True)
    logs_query = logs_sub.add_parser("query")
    logs_query.add_argument("-d", "--datasource", dest="datasource_uid")
    logs_query.add_argument("expr")
    logs_query.add_argument("--since", default="1h")
    logs_query.add_argument("--limit", type=int, default=100)
    logs_query.add_argument("--from", dest="from_time")
    logs_query.add_argument("--to", dest="to_time")
    logs_query.set_defaults(
        handler=lambda args: _client().query_logs(args.expr, args.datasource_uid, args.since, args.limit, args.from_time, args.to_time)
    )
    logs_labels = logs_sub.add_parser("labels")
    logs_labels.add_argument("-d", "--datasource", dest="datasource_uid")
    logs_labels.set_defaults(handler=lambda args: _client().log_labels(args.datasource_uid))
    logs_values = logs_sub.add_parser("label-values")
    logs_values.add_argument("-d", "--datasource", dest="datasource_uid")
    logs_values.add_argument("label")
    logs_values.set_defaults(handler=lambda args: _client().log_label_values(args.label, args.datasource_uid))

    alert = sub.add_parser("alert", help="alerting commands")
    alert_sub = alert.add_subparsers(dest="alert_cmd", required=True)
    rules = alert_sub.add_parser("rules")
    rules_sub = rules.add_subparsers(dest="rules_cmd", required=True)
    rules_list = rules_sub.add_parser("list")
    rules_list.add_argument("--state", choices=["firing", "normal", "error"])
    rules_list.set_defaults(handler=lambda args: _client().alert_rules(args.state))
    rules_get = rules_sub.add_parser("get")
    rules_get.add_argument("uid")
    rules_get.set_defaults(handler=lambda args: _client().alert_rule(args.uid))
    instances = alert_sub.add_parser("instances")
    instances_sub = instances.add_subparsers(dest="instances_cmd", required=True)
    instances_list = instances_sub.add_parser("list")
    instances_list.add_argument("--state", choices=["firing", "normal", "error"])
    instances_list.set_defaults(handler=lambda args: _client().alert_instances(args.state))
    alert_history = alert_sub.add_parser("history")
    alert_history.add_argument("rule_uid")
    alert_history.set_defaults(handler=lambda args: _client().alert_history(args.rule_uid))

    annotations = sub.add_parser("annotations", help="annotation commands")
    ann_sub = annotations.add_subparsers(dest="annotations_cmd", required=True)
    ann_list = ann_sub.add_parser("list")
    ann_list.add_argument("--dashboard")
    ann_list.add_argument("--tags")
    ann_list.set_defaults(handler=lambda args: _client().annotations(args.dashboard, args.tags))
    ann_create = ann_sub.add_parser("create")
    ann_create.add_argument("--dashboard", required=True)
    ann_create.add_argument("--panel", type=int)
    ann_create.add_argument("--text", required=True)
    ann_create.add_argument("--tags")
    ann_create.set_defaults(handler=lambda args: _client().create_annotation(args.dashboard, args.text, args.panel, _csv(args.tags)))

    link_group = sub.add_parser("links", help="Grafana deeplink commands")
    link_sub = link_group.add_subparsers(dest="links_cmd", required=True)
    link_dash = link_sub.add_parser("dashboard")
    link_dash.add_argument("uid")
    link_dash.set_defaults(handler=_dashboard_link)
    link_panel = link_sub.add_parser("panel")
    link_panel.add_argument("uid")
    link_panel.add_argument("panel_id", type=int)
    link_panel.add_argument("--from", dest="from_range")
    link_panel.add_argument("--to", dest="to_range")
    link_panel.set_defaults(handler=_panel_link)
    link_explore = link_sub.add_parser("explore")
    link_explore.add_argument("-d", "--datasource", required=True, dest="datasource_uid")
    link_explore.add_argument("--query", required=True)
    link_explore.set_defaults(handler=lambda args: links.explore_link(_client().base_url, args.datasource_uid, args.query))

    return parser


def _dashboard_link(args: argparse.Namespace) -> dict[str, str]:
    client = _client()
    dashboard = client.dashboard(args.uid).get("dashboard", {})
    return links.dashboard_link(client.base_url, dashboard)


def _panel_link(args: argparse.Namespace) -> dict[str, str]:
    client = _client()
    dashboard = client.dashboard(args.uid).get("dashboard", {})
    return links.panel_link(client.base_url, dashboard, args.panel_id, args.from_range, args.to_range)


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
