# otel-wrap/ — OTel deploy overlay for the VENDORED Conduit SUT (`../app/`)

This directory wraps the **vendored real-OSS RealWorld backend**
(`nsidnev/fastapi-realworld-example-app` @ `029eb77`, full source in `../app/`,
provenance in `../../MANIFEST.json`) into the dokku-deployable, OTel-
auto-instrumented SUT. The vendored tree stays pristine (its upstream
poetry Dockerfile is kept for provenance but never used).

## Assembly (done by `platform/smoke.sh` / task setup)

```sh
repo=$(mktemp -d)
cp -R sut-conduit/app/ "$repo"                  # vendored source
cp sut-conduit/otel-wrap/Dockerfile \
   sut-conduit/otel-wrap/requirements.txt "$repo"/   # overlay at repo root
# git init + commit, then `dokku git:sync --build conduit $repo`
```

## Files
| File | Role |
|---|---|
| `Dockerfile` | Replaces the upstream poetry Dockerfile: pip-pinned deps + `opentelemetry-instrument uvicorn` CMD (alembic migrations at boot, DB-wait retry). Zero app-code changes. |
| `requirements.txt` | Upstream poetry.lock main-category pins + OTel distro/exporter/instrumentors. Two documented deviations (typing-extensions, psycopg2-binary). |
| `seed.py` | Idempotent API-level fixture: 3 users, 6 tagged articles. |
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
