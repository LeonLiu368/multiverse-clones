# Tools

Gauge ships the agent-facing Grafana-compatible tools `gcx` and `mcp-grafana`.

## `gcx`

Every command supports `--json`.

```bash
gcx config check --json
gcx whoami --json

gcx dashboards list --json
gcx dashboards search payment --json
gcx dashboards get dash-payment-webhooks --json
gcx dashboards summary dash-payment-webhooks --json
gcx dashboards panels dash-payment-webhooks --json
gcx dashboards query-panel dash-payment-webhooks 1 --since 10m --json
gcx dashboards variables dash-payment-webhooks --json

gcx datasources list --json
gcx datasources get prom-payments --json
gcx datasources health prom-payments --json

gcx metrics query -d prom-payments 'sum by (status_code)(increase(payment_gateway_responses_total{service="payments"}[5m]))' --since 1h --step 5m --json
gcx metrics query -d prom-payments 'sum(rate(payment_webhook_failures_total[5m]))' --from 2026-06-07T11:50:00Z --to 2026-06-07T12:00:00Z --json
gcx metrics labels -d prom-payments --json
gcx metrics label-values -d prom-payments status_code --json

gcx logs query -d loki-payments '{service="payments"} |= "lock_conflict"' --since 1h --limit 20 --json
gcx logs labels -d loki-payments --json
gcx logs label-values -d loki-payments level --json

gcx alert rules list --state firing --json
gcx alert rules get alert-payment-retry-burn --json
gcx alert instances list --state firing --json
gcx alert history alert-payment-retry-burn --json

gcx annotations list --dashboard dash-payment-webhooks --json
gcx annotations create --dashboard dash-payment-webhooks --panel 1 --text "investigated spike" --tags incident,OPS-1 --json

gcx links dashboard dash-payment-webhooks --json
gcx links panel dash-payment-webhooks 1 --from now-1h --to now --json
gcx links explore -d prom-payments --query 'sum(rate(payment_webhook_failures_total[5m]))' --json
```

Exit codes:

- `0`: success
- `1`: user/input error
- `2`: not found
- `3`: auth/config error
- `5`: backend unavailable
- `6`: unsupported command

## `mcp-grafana`

`mcp-grafana` is a stdio MCP server. It exposes these tools:

- `search_dashboards`
- `get_dashboard_by_uid`
- `get_dashboard_summary`
- `get_dashboard_property`
- `get_dashboard_panel_queries`
- `get_dashboard_variables`
- `run_dashboard_panel_query`
- `list_datasources`
- `get_datasource`
- `get_query_examples`
- `query_prometheus`
- `list_prometheus_metric_names`
- `list_prometheus_label_names`
- `list_prometheus_label_values`
- `query_loki_logs`
- `list_loki_label_names`
- `list_loki_label_values`
- `alerting_list_rules`
- `alerting_get_rule`
- `alerting_list_instances`
- `alerting_get_state_history`
- `generate_deeplink`
- `get_annotations`
- `create_annotation`

Both tools use `GRAFANA_URL` and `GRAFANA_TOKEN` or `GRAFANA_SERVICE_ACCOUNT_TOKEN`.
`gcx` also accepts `GRAFANA_SERVER` as a base URL alias when `GRAFANA_URL` is unset.

## Read-Only MCP

Use `mcp-grafana --disable-write` to expose read/query/list tools while hiding write tools such as `create_annotation`.
