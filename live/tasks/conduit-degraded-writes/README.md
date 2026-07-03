# live/tasks/conduit-degraded-writes

A **live-deployment observability + remediation** eval task. Conduit (a RealWorld
FastAPI + Postgres service) is deployed on a real **Dokku** plane with a
config-driven fault: it runs a **single uvicorn worker** (`WEB_CONCURRENCY=1`), so
under concurrent load the CPU-bound request path (bcrypt logins) serializes on one
event loop and article writes / logins saturate. The agent must:

1. **Diagnose from live telemetry** — spans stream `conduit → otel-collector →
   logfire clone`; the agent queries them with `logfire query` (SQL over a
   `records` table).
2. **Remediate the live deployment** via the Dokku SSH surface
   (`ssh dokku@dokku config:set conduit …`).
3. **Write `/workspace/findings.json`** naming the failing component + mechanism.

Graded by a post-agent **soak** (drives concurrent load, checks the deployment now
holds up) + a findings mechanism gate. **nop=0, oracle=1.**

## Compose topology (`environment/docker-compose.yaml`)

No explicit `networks:` block — Harbor puts every service on one default network,
so containers reach each other by name.

| Service | Role |
|---|---|
| `postgres` | SUT database |
| `logfire` | telemetry backend (Logfire clone, `logfire-service:latest`) — live OTLP-JSON ingest (`/v1/traces`, write-token gated) + query (`/v2/query`, read-token). Boots from a **minimal 1-row** `logfire-records.json`, fills via ingest. |
| `otel-collector` | OTLP/protobuf in (`:4318`) → OTLP/HTTP **JSON** out to `http://logfire:80`, `encoding: json`, `compression: none`, `Authorization: Bearer <write token>`. |
| `dokku` | deploy plane (socket-sibling) — hosts conduit as a sibling container `conduit.web.1:8000`. |
| `provisioner` | one-shot: generates the agent keypair, assembles the SUT repo (vendored `app/` + `otel-wrap/` overlay), `provision-gitsync.sh` deploys conduit **with the fault** (`WEB_CONCURRENCY=1`) + OTEL env + `DATABASE_URL`/`SECRET_KEY`, seeds users/articles + a fixed `soakfixed` login user, waits healthy, writes a readiness marker, exits 0. |
| `main` | the agent: `python:3.12-slim` + `logfire` CLI/MCP (client-only, **no `server.py`**), ssh/git/httpx/curl, the provisioned agent SSH key. **No answer material.** |

### Provisioning wiring
`main` `depends_on: provisioner (service_completed_successfully)`. As a fallback for
Harbors that don't honor that condition, `main`'s entrypoint also **waits** until
the readiness marker (`/mnt/state/provisioned`, shared volume) exists AND
`conduit.web.1:8000/api/tags` is healthy before handing off. Shared named volumes:
`keys` (agent pubkey→dokku, privkey→main), `sut` (assembled repo→dokku git:sync),
`state` (readiness marker).

### Telemetry hop that matters
The clone's stdlib ingest reads the request body as plain JSON, so the collector's
`otlphttp` exporter must set **`compression: none`** (its default gzip makes
`/v1/traces` 400). With that, `service.name=conduit` (from `OTEL_SERVICE_NAME`)
lands as `service_name='conduit'` rows carrying `duration`, `span_name`,
`http_route`, `http_method`, `http_response_status_code`.

## The fault + fix
- **Fault (armed by provisioner):** `WEB_CONCURRENCY=1` — one uvicorn worker.
- **Fix (oracle / agent):** `ssh dokku@dokku config:set conduit WEB_CONCURRENCY=4`
  → redeploy (4 workers). NOT named in the instruction or the `main` image.

## Calibrated soak config (`tests/soak_config.json`)
The soak drives two flows against `conduit.web.1:8000`: `write_readback` (POST
`/api/articles` + read-back by slug) and `login_churn` (POST `/api/users/login`
per request — bcrypt CPU that blocks the single event loop). Calibration:

| Key | Value | Why |
|---|---|---|
| `warmup_s` | 12 | discarded — absorbs the agent's redeploy blip |
| `soak_s` | 60 | measured window |
| `rps` | 8 | offered rate: above a single worker's bcrypt-login capacity (~4/s) but below 4 workers' (~15/s) |
| `workers` | 24 | ≥ rps·request_timeout so the offered rate isn't self-throttled |
| `request_timeout_s` | 1.5 | **the separator**: between fixed p95 (~0.4s, clears) and faulty p95 (~1.5s+, times out → counts as error + lost goodput) |
| `goodput_min` | 0.80 | fixed sits at 1.0; faulty at ~0.01 |
| `error_rate_max` | 0.15 | fixed at 0.0; faulty at ~0.99 |

Two flows, weight 1.0 each: `write_readback` (POST `/api/articles` + read-back)
and `login_churn` (POST `/api/users/login` every request — bcrypt CPU that blocks
the single event loop). Findings gate (`mechanism_regexes`): must match
`(worker|concurren|event.?loop)` AND `(bcrypt|cpu|serial|saturat|block|queue)` —
forces naming the real mechanism, blocks a vague "it was slow" or a wrong
"connection pool" answer.

## Measured nop vs oracle (local, arm64 Docker Desktop)

Full stack up, spans confirmed flowing to logfire (`logfire query` returns live
`service_name='conduit'` rows). Per-driver AND overall gates.

| Scenario | WEB_CONCURRENCY | overall goodput | overall error_rate | overall p95 | reward |
|---|---|---|---|---|---|
| **NOP** (faulty, no fix) | 1 | 0.01 | 0.99 | ~1510ms (timeouts) | **0.0** |
| **ORACLE** (solve.sh fix) | 4 | 1.00 | 0.00 | ~399ms | **1.0** |

ORACLE ×3 = **1.0, 1.0, 1.0** (stable). The oracle each run: `logfire query`
diagnoses the single-service latency saturation → `ssh dokku@dokku config:set
conduit WEB_CONCURRENCY=4` (clean redeploy, 4 workers confirmed) → writes
`findings.json`. NOP fails on BOTH goodput and error_rate gates, per-driver and
overall — a wide, non-marginal margin.

### Deploy-plane details that matter (learned during calibration)
- **Port**: the provisioner runs `dokku ports:set conduit http:80:8000` so dokku
  injects `PORT=8000` (the app honors `$PORT`; the whole task targets
  `conduit.web.1:8000`). Without it dokku defaults to `PORT=5000`.
- **Redeploy reliability**: the provisioner runs `dokku checks:disable conduit`.
  Dokku's zero-downtime port-listening check uses `nsenter` into the app
  container, which fails in socket-sibling mode and makes every redeploy
  (including the agent's `config:set` fix) slow/flaky. Disabling it makes
  `config:set` redeploys complete in ~30-40s. The app's real health is gated by
  the soak verifier + the provisioner directly (not dokku's proxy).
- **Local build note**: Docker Desktop's `credsStore: desktop` credential helper
  can wedge and stall all buildkit `load metadata` steps (host builds AND dokku's
  git:sync builds). If builds hang at "load metadata", remove `credsStore` from
  `~/.docker/config.json`. (Not a task-artifact issue — a local-daemon quirk.)

## Local validation
`environment/validate_local.sh` brings the full stack up, confirms live spans reach
logfire, runs NOP (faulty → reward 0) and ORACLE (`solution/solve.sh` → reward 1,
repeated ×3 for stability).
