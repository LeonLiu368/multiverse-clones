# Clone Audit Report — `abundant-logfire-clone`

- **Audited:** `2026-06-30` · **Auditor:** `clone-audit v1` · **Commit:** `36e78af`
- **Fidelity tier (declared / observed):** `T2` (implied) / `T2` — real DuckDB SQL query grammar over a `records` table
- **Verdict:** ❌ FAILS — *(meets = all gating reqs pass)*
- **Gating score:** `2 / 6` gating requirements pass (R3, R5). R1, R2, R4, R6 fail.

## TL;DR
A genuinely faithful, thin Logfire **Query API** clone: `POST /v2/query` runs read-only DuckDB SQL
over a `records` table with real trace/span/exception/http columns, fronted by a `logfire` CLI (3
commands) and a `logfire-mcp` server (3 tools mirroring the real Pydantic Logfire MCP), both verified
to be thin clients of one HTTP API and in **parity**. The *query surface* is eval-useful today. But it
is **not a Clone-Standard task**: there is **no docker-compose, no `tests/`, no `test.sh`/`solve.sh`
oracle, no `docs/COVERAGE.md`, no CI**, and the gateway ships as a per-incident COPY-data image
(`logfire-gateway:oddish-incident-534pm`) rather than the canonical `:prod-v1`(baked-DB) + `:empty`
(mount-target) pair. **Top action item:** add the Harbor task scaffold (compose + `tests/test.sh` →
`reward.txt` + `solution/solve.sh`) and re-tag the gateway as the `:prod-v1`/`:empty` trio.

## What it handles well
- **Faithful Query API envelope.** `POST /v2/query` returns the real `{schema:{fields:[{name,data_type}]}, data:[…]}`
  shape; required body is `sql` + `min_timestamp` (optional `max_timestamp`/`limit`), exactly as upstream.
  Verified by direct curl (HTTP 200 with full 12-column schema on `SELECT *`).
- **Real read-only enforcement + auth.** Bad token → `401 {"detail":"Invalid read token"}`; `INSERT`/`DROP`
  → `400 {"error":"invalid query","details":"only SELECT/WITH queries are allowed"}`; missing fields →
  `400 {"error":"sql and min_timestamp are required"}`; bad column → `400` with the real DuckDB Binder
  Error. Unknown path → `404`. All observed, real envelopes (no 500s).
- **Time-window scoping works.** `max_timestamp` correctly excludes out-of-window records (verified:
  a `2026-06-27` KeyError dropped when `max=2026-06-26T23:59:59Z`).
- **CLI + MCP parity.** `logfire {query,exceptions,schema}` and MCP `{arbitrary_query, find_exceptions,
  get_logfire_records_schema}` both call `cli.query` → the one HTTP API; CLI `exceptions` vs MCP
  `find_exceptions` returned byte-equal data (`EQUAL`, 2 rows).
- **Baked-DB mechanism works.** `logfire-gateway:oddish-incident-534pm` boots **mount-free** and serves
  a real 3292-record corpus (`{"ok":true,"records":3292}`) — the prod-v1 *mechanism* exists, just
  mis-tagged.
- **Agent is data-free.** Agent image has no `/data/records.json` (`SEALED`); the corpus lives only
  behind the gateway.

## Scorecard

| Req | Area | Result | Evidence | Action item (if not full pass) |
|---|---|---|---|---|
| R1 | Setup & run (Harbor) | **fail** | no compose / no `tests/test.sh` / no `solution/solve.sh`; nop & oracle unmeasurable | Add Harbor task scaffold; measure nop=0/oracle=1 |
| R2 | Architecture canon a–g + seeding j–k | **fail** | grid below; gateway tag `oddish-incident-534pm`, no `:prod-v1`/`:empty`; both images `linux/amd64`-only; agent carries `server.py` | Re-tag trio; multi-arch; strip gateway API from agent |
| R3 | CLI + MCP parity | **pass** | CLI 3 cmds + MCP 3 tools listed & called; `find_exceptions`==`exceptions` `EQUAL` | — (advisory: no COVERAGE doc) |
| R4 | Functional coverage | **fail** | envelopes/ids verified faithful, but **no `docs/COVERAGE.md`** (R4.1) | Author machine-checkable `docs/COVERAGE.md` |
| R5 | Assessment-grade endpoints | **pass** | SQL query grammar over records = T2; 3 capabilities ≥3 criteria | (advisory: no bundled round-trip task) |
| R6 | Unit tests all surfaces | **fail** | **no `tests/` at all** | Add pytest: endpoint+CLI+MCP happy/error + parity + isolation |

