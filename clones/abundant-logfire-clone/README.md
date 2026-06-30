# abundant-logfire-clone

A thin, **faithful Logfire clone** for agent-eval: serves Logfire's Query API
(`POST /v2/query` — SQL over a `records` table) backed by DuckDB, so an agent debugs the
way an Abundant SWE actually does — `SELECT … FROM records WHERE …`, with real
**traces/spans** (`trace_id/span_id/parent_span_id/duration`), **exceptions**
(`exception_type/message/stacktrace`), and **http** columns.

- Same endpoint + `{schema,data}` response + required body (`sql` + `min_timestamp`,
  optional `max_timestamp`/`limit`) + time-window scoping as the real Logfire Query API.
- Read-only (SELECT/WITH only), Bearer read token, offline, data sealed behind the API.
- Operated through a **`logfire` CLI** and a **`logfire-mcp` server**, both thin clients of
  the one HTTP API and in parity (see `docs/COVERAGE.md`).

## Architecture (agent + gateway, canon image trio)

Two containers per Harbor task:

- **agent** (`main`) — neutral `python:slim`, ships only `logfire` + `logfire-mcp`,
  **no data, no `server.py`**; reaches state only over HTTP at `$LOGFIRE_URL`.
- **gateway** — the Query API + DuckDB store. Realized as the canon trio:
  - `logfire-service:latest` — base, data-free
  - `logfire-service:empty` — mount target (`/data/records.json`)
  - `logfire-service:prod-v1` — incident corpus **baked** (`corpus/records.json.gz`),
    served **mount-free**

Switching a task `empty ↔ prod-v1` is the **image tag alone**.

## Build

```bash
./build.sh                       # build the trio + agent locally (ghcr.io/abundant-ai/*)
./build.sh <registry/ns>         # override the namespace
```

CI (`.github/workflows/logfire-service-image.yml`) publishes the trio to GHCR
**multi-arch** (`linux/amd64,linux/arm64`) on push-to-main.

## Tests

```bash
pytest                           # api + CLI/MCP parity + isolation/import-leak (needs duckdb, mcp, pytest)
```

The isolation tests run against the locally-built `logfire-agent` image (skipped if absent).

## Bundled task

`oddish/tasks/logfire-incident-rca` — an observability + SWE task on the **prod-v1** baked
corpus: the agent must query the telemetry to recover an incident root cause
(missing DB column on the worker's table) and apply a code fix. `nop=0, oracle=1`.
See `oddish/README.md`.
