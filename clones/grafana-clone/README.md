# grafana-clone

grafana-clone is a local Grafana-compatible observability service for agent benchmarks. It gives agents realistic Grafana-style surfaces for dashboards, datasources, Prometheus-like metric queries, Loki-like log queries, alerts, annotations, and deeplinks without requiring real Grafana, Grafana Cloud, Prometheus, Loki, Tempo, cloud credentials, or runtime internet access.

grafana-clone — a Grafana-compatible clone (a benchmark-focused API subset; not affiliated with Grafana Labs).

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

## Service Image Pattern (the gateway trio)

Grafana ships a **gateway image trio** (see `docs/IMAGE-RELEASE.md`):

```text
ghcr.io/abundant-ai/grafana-service:main      # base gateway (data-free)
ghcr.io/abundant-ai/grafana-service:empty     # base, no data — a MOUNT target
ghcr.io/abundant-ai/grafana-service:prod-v1   # corpus baked in — serves mount-free
```

A task selects its seeding path by **image tag alone**: `:empty` + a mounted `state.json`
fixture, or `:prod-v1` which serves the baked corpus with no mount. Both are published
multi-arch (`linux/amd64,linux/arm64`).

The **agent** image must carry the tools ONLY — copy `gcx` + `mcp-grafana` + `/opt/grafanacli`,
then strip the gateway's server source so an agent can neither read nor regenerate the
answer (R2.k):

```dockerfile
FROM ghcr.io/abundant-ai/grafana-service:<tag>@sha256:<digest> AS grafana-tools
FROM python:3.10-slim
COPY --from=grafana-tools /usr/local/bin/gcx /usr/local/bin/mcp-grafana /usr/local/bin/
COPY --from=grafana-tools /opt/grafanacli /opt/grafanacli
# strip api/seed/query/admin source; keep only the CLI/MCP + pure links.py helper
RUN find /opt/grafanacli/grafana/server -type f -name '*.py' \
        ! -name '__init__.py' ! -name 'links.py' -delete && \
    ! python -c 'import grafana.server.state' 2>/dev/null   # leak probe must FAIL to import
ENV PYTHONPATH=/opt/grafanacli GRAFANA_URL=http://grafana
```

```yaml
# :empty + mount (per-task fixture into the GATEWAY only)
grafana:
  image: ghcr.io/abundant-ai/grafana-service:empty
  environment:
    GRAFANA_STATE_FILE: /data/grafana/state.json
    GRAFANA_RUNTIME_STATE_FILE: /var/lib/grafana/state.json
  volumes:
    - ./data/grafana/state.json:/data/grafana/state.json:ro
    - grafana-runtime:/var/lib/grafana
# OR :prod-v1 — same task, corpus baked in, no volume needed
```

The raw seed state must NEVER be mounted into the agent container.
`/opt/grafanacli` is Python 3.10+ compatible.

## Bundled Harbor task

`oddish/tasks/gauge-annotation-roundtrip/` is a runnable two-container (agent + grafana
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
docker build -f Dockerfile.service -t grafana-service:local .
docker compose -f examples/docker-compose.yaml up -d
curl -sf http://localhost:3000/api/healthz
GRAFANA_URL=http://localhost:3000 GRAFANA_TOKEN=test-token-acme-eval bin/gcx alert rules list --state firing --json
GRAFANA_URL=http://localhost:3000 GRAFANA_TOKEN=test-token-acme-eval bin/gcx alert instances list --state firing --json
GRAFANA_URL=http://localhost:3000 GRAFANA_TOKEN=test-token-acme-eval bin/gcx dashboards query-panel dash-payment-webhooks 1 --since 10m --json
GRAFANA_URL=http://localhost:3000 GRAFANA_ADMIN_TOKEN=test-admin-token-acme-eval bin/grafanactl mutations
docker compose -f examples/docker-compose.yaml down -v
```
