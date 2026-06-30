# Image Release

Grafana publishes a **gateway image trio** (R2) plus a thin agent built per task. The gateway
is the single source of truth (HTTP API + CLI/MCP thin clients + seeder); the agent carries
the tools only, no data, no server source.

## The trio

```text
ghcr.io/abundant-ai/grafana-service:main      # base gateway (data-free), tagged per branch/sha
ghcr.io/abundant-ai/grafana-service:empty     # base gateway, no data — a MOUNT target
ghcr.io/abundant-ai/grafana-service:prod-v1   # corpus state.json BAKED IN — serves mount-free
```

All three are published **multi-arch** (`linux/amd64,linux/arm64`) by CI.

### `:empty` (base) — empty + mount path
Data-free gateway. Per-task fixture is delivered by **mounting** `state.json` into the
gateway (`GRAFANA_STATE_FILE` → the mount). Built from `Dockerfile.service`. Use for tasks
that need a small/custom workspace. The base/`:main`/`:empty` images are the same build.

### `:prod-v1` — baked-DB (GHCR image-DB seeding)
`Dockerfile.prod-v1` is `FROM` `:empty` and `COPY`s the corpus
(`examples/data/grafana/state.json`) to `/srv/grafana/state.json`, pointing `GRAFANA_STATE_FILE`
at it. It boots healthy and serves the **full corpus from a cold `docker compose up` with
no mount** — switching a task `empty ↔ prod-v1` is the **image tag alone**.

```bash
# build + boot prod-v1 mount-free, query the baked corpus:
docker build -f Dockerfile.service -t ghcr.io/abundant-ai/grafana-service:empty .
docker build -f Dockerfile.prod-v1 --build-arg BASE=ghcr.io/abundant-ai/grafana-service:empty \
  -t ghcr.io/abundant-ai/grafana-service:prod-v1 .
docker run -d --name g -e GRAFANA_TOKEN=test-token-acme-eval ghcr.io/abundant-ai/grafana-service:prod-v1
docker exec -e GRAFANA_URL=http://localhost -e GRAFANA_TOKEN=test-token-acme-eval g \
  gcx dashboards search payment --json     # returns the seeded dashboard, no mount
```

## The thin agent (R2.c / R2.k)
The agent image (`examples/task-pack-compose/Dockerfile.agent`, and each task's
`environment/Dockerfile`) copies only `gcx` + `mcp-grafana` + `/opt/grafanacli`, then **strips
the gateway's API/seed/query/admin source** — every `grafana/server/*.py` except `__init__.py`
and the pure `links.py` helper. After the strip:

- `import grafana.server.state` (the seed/state loader) raises `ModuleNotFoundError`,
- `import grafana.server.query_engine` / `.app` / `.clone_admin` raise,
- no `api/`/`seed` source survives, and the `grafanactl` admin CLI is absent,
- `gcx` and `mcp-grafana` still load.

The Dockerfiles run this as a build-time leak smoke test; `tests/test_isolation.py` enforces
it by default in `pytest`.

## Local build (base)

```bash
docker build -f Dockerfile.service -t grafana-service:local .
docker compose -f examples/docker-compose.yaml up -d
curl -sf http://localhost:3000/api/healthz
GRAFANA_URL=http://localhost:3000 GRAFANA_ADMIN_TOKEN=test-admin-token-acme-eval bin/grafanactl mutations
docker compose -f examples/docker-compose.yaml down -v
```

## CI

`.github/workflows/build-service-image.yml` runs tests (Py 3.10/3.11/3.13), builds the
image, runs the example + task-pack compose smoke tests, then on `main` pushes the gateway
trio **multi-arch**: `:main`/`:<sha>`/`:empty` from `Dockerfile.service` and `:prod-v1` from
`Dockerfile.prod-v1` (FROM `:empty`, corpus baked in). `permissions: packages: write` with
the built-in `GITHUB_TOKEN`.

Task packs may pull `:prod-v1`/`:empty` directly, or (default) carry a `build:`+`image:`
dual so the gateway builds locally and never needs a registry pull (R1.5).
```text
ghcr.io/abundant-ai/grafana-service:prod-v1@sha256:<digest>
```
