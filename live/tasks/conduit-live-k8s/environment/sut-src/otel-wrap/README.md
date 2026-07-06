# otel-wrap/ — OTel overlay + build recipe for the Conduit SUT image

This directory is the **build recipe** for the published SUT image
`ghcr.io/abundant-ai/conduit-otel:latest` (PUBLIC on ghcr). It wraps the real-OSS
RealWorld backend (`nsidnev/fastapi-realworld-example-app` @ `029eb77`) with OTel
auto-instrumentation. **The upstream app source is no longer vendored in this task
dir** — the published image carries it, and the task references the image only (k3s
pulls it at runtime). Provenance is in `../MANIFEST.json`.

## Rebuild / republish the image (optional maintenance)

`./publish-sut.sh` re-fetches the upstream repo@commit, overlays this dir's
`Dockerfile` + `requirements.txt` at the repo root, builds
`ghcr.io/abundant-ai/conduit-otel:latest` (`--provenance=false`), and pushes it
(needs `docker login ghcr.io`). The task's `docker compose build` does NOT run
this — the SUT is a published public image, not built at task time.

## Files
| File | Role |
|---|---|
| `Dockerfile` | Replaces the upstream poetry Dockerfile: pip-pinned deps + `opentelemetry-instrument uvicorn` CMD (alembic migrations at boot, DB-wait retry). Zero app-code changes. |
| `requirements.txt` | Upstream poetry.lock main-category pins + OTel distro/exporter/instrumentors. Two documented deviations (typing-extensions, psycopg2-binary). |
| `publish-sut.sh` | Optional: (re)build + push the public SUT image from provenance. NOT in the task build/run path. |
| `seed.py` | Idempotent API-level fixture: 3 users, 6 tagged articles. Inlined into `k3s/manifests/50-conduit-seed.yaml` (the seed Job's ConfigMap). |
| `load_probe.py` | Stdlib concurrent load probe (writers × requests, write/read/mixed + `--login-every` session churn). Prints JSON p50/p95/max/error-rate. |

## Runtime env (set via `dokku config:set`)
| Var | Meaning |
|---|---|
| `DATABASE_URL` | `postgresql://user:pass@host:5432/db` — **postgresql:// scheme** (SQLAlchemy 1.4 alembic rejects legacy `postgres://`). |
| `SECRET_KEY` | JWT secret (required). |
| `WEB_CONCURRENCY` | **The P4 fault knob.** Read natively by uvicorn (uvicorn/config.py) — worker process count. Faulty `1`, fix `4`. Zero code changes. |
| `MAX_CONNECTIONS_COUNT` / `MIN_CONNECTIONS_COUNT` | asyncpg pool bounds per worker (app-native env). Keep at `10`/`5`. |
| `OTEL_*` | Standard OTel env (`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, exporters...), or `OTEL_SDK_DISABLED=true` for collector-less smoke runs. |

## Why the fault knob is WEB_CONCURRENCY, not MAX_CONNECTIONS_COUNT

The plan hypothesized the app-native asyncpg pool bound
(`MAX_CONNECTIONS_COUNT=1`) as the fault. **Measured (arm64 Docker Desktop,
local postgres:16, 12 concurrent clients × 20 reqs): the pool knob does NOT
degrade.** Three workloads tried — pure writes, mixed write+read, deep-offset
reads over a 100k-article table:

| Workload | pool=1 p95 | pool=15 p95 |
|---|---|---|
| 12×20 writes | 195ms | 261ms |
| 12×20 mixed | 140ms | 157ms |
| 12×20 deep reads (100k rows) | 564ms | 638ms |

No separation (differences are noise): the app is fully async and local
queries are sub-ms, so the single Python event loop — not the pool — is the
bottleneck. The plan's fallback ("env-driven uvicorn worker count") applies
and it IS genuinely load-degrading, because real traffic includes session
churn: every login does a passlib/bcrypt verify (~265ms of pure CPU measured)
that blocks the whole event loop of a single worker.

Measured with the smoke workload (12 writers × 20 iterations of
write+read, login every 5th iteration):

| Config | Throughput | p50 | p95 | max |
|---|---|---|---|---|
| faulty `WEB_CONCURRENCY=1` | 28.4 rps | 113ms | **1892ms** | 3654ms |
| fixed `WEB_CONCURRENCY=4` | 111.1 rps | 26ms | **314ms** | 1351ms |

~6× p95 / ~4× throughput separation; a single request at rest is ~15ms in
both configs (healthy at rest). See `platform/SMOKE-RESULTS.md` for the
end-to-end numbers measured through dokku.
