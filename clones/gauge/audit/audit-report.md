# Clone Audit Report — `gauge`

- **Audited:** `2026-06-30` · **Auditor:** `clone-audit v1` · **Commit:** `36e78af`
- **Fidelity tier (declared / observed):** `T2` / `T2` (handwritten stdlib HTTP + embedded PromQL/LogQL-style query engine over JSON state)
- **Verdict:** ❌ FAILS — *(meets = all gating reqs pass)*
- **Gating score:** `3 / 6` gating requirements pass (R3, R4, R5 pass; R1, R2, R6 fail).

## TL;DR
Gauge is a zero-dependency, stdlib-only Grafana/Prometheus/Loki clone (`http.server` + a JSON state
file) with two agent-facing tools — `gcx` (CLI) and `mcp-grafana` (24-tool stdio MCP server) — plus a
`gaugectl` admin CLI. Its **tool surface is excellent**: CLI and MCP are tight thin clients of one
HTTP API, in parity, with a real PromQL/LogQL-ish query grammar and a working annotation write→read
round-trip — easily clearing R3/R4/R5. It is **not Harbor-ready**, though: there is **no bundled task**
(`tests/test.sh`, `solution/solve.sh` absent → no nop=0/oracle=1), and it ships **only the empty+mount
seeding path** — there is no `:prod-v1`/`:empty` image trio, no baked-DB image, the GHCR image is
**amd64-only**, and the agent image carries the **full `gauge/server/` API source** (importable). The
single most important action item is to **add the `:prod-v1` baked-DB image (R2.b/j) and bundle a
nop/oracle task (R1.3)**.

## What it handles well
- **CLI + MCP parity over one HTTP API (R3).** `gcx dashboards search payment --json` and MCP
  `search_dashboards{query:"payment"}` return byte-identical dashboard records; both are thin clients
  of the same `gauge.cli.client` → HTTP API (verified by running each against a live server).
- **Real query grammar (R5, T2).** `gcx metrics query -d prom-payments 'sum by (status_code)(increase(...[5m]))'`
  and `gcx logs query -d loki-payments '{service="payments"} |= "lock_conflict"'` both evaluate against
  the embedded engine (`gauge/server/query_engine.py`) and return Grafana-shaped envelopes.
- **Write→read round-trip (R5.2 shape).** `gcx annotations create … ` returns `id:1`; a follow-up
  `gcx annotations list` reads it back; `gaugectl mutations` shows the `annotation.create` op-log entry.
- **Realistic error envelopes (R5).** `gcx datasources get nonexistent-ds` → `Not found`, exit `2`;
  MCP `get_datasource{uid:"nope"}` → `isError:true "Not found"`; MCP bad-arg → JSON-RPC `-32602`.
- **Clean agent isolation at runtime (R2.c/g).** In the task-pack agent container: no seed on disk
  (`[ ! -e /data/gauge/state.json ]` → SEALED), `gaugectl` absent, answer not literally greppable.
- **Read-only MCP mode** (`mcp-grafana --disable-write` hides `create_annotation`) — a nice control for
  read-investigation tasks.
- **Green unit suite**: `26 passed` from a clean `pip install -e ".[dev]"` (Python 3.13).

## Scorecard

| Req | Area | Result | Evidence | Action item (if not full pass) |
|---|---|---|---|---|
| R1 | Setup & run (Harbor) | **fail** | agent→gateway HTTP works (`gcx dashboards search` via `http://gauge`), gateway healthy; but **no `tests/test.sh` / `solution/solve.sh`** → nop/oracle unmeasurable | Bundle a task with `test.sh`→`reward.txt` + oracle; prove nop=0/oracle=1 |
| R2 | Architecture canon a–g + seeding j–k | **fail** | `:prod-v1`/`:empty` ABSENT on GHCR; no baked-DB Dockerfile; GHCR `:main` amd64-only; agent ships full `gauge/server/` source | Add image trio + baked-DB prod-v1; multi-arch; strip server source from agent |
| R3 | CLI + MCP parity | **pass** | 24 MCP tools listed; `search_dashboards` MCP == `gcx dashboards search` output; both → one HTTP API | — |
| R4 | Functional coverage | **partial→pass(behavior)** | every CLI group + 24 MCP tools map to real `/api/*` endpoints; envelopes Grafana-shaped. **`docs/COVERAGE.md` missing** | Add machine-checkable `docs/COVERAGE.md` |
| R5 | Assessment-grade endpoints | **pass** | ≥6 assessment-grade caps (PromQL, LogQL, alert instances, annotation RT, panel-query, label-values); 1 write→read RT exercised | — |
| R6 | Unit tests all surfaces | **partial** | `26 passed`; broad CLI/MCP/endpoint coverage **but no in-process parity test, no importable-generator isolation test**; docker isolation tests gated off by default | Add R6.2 parity + R6.3 isolation (import raises) tests |

