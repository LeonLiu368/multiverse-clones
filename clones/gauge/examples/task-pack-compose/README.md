# Task-Pack Compose Example

This example mirrors the future Harbor/TB3 integration shape.

- `agent` receives only `gcx`, `mcp-grafana`, and `/opt/gaugecli`.
- `agent` receives normal Grafana-compatible env vars only.
- `agent` does not receive `gaugectl`, `GAUGE_ADMIN_TOKEN`, or the raw state mount.
- `gauge` owns the raw seed state and mutable runtime state.

Smoke:

```bash
docker build -f Dockerfile.service -t gauge-service:local .
docker compose -f examples/task-pack-compose/docker-compose.yaml up -d --build
docker compose -f examples/task-pack-compose/docker-compose.yaml exec -T agent test ! -e /data/gauge/state.json
docker compose -f examples/task-pack-compose/docker-compose.yaml exec -T agent gcx dashboards search payment --json
docker compose -f examples/task-pack-compose/docker-compose.yaml exec -T agent gcx metrics query -d prom-payments 'sum by (status_code)(increase(payment_gateway_responses_total{service="payments"}[5m]))' --since 1h --step 5m --json
docker compose -f examples/task-pack-compose/docker-compose.yaml exec -T agent gcx logs query -d loki-payments '{service="payments"} |= "lock_conflict"' --since 1h --limit 20 --json
docker compose -f examples/task-pack-compose/docker-compose.yaml exec -T agent gcx annotations create --dashboard dash-payment-webhooks --panel 1 --text "task-pack smoke annotation" --tags smoke,TASK-PACK --json
docker compose -f examples/task-pack-compose/docker-compose.yaml exec -T -e GRAFANA_URL=http://localhost -e GAUGE_ADMIN_TOKEN=test-admin-token-acme-eval gauge gaugectl mutations
docker compose -f examples/task-pack-compose/docker-compose.yaml down -v
```