### Canon + seeding parity grid (R2 detail) — a–i canon, j–k GHCR image DB seeding
| a | b | c | d | e | f | g | h | i | j | k |
|---|---|---|---|---|---|---|---|---|---|---|
| ⚠️ | ❌ | ⚠️ | ❌ | ⚠️ | ❌ | ✅ | ⚠️ | ❌ | ❌ | ❌ |

- **a (⚠️):** A gateway image exists but there is **no neutral `logfire-service` base** image; the
  Dockerfile bakes data directly (`COPY records.json /data/records.json`). Base-without-data role unmet.
- **b (❌):** No `:prod-v1` + `:empty` pair. Only `logfire-gateway:oddish-incident-534pm` (per-incident).
  `buildx imagetools inspect …:prod-v1` and `…:empty` → **not found** on GHCR.
- **c (⚠️):** Agent is **data-free** (`/data/records.json` absent → `SEALED`), but the agent image
  **carries the gateway's API source** (`/opt/logfire_clone/server.py` present). No separate seed
  generator and no data, so it is not an answer leak, but the API source is not stripped (R2.k tie-in).
- **d (❌):** Per-task data is delivered by **`COPY records.json` into a per-task gateway image**
  (`build.sh <records.json> <tag>`), not by mounting into an `:empty` gateway. The `:empty`+mount path
  does not exist.
- **e (⚠️):** Bulk = native JSON (`records.json`, good). No mutation op-list (clone is read-only by
  design — acceptable for a read-only telemetry API, but the canon "shared op-list" half is N/A-ish).
- **f (❌):** No Harbor 2-container task: no `docker-compose.yaml`, no `tests/test.sh`→`reward.txt`.
- **g (✅):** No world-building/seed entrypoint is on the agent's PATH (only `logfire` + `logfire-mcp`);
  seeding is a build-time `COPY` on the gateway, not agent-callable.
- **h (⚠️):** No identity registry wiring (advisory).
- **i (⚠️):** No skill/catalog/PROD-OVERLAY doc (advisory). No `docs/` dir at all.
- **j (❌):** The baked-DB *mechanism* works (the incident gateway boots mount-free, serves 3292
  records), **but there is no `:prod-v1` tag** baking the corpus per the contract — fails by name.
- **k (❌):** Both `logfire-gateway` and `logfire-agent` are **`linux/amd64`-only** (host-arm warning;
  `docker image inspect` → `linux/amd64`); no CI workflow declares multi-arch. **And** the agent image
  bundles the gateway API source (`server.py`) — not stripped to a neutral client. (Literal grep finds
  only source comments, not seeded answers, since no corpus/seed-generator ships in the agent; but the
  "strip the gateway API/seed source" rule is unmet.)

> **Auditor harness notes:** No standalone compose to merge — there is no Harbor task. I ran the
> gateway/CLI/MCP directly (local `python3.13` venv with `duckdb`+`mcp`, a 5-record synthetic
> `records.json`) to exercise the surface, and booted the local `logfire-gateway:oddish-incident-534pm`
> image mount-free to confirm the baked corpus (3292 records). amd64 emulation on the arm host adds
> ~9s corpus-load lag before `/health` answers — worth a healthcheck `start_period`.

### Coverage matrix audit (R4/R5 detail)
| Capability | Endpoint | CLI | MCP | Envelope OK | Assessment-grade | Tested |
|---|---|---|---|---|---|---|
| Arbitrary SQL over records | `POST /v2/query` | `logfire query <sql>` | `arbitrary_query` | ✅ `{schema,data}` | ✅ (stateful-read, multi-step, query grammar, realistic errors) | ❌ no tests |
| Recent exceptions | `POST /v2/query` (canned SQL) | `logfire exceptions` | `find_exceptions` | ✅ | ✅ (multi-step, query grammar, devops-investigation shape) | ❌ |
| Records schema | `POST /v2/query` (`limit 0`) | `logfire schema` | `get_logfire_records_schema` | ✅ `{schema.fields}` | ⚠️ (1–2 criteria) | ❌ |
| Health | `GET /health` | — | — | ✅ `{ok,records}` | — (operator) | ❌ |

**R5 assessment-grade tally:** `arbitrary_query` and `find_exceptions` each satisfy ≥3 of
{stateful-read, multi-step, realistic errors, query grammar, devops shape}. The **SQL query grammar**
(DuckDB `SELECT … WHERE … GROUP BY`, time-window scoping) is the discriminating surface — strong T2
signal. Meets the **small-clone ≥3** bar (here 2 strong + schema). **Gap:** R5.2's "≥1 write→read
round-trip exercised by a bundled task" is **N/A** — the clone is read-only and ships no task, so the
round-trip is replaced by a read-investigation chain; acceptable for a read-only telemetry clone but
there is no bundled task to demonstrate it.