### Canon + seeding parity grid (R2 detail) — a–i canon, j–k GHCR image DB seeding
| a | b | c | d | e | f | g | h | i | j | k |
|---|---|---|---|---|---|---|---|---|---|---|
| ✅ | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ⚠️ | ⚠️ | ❌ | ⚠️ |

Why:
- **a ✅** base `gauge-service` image published (`ghcr.io/abundant-ai/gauge-service:main`, pullable).
- **b ❌** no `:prod-v1` + `:empty` pair — `docker manifest inspect …:prod-v1` and `:empty` both ABSENT; repo defines only `:main`.
- **c ✅** agent thin + data-free (SEALED, no seed file; built on `python:3.10-slim`).
- **d ✅** per-task data by **mount** into the gateway (`./data/gauge/state.json:…:ro`), never `COPY`d into a per-task image.
- **e ✅** bulk = native JSON state; mutations recorded in a shared op-list (`mutation_log`, visible via `gaugectl mutations`).
- **f ⚠️** 2-container agent+gateway shape is correct, but **no `test.sh`→`reward.txt`** verifier wired and no documented isolation exception → the Harbor-task half is incomplete.
- **g ✅** world-building is gateway-only: seed load happens in `gauge.server.state`/`clone_admin` inside the gateway; `gaugectl` + `GAUGE_ADMIN_TOKEN` are not on the agent.
- **h ⚠️** no identity registry (`abundant-identity`) wiring — users are inline in state (advisory).
- **i ⚠️** docs present (TOOLS/API_COMPATIBILITY/CREATING-TASKS/IMAGE-RELEASE/STATE_SCHEMA) but **no `COVERAGE.md`** and no PROD-OVERLAY (advisory).
- **j ❌** **no GHCR image DB seeding** — there is no `:prod-v1` that bakes the corpus; the only seed path is empty-image + mounted `state.json`. Switching `empty↔prod-v1` by tag alone is impossible.
- **k ⚠️** partial: GHCR `:main` is **amd64-only** (`docker manifest inspect` → `linux/amd64` + attestation only; CI declares no `platforms:`) → multi-arch FAIL; **and** the agent image copies `/opt/gaugecli` wholesale, so the full `gauge/server/` **API source is present and `import gauge.server.state` succeeds** in the agent (violates the "strip api/seed source" rule). **Mitigated:** no baked corpus and no deterministic *generator* exist, so the answer is neither greppable nor recomputable from the agent — the data lives only on the gateway mount. Scored ⚠️ (hygiene gap, not an exploitable leak).

> **Auditor harness notes:** Two reconstructions were needed. (1) The shared docker host had a
> **compose-project-name collision** — `examples/task-pack-compose` defaults to project
> `task-pack-compose`, which a parallel **sentry** audit was also using, so the gauge agent container
> came up on `sentry-clone-task-agent:local` and stuck in `Created`. Re-running with `-p gaugeaudit`
> isolated it. (2) Several **stray local images** exist on the host (`gauge-gateway:superset-prod`,
> `gauge-service:fixed`, `gauge-agent:local`) that are **not referenced by any Dockerfile/compose/CI in
> this repo** — they are leftovers from other experiments, not part of this clone's canon. The repo's
> own R2 surface is strictly `:main` + mount.

