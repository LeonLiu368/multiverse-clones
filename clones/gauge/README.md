# Gauge

Gauge is a local Grafana-compatible observability service for agent benchmarks. It gives agents realistic Grafana-style surfaces for dashboards, datasources, Prometheus-like metric queries, Loki-like log queries, alerts, annotations, and deeplinks without requiring real Grafana, Grafana Cloud, Prometheus, Loki, Tempo, cloud credentials, or runtime internet access.

Gauge is not Grafana and is unaffiliated with Grafana Labs. It implements a small compatibility subset for task environments.

## Quick Start

```bash
docker compose -f examples/docker-compose.yaml up --build
curl -sf http://localhost:3000/api/healthz
GRAFANA_URL=http://localhost:3000 GRAFANA_TOKEN=test-token-acme-eval bin/gcx whoami --json
GRAFANA_URL=http://localhost:3000 GRAFANA_TOKEN=test-token-acme-eval bin/gcx dashboards search payment --json
```

The example service reads `examples/data/gauge/state.json`, listens on port 80 in the container, and is published on `localhost:3000`.
The seed file is copied into mutable runtime state at `GAUGE_RUNTIME_STATE_FILE` so task fixtures can stay read-only while annotations and mutation logs persist.

## Agent Tools

Gauge intentionally does not make `gauge` the primary task tool. Agents use Grafana-compatible names:

- `gcx`
- `mcp-grafana`

The service image also includes `gaugectl` for admin/debug use. Task instructions should avoid exposing `gaugectl` unless the verifier or operator explicitly needs it.

Admin/verifier endpoints under `/api/_clone/*` require both `GAUGE_ENABLE_ADMIN_API=1` and `GAUGE_ADMIN_TOKEN`. Normal `GRAFANA_TOKEN` and `GRAFANA_SERVICE_ACCOUNT_TOKEN` values cannot read these endpoints.

## Service Image Pattern

Gauge is built as one reusable service image:

```text
ghcr.io/abundant-ai/gauge-service:main
```

Future task packs should copy only the agent tools into the agent image and mount task-specific state only into the Gauge sidecar:

```dockerfile
FROM ghcr.io/abundant-ai/gauge-service:<tag>@sha256:<digest> AS gauge-tools
COPY --from=gauge-tools /usr/local/bin/gcx /usr/local/bin/mcp-grafana /usr/local/bin/
COPY --from=gauge-tools /opt/gaugecli /opt/gaugecli
ENV PYTHONPATH=/opt/gaugecli
ENV GRAFANA_URL=http://gauge
```

```yaml
agent:
  environment:
    GRAFANA_URL: http://gauge
    GRAFANA_TOKEN: test-token-acme-eval
    GRAFANA_SERVICE_ACCOUNT_TOKEN: test-token-acme-eval

gauge:
  image: ghcr.io/abundant-ai/gauge-service:<tag>@sha256:<digest>
  environment:
    GAUGE_STATE_FILE: /data/gauge/state.json
    GAUGE_RUNTIME_STATE_FILE: /var/lib/gauge/state.json
    GRAFANA_SERVICE_ACCOUNT_TOKEN: test-token-acme-eval
  volumes:
    - ./data/gauge/state.json:/data/gauge/state.json:ro
    - gauge-runtime:/var/lib/gauge
```

The raw seed state must not be mounted into the agent container.

`/opt/gaugecli` is Python 3.10+ compatible for current clone task images.

## Local Checks

```bash
python -m pytest tests
docker build -f Dockerfile.service -t gauge-service:local .
docker compose -f examples/docker-compose.yaml up -d
curl -sf http://localhost:3000/api/healthz
GRAFANA_URL=http://localhost:3000 GRAFANA_TOKEN=test-token-acme-eval bin/gcx alert rules list --state firing --json
GRAFANA_URL=http://localhost:3000 GRAFANA_TOKEN=test-token-acme-eval bin/gcx alert instances list --state firing --json
GRAFANA_URL=http://localhost:3000 GRAFANA_TOKEN=test-token-acme-eval bin/gcx dashboards query-panel dash-payment-webhooks 1 --since 10m --json
GRAFANA_URL=http://localhost:3000 GAUGE_ADMIN_TOKEN=test-admin-token-acme-eval bin/gaugectl mutations
docker compose -f examples/docker-compose.yaml down -v
```