## Action items (ordered, for the creator loop)
1. **[R1 · gating · P0]** Add the Harbor task scaffold. *Where:* new `environment/docker-compose.yaml`
   (agent `main` + `logfire` gateway, `depends_on` on a gateway healthcheck), `tests/test.sh` (writes
   `/logs/verifier/reward.txt`), `solution/solve.sh` (oracle). *Acceptance:* `docker compose up` reaches
   healthy and a bundled task scores **nop=0.0, oracle=1.0**.
2. **[R2.b/j · gating · P0]** Re-tag the gateway as the canon trio. *Where:* `build.sh` + CI. Produce
   `logfire-service:prod-v1` (corpus baked, boots mount-free) **and** `logfire-service:empty` (no data,
   mount target); switching tasks = tag swap. *Acceptance:* `…:prod-v1` boots with no mount and answers
   a seeded `POST /v2/query`; `…:empty` + a mounted `records.json` serves the mounted corpus.
3. **[R6 · gating · P0]** Add `tests/` (pytest). *Where:* new `tests/`. Cover **each** of `/v2/query`,
   `/health`, all 3 CLI commands, all 3 MCP tools — happy + ≥1 error path each; **parity** test
   (`exceptions`==`find_exceptions`, `schema`==`get_logfire_records_schema`); **isolation** test
   (`[ ! -e /data/records.json ]` in agent, state only over HTTP). *Acceptance:* `pytest -q` green from
   cold boot, wired into `test.sh`/CI; report `<passed>/<total>`.
4. **[R4 · gating · P1]** Add `docs/COVERAGE.md`. *Where:* new `docs/COVERAGE.md`. One row per capability
   → endpoint + CLI cmd + MCP tool + fidelity grade + assessment-grade label. *Acceptance:* matrix exists,
   machine-checkable, and matches the audited matrix above.
5. **[R2.k · gating · P1]** Image hygiene. *Where:* `Dockerfile.agent` + CI. (a) Build & publish both
   images **multi-arch** (`linux/amd64,linux/arm64`). (b) Strip the gateway API source from the agent —
   the agent only needs `cli.py`/`mcp_server.py`/`__init__.py`; `rm` `server.py` (or build the agent from
   a neutral base copying only the client + CLI + MCP). *Acceptance:* `buildx imagetools inspect` lists
   both arches; `docker run --rm <agent> sh -c '[ ! -e /opt/logfire_clone/server.py ]'` succeeds.
6. **[R2 · advisory · P2]** Add a gateway healthcheck with a `start_period` covering the corpus-load lag
   (~9s observed under amd64 emulation), so `depends_on: service_healthy` doesn't race the boot.

## Reproduction
```bash
# Surface exercised locally (no Harbor task exists to boot):
python3.13 -m venv venv && venv/bin/pip install 'duckdb>=1.0' mcp
LOGFIRE_RECORDS=records.json LOGFIRE_PORT=8771 LOGFIRE_TOKEN=test-token-acme-eval \
  venv/bin/python -m logfire_clone.server   # /health -> {"ok":true,"records":5}

# HTTP: happy, scoping, auth(401), read-only(400 INSERT/DROP), bad-sql(400), 404, /v1 alias  — all real envelopes
curl -s -X POST :8771/v2/query -H "Authorization: Bearer test-token-acme-eval" \
  -d '{"sql":"SELECT exception_type,count(*) n FROM records WHERE exception_type IS NOT NULL GROUP BY 1","min_timestamp":"2026-06-24T00:00:00Z"}'

# CLI: logfire {schema,exceptions,query}  (exit=1 + verbatim gateway error on bad SQL)
# MCP: stdio list_tools -> {arbitrary_query, find_exceptions, get_logfire_records_schema}; called each
# Parity: CLI `exceptions` == MCP `find_exceptions`  -> EQUAL

# Images (local, no GHCR prod-v1/empty):
docker image inspect ghcr.io/abundant-ai/logfire-gateway:oddish-incident-534pm --format '{{.Os}}/{{.Architecture}}'  # linux/amd64
docker run -d -p 8772:80 ghcr.io/abundant-ai/logfire-gateway:oddish-incident-534pm   # mount-free -> {"ok":true,"records":3292}
docker run --rm ghcr.io/abundant-ai/logfire-agent:latest sh -c '[ -e /data/records.json ] && echo LEAK || echo SEALED'  # SEALED
docker run --rm ghcr.io/abundant-ai/logfire-agent:latest sh -c 'ls /opt/logfire_clone/server.py'  # present (API source not stripped)
docker buildx imagetools inspect ghcr.io/abundant-ai/logfire-gateway:prod-v1   # not found
```
