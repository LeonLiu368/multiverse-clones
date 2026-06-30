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

## Service Image Pattern (the gateway trio)

Gauge ships a **gateway image trio** (see `docs/IMAGE-RELEASE.md`):

```text
ghcr.io/abundant-ai/gauge-service:main      # base gateway (data-free)
ghcr.io/abundant-ai/gauge-service:empty     # base, no data — a MOUNT target
ghcr.io/abundant-ai/gauge-service:prod-v1   # corpus baked in — serves mount-free
```

A task selects its seeding path by **image tag alone**: `:empty` + a mounted `state.json`
fixture, or `:prod-v1` which serves the baked corpus with no mount. Both are published
multi-arch (`linux/amd64,linux/arm64`).

The **agent** image must carry the tools ONLY — copy `gcx` + `mcp-grafana` + `/opt/gaugecli`,
then strip the gateway's server source so an agent can neither read nor regenerate the
answer (R2.k):

```dockerfile
FROM ghcr.io/abundant-ai/gauge-service:<tag>@sha256:<digest> AS gauge-tools
FROM python:3.10-slim
COPY --from=gauge-tools /usr/local/bin/gcx /usr/local/bin/mcp-grafana /usr/local/bin/
COPY --from=gauge-tools /opt/gaugecli /opt/gaugecli
# strip api/seed/query/admin source; keep only the CLI/MCP + pure links.py helper
RUN find /opt/gaugecli/gauge/server -type f -name '*.py' \
        ! -name '__init__.py' ! -name 'links.py' -delete && \
    ! python -c 'import gauge.server.state' 2>/dev/null   # leak probe must FAIL to import
ENV PYTHONPATH=/opt/gaugecli GRAFANA_URL=http://gauge
```

```yaml
# :empty + mount (per-task fixture into the GATEWAY only)
gauge:
  image: ghcr.io/abundant-ai/gauge-service:empty
  environment:
    GAUGE_STATE_FILE: /data/gauge/state.json
    GAUGE_RUNTIME_STATE_FILE: /var/lib/gauge/state.json
  volumes:
    - ./data/gauge/state.json:/data/gauge/state.json:ro
    - gauge-runtime:/var/lib/gauge
# OR :prod-v1 — same task, corpus baked in, no volume needed
```

The raw seed state must NEVER be mounted into the agent container.
`/opt/gaugecli` is Python 3.10+ compatible.

## Bundled Harbor task

`oddish/tasks/gauge-annotation-roundtrip/` is a runnable two-container (agent + gauge
gateway) task: the agent investigates a firing alert via `gcx`/`mcp-grafana` and posts an
incident annotation, read back through the API (write→read round-trip). `tests/test.sh`
writes `/logs/verifier/reward.txt`; `solution/solve.sh` is the oracle. Validate end-to-end
(nop=0, oracle=1, decoy=0, isolation):

```bash
bash oddish/tasks/gauge-annotation-roundtrip/validate_local.sh
```

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