### Coverage matrix audit (R4/R5 detail) — filled by calling each tool against a live server
| Capability | Endpoint | CLI | MCP | Envelope OK | Assessment-grade | Tested |
|---|---|---|---|---|---|---|
| current user | `GET /api/user` | `gcx whoami` | — (no MCP) | ✅ | — | ✅ |
| dashboard search | `GET /api/search` | `gcx dashboards search` | `search_dashboards` | ✅ | — | ✅ |
| dashboard get | `GET /api/dashboards/uid/{uid}` | `gcx dashboards get` | `get_dashboard_by_uid` | ✅ | — | ✅ |
| dashboard summary | (derived) | `gcx dashboards summary` | `get_dashboard_summary` | ✅ | — | ✅ |
| dashboard panels | (derived) | `gcx dashboards panels` | `get_dashboard_panel_queries` | ✅ | — | ✅ |
| dashboard variables | (derived) | `gcx dashboards variables` | `get_dashboard_variables` | ✅ | ⚠️ multi-step | ✅ |
| panel query exec | `POST /api/ds/query` | `gcx dashboards query-panel` | `run_dashboard_panel_query` | ✅ | ✅ stateful+multi-step | ✅ |
| datasource list/get/health | `GET /api/datasources[...]` | `gcx datasources …` | `list_datasources`/`get_datasource` | ✅ | — | ✅ |
| PromQL query | `POST /api/ds/query` | `gcx metrics query` | `query_prometheus` | ✅ | ✅ query grammar | ✅ |
| Prom labels/values | `POST /api/ds/query` | `gcx metrics labels/label-values` | `list_prometheus_label_*` | ✅ | ⚠️ multi-step | ✅ |
| LogQL query | `POST /api/ds/query` | `gcx logs query` | `query_loki_logs` | ✅ | ✅ query grammar | ✅ |
| Loki labels/values | `POST /api/ds/query` | `gcx logs labels/label-values` | `list_loki_label_*` | ✅ | ⚠️ multi-step | ✅ |
| alert rules list/get | `GET /api/alert-rules[/{uid}]` | `gcx alert rules …` | `alerting_list_rules`/`get_rule` | ✅ | ✅ filter by state | ✅ |
| alert instances | `GET /api/alert-instances` | `gcx alert instances list` | `alerting_list_instances` | ✅ | ✅ multi-step+filter | ✅ |
| alert state history | `GET /api/alert-rules/{uid}/history` | `gcx alert history` | `alerting_get_state_history` | ✅ | ✅ devops shape | ✅ |
| annotations list | `GET /api/annotations` | `gcx annotations list` | `get_annotations` | ✅ | — | ✅ |
| **annotation create** | `POST /api/annotations` | `gcx annotations create` | `create_annotation` | ✅ | ✅ **write→read RT** | ✅ |
| deeplinks | (computed) | `gcx links dashboard/panel/explore` | `generate_deeplink` | ✅ | — | ✅ |
| query examples | (static) | — | `get_query_examples` | ✅ | — | ✅ |

Counts: **~19 capabilities**, **18 with CLI**, **18 with MCP** (whoami is CLI-only; query-examples is
MCP-only — both minor, not gating). Parity verified on the calls run. **≥6 assessment-grade**, **1
write→read round-trip** exercised. Comfortably clears R5.1 (≥5) and R5.2.

## Action items (ordered, for the creator loop)
1. **[R2 · gating · P0]** Add the **`:prod-v1` baked-DB image** (and `:empty`).
   *Where:* new `Dockerfile.prod-v1` (or build arg) that `COPY`s a corpus `state.json` to
   `GAUGE_STATE_FILE` and boots healthy with **no mount**; CI tags `:prod-v1`/`:empty`.
   *Acceptance:* `docker compose up` of `:prod-v1` with no volume answers
   `gcx dashboards search payment --json` with corpus data; `docker manifest inspect …:prod-v1` exists.
2. **[R1 · gating · P0]** Bundle at least one **Harbor task** with `tests/test.sh` (writes
   `/logs/verifier/reward.txt`) and `solution/solve.sh`.
   *Where:* `tests/test.sh`, `solution/solve.sh`, task `environment/docker-compose.yaml`.
   *Acceptance:* nop run → `reward.txt` = `0.0`; oracle (`solve.sh`) → `1.0`.
