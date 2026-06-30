# State Schema

Grafana reads one task-authored JSON state file from `GRAFANA_STATE_FILE`, defaulting to `/data/grafana/state.json`.

Top-level fields:

- `meta`: workspace metadata, including optional `workspace` and `now`.
- `users`: Grafana-like users; the first user is returned by `/api/user`.
- `datasources`: datasource definitions with `uid`, `name`, `type`, `mode`, and `health`.
- `dashboards`: dashboards with `uid`, `title`, `folder`, `tags`, and `panels`.
- `alerts`: alert rules with `uid`, `name`, `state`, `health`, labels, and optional dashboard/panel links.
- `alert_instances`: alert instances for rule/label combinations.
- `alert_state_history`: timestamped alert state transitions.
- `metrics.queries`: Prometheus-like query fixtures keyed by expression.
- `logs.queries`: Loki-like query fixtures keyed by expression.
- `annotations`: mutable annotations, initially often empty.
- `mutation_log`: mutable verifier-inspectable mutation history, initially often empty.

Grafana copies the read-only seed file from `GRAFANA_STATE_FILE` into `GRAFANA_RUNTIME_STATE_FILE` on startup when the runtime file does not exist. Mutations update only the runtime state file, atomically.

Datasource shape:

```json
{
  "uid": "prom-payments",
  "name": "Payments Prometheus",
  "type": "prometheus",
  "mode": "embedded",
  "health": "ok"
}
```

Future external datasource shape is reserved but not implemented in v1:

```json
{
  "uid": "prom-payments",
  "type": "prometheus",
  "mode": "http",
  "base_url": "http://prometheus-clone:9090"
}
```

Grafana v1 serves embedded fixtures only. Query matching supports exact fixture matches, normalized PromQL matches, metric/log discovery, and simple Loki selectors with optional `|= "text"` filtering.

Metric values and log entries use ISO timestamps. Query callers can provide `since`, `from`, and `to`; Grafana filters fixture values deterministically against `meta.now`.

Dashboard variables live on each dashboard:

```json
{
  "uid": "dash-payment-webhooks",
  "variables": [
    {
      "name": "service",
      "label": "Service",
      "query": "payments",
      "current": {"text": "payments", "value": "payments"}
    }
  ]
}
```
