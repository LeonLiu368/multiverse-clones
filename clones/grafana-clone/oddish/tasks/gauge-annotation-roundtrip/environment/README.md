# Grafana

Grafana is a local Grafana-compatible observability service for agent benchmarks. It gives agents realistic Grafana-style surfaces for dashboards, datasources, Prometheus-like metric queries, Loki-like log queries, alerts, annotations, and deeplinks without requiring real Grafana, Grafana Cloud, Prometheus, Loki, Tempo, cloud credentials, or runtime internet access.

Grafana is not Grafana and is unaffiliated with Grafana Labs. It implements a small compatibility subset for task environments.

## Quick Start

```bash
docker compose -f examples/docker-compose.yaml up --build
curl -sf http://localhost:3000/api/healthz
GRAFANA_URL=http://localhost:3000 GRAFANA_TOKEN=test-token-acme-eval bin/gcx whoami --json
GRAFANA_URL=http://localhost:3000 GRAFANA_TOKEN=test-token-acme-eval bin/gcx dashboards search payment --json
```

The example service reads `examples/data/grafana/state.json`, listens on port 80 in the container, and is published on `localhost:3000`.
The seed file is copied into mutable runtime state at `GRAFANA_RUNTIME_STATE_FILE` so task fixtures can stay read-only while annotations and mutation logs persist.

## Agent Tools

Grafana intentionally does not make `grafana` the primary task tool. Agents use Grafana-compatible names:

- `gcx`
- `mcp-grafana`

The service image also includes `grafanactl` for admin/debug use. Task instructions should avoid exposing `grafanactl` unless the verifier or operator explicitly needs it.

Admin/verifier endpoints under `/api/_clone/*` require both `GRAFANA_ENABLE_ADMIN_API=1` and `GRAFANA_ADMIN_TOKEN`. Normal `GRAFANA_TOKEN` and `GRAFANA_SERVICE_ACCOUNT_TOKEN` values cannot read these endpoints.

## Service Image Pattern

Grafana is built as one reusable service image:

```text
ghcr.io/abundant-ai/grafana-service:main
```

Future task packs should copy only the agent tools into the agent image and mount task-specific state only into the Grafana sidecar:

```dockerfile
FROM ghcr.io/abundant-ai/grafana-service:<tag>@sha256:<digest> AS grafana-tools
COPY --from=grafana-tools /usr/local/bin/gcx /usr/local/bin/mcp-grafana /usr/local/bin/
COPY --from=grafana-tools /opt/grafanacli /opt/grafanacli
ENV PYTHONPATH=/opt/grafanacli
ENV GRAFANA_URL=http://grafana
```

```yaml
agent:
  environment:
    GRAFANA_URL: http://grafana
    GRAFANA_TOKEN: test-token-acme-eval
    GRAFANA_SERVICE_ACCOUNT_TOKEN: test-token-acme-eval

grafana:
  image: ghcr.io/abundant-ai/grafana-service:<tag>@sha256:<digest>
  environment:
    GRAFANA_STATE_FILE: /data/grafana/state.json
    GRAFANA_RUNTIME_STATE_FILE: /var/lib/grafana/state.json
    GRAFANA_SERVICE_ACCOUNT_TOKEN: test-token-acme-eval
  volumes:
    - ./data/grafana/state.json:/data/grafana/state.json:ro
    - grafana-runtime:/var/lib/grafana
```

The raw seed state must not be mounted into the agent container.

`/opt/grafanacli` is Python 3.10+ compatible for current clone task images.

## Local Checks

```bash
python -m pytest tests
docker build -f Dockerfile.service -t grafana-service:local .
docker compose -f examples/docker-compose.yaml up -d
curl -sf http://localhost:3000/api/healthz
GRAFANA_URL=http://localhost:3000 GRAFANA_TOKEN=test-token-acme-eval bin/gcx alert rules list --state firing --json
GRAFANA_URL=http://localhost:3000 GRAFANA_TOKEN=test-token-acme-eval bin/gcx alert instances list --state firing --json
GRAFANA_URL=http://localhost:3000 GRAFANA_TOKEN=test-token-acme-eval bin/gcx dashboards query-panel dash-payment-webhooks 1 --since 10m --json
GRAFANA_URL=http://localhost:3000 GRAFANA_ADMIN_TOKEN=test-admin-token-acme-eval bin/grafanactl mutations
docker compose -f examples/docker-compose.yaml down -v
```