3. **[R2.k · gating · P0]** Publish the gateway **multi-arch** and **strip the gateway API/seed source
   from the agent image**.
   *Where:* CI `build-push-action` add `platforms: linux/amd64,linux/arm64`; agent Dockerfile copy only
   `gcx`/`mcp-grafana` + the client module (or `rm -rf /opt/gaugecli/gauge/server` after copy).
   *Acceptance:* `docker manifest inspect …:prod-v1` lists amd64+arm64; in the agent
   `python -c 'import gauge.server.state'` raises `ModuleNotFoundError` and `find /opt -path '*/server/*'`
   is empty.
4. **[R6 · gating · P1]** Add **parity tests (R6.2)** and an **importable-generator isolation test
   (R6.3)** that run by default.
   *Where:* `tests/test_parity.py` (assert `gcx … --json` == matching MCP tool output per capability);
   `tests/test_isolation.py` (assert no seed on disk + `import gauge.server.state` raises in the agent
   image / `--disable-write` filters writes). Don't gate the isolation assertions behind
   `GAUGE_RUN_DOCKER_SMOKE`.
   *Acceptance:* `pytest -q` runs the new tests green without `GAUGE_RUN_DOCKER_SMOKE=1`.
5. **[R4 · advisory · P2]** Add **`docs/COVERAGE.md`** — the machine-checkable matrix (capability →
   endpoint → CLI → MCP → fidelity → assessment-grade).
   *Where:* `docs/COVERAGE.md`. *Acceptance:* file exists and every row maps to a real endpoint + CLI +
   MCP tool (or N/A with reason); ≥5 rows flagged assessment-grade.

## Reproduction
```bash
# Unit suite (R6) — clean install, no docker
python3.13 -m venv /tmp/gauge-venv && /tmp/gauge-venv/bin/pip install -e ".[dev]"
/tmp/gauge-venv/bin/python -m pytest tests -q          # -> 26 passed

# Local server (R3/R4/R5) — stdlib only, no docker
cp examples/data/gauge/state.json /tmp/gauge-state.json
GAUGE_STATE_FILE=/tmp/gauge-state.json GAUGE_RUNTIME_STATE_FILE=/tmp/gauge-runtime.json \
  GAUGE_ENABLE_ADMIN_API=1 GAUGE_ADMIN_TOKEN=admintok GAUGE_BIND_HOST=127.0.0.1 GAUGE_PORT=8799 \
  /tmp/gauge-venv/bin/python -m gauge.server.app &
export GRAFANA_URL=http://127.0.0.1:8799 GRAFANA_TOKEN=test-token-acme-eval PATH=/tmp/gauge-venv/bin:$PATH
gcx whoami --json; gcx dashboards search payment --json
gcx metrics query -d prom-payments 'sum by (status_code)(increase(payment_gateway_responses_total{service="payments"}[5m]))' --since 1h --step 5m --json
gcx logs query -d loki-payments '{service="payments"} |= "lock_conflict"' --since 1h --limit 20 --json
gcx datasources get nonexistent-ds --json            # -> 'Not found', exit 2
gcx annotations create --dashboard dash-payment-webhooks --panel 1 --text "audit round-trip" --tags audit,OPS-1 --json
gcx annotations list --dashboard dash-payment-webhooks --json   # reads the write back
# MCP: stdio client -> 24 tools listed; search_dashboards == gcx output; get_datasource{bad} -> isError

# Standup (R1/R2) — docker, isolated project name to avoid shared-host collision
docker build -f Dockerfile.service -t gauge-service:local .
docker compose -p gaugeaudit -f examples/task-pack-compose/docker-compose.yaml up -d --build
docker compose -p gaugeaudit -f examples/task-pack-compose/docker-compose.yaml exec -T agent gcx dashboards search payment --json
docker compose -p gaugeaudit -f examples/task-pack-compose/docker-compose.yaml exec -T agent sh -c '[ ! -e /data/gauge/state.json ] && echo SEALED'   # SEALED
docker compose -p gaugeaudit -f examples/task-pack-compose/docker-compose.yaml exec -T agent python -c 'import gauge.server.state; print("IMPORTABLE")'  # IMPORTABLE (k gap)
docker manifest inspect ghcr.io/abundant-ai/gauge-service:main      # linux/amd64 only
docker manifest inspect ghcr.io/abundant-ai/gauge-service:prod-v1   # ABSENT (b/j fail)
docker compose -p gaugeaudit -f examples/task-pack-compose/docker-compose.yaml down -v
```
