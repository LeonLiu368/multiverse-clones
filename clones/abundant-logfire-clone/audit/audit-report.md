# Clone Audit Report — `abundant-logfire-clone` (RE-AUDIT)

- **Audited:** `2026-06-30` · **Auditor:** `clone-audit v1` · **Commit:** `b2b2abd`
- **Fidelity tier (declared / observed):** `T2` / `T2` — real DuckDB SQL query grammar over a `records` table
- **Verdict:** ✅ MEETS STANDARD — *(meets = all gating reqs pass)*
- **Gating score:** `6 / 6` gating requirements pass (R1, R2, R3, R4, R5, R6).

## TL;DR
Re-audit after the fix pass. The Round-1 blockers (R1, R2, R4, R6) are all **independently
confirmed fixed** — nothing taken on the fixer's word. The clone is now a complete
Clone-Standard task: a canon docker trio (`base` → `:empty` + `:prod-v1`) plus a matched
data-free agent, a real Harbor/Oddish task (`oddish/tasks/logfire-incident-rca/`) that boots
the agent+gateway pair and scores **nop=0 / oracle=1**, a machine-checkable `docs/COVERAGE.md`,
and a **23/23-green** pytest suite covering every endpoint, CLI command, MCP tool, parity, and
isolation. R3/R5 (Round-1 passes) still hold. One non-gating P2 remains (verify GHCR tags
resolve once published).

## What it handles well
- **`:prod-v1` bakes the corpus and boots mount-free.** `docker run :prod-v1` (no mount) →
  `/health` `{"ok":true,"records":3292}`; seeded `POST /v2/query` for the incident exception
  count returns `60`. `:empty` + a bind-mounted `records.json` serves the mounted corpus.
  Switching is the **image tag alone** (entrypoint prefers `$LOGFIRE_BAKED`, else mounted
  `$LOGFIRE_RECORDS`; server transparently gunzips a `.gz` corpus).
- **Agent is sealed.** `import logfire_clone.server` → `ModuleNotFoundError`; the agent package
  is `__init__ + cli + mcp_server` only (no `server.py`); the answer literals
  (`asyncpg.exceptions.UndefinedColumnError`, `locked_at`) are not greppable under `/opt`
  or `/usr/local`; no `/data/records.json[.gz]` on the agent. State is reachable only over HTTP.
- **The Harbor task is real and non-hackable.** Gateway reaches `Healthy`, agent reaches it by
  name (`curl http://logfire:80/health`), no `networks:` block. The verifier grades in a
  verifier-owned `/tmp` dir (not `/workspace`) against a hidden exact-value grader. Measured
  **nop=0** (untouched workspace) and **oracle=1** (after `solve.sh`).
- **Faithful Query API + thin CLI/MCP in parity.** `POST /v2/query` returns the real
  `{schema:{fields:[{name,data_type}]}, data:[…]}`; real error envelopes (401 `{detail}`,
  400 `{error[,details]}`, 404). CLI and MCP both route through `cli.query`; parity asserted
  by green tests.

## Scorecard

| Req | Area | Result | Evidence | Action item (if not full pass) |
|---|---|---|---|---|
| R1 | Setup & run (Harbor) | **pass** | pair boots healthy; agent→gateway by name; no real `networks:`; nop=0, oracle=1 (reward.txt) | — |
| R2 | Architecture canon a–g + seeding j–k | **pass** | trio builds; `:prod-v1` mount-free `/health`=3292 + query=60; `:empty`+mount works; agent sealed (no server.py, import raises, not greppable); CI declares multi-arch | (P2) verify GHCR tags resolve once published |
| R3 | CLI + MCP parity | **pass** | 3 CLI cmds + 3 MCP tools, all thin clients; `test_parity_exceptions`/`test_parity_schema` green | — |
| R4 | Functional coverage | **pass** | `docs/COVERAGE.md` machine-checkable matrix; envelopes/errors verified | — |
| R5 | Assessment-grade endpoints | **pass** | 3 assessment-grade (small-clone ≥3); round-trip = bundled RCA read-investigation chain (nop=0/oracle=1) | — |
| R6 | Unit tests all surfaces | **pass** | **23/23 green from cold**; endpoint+CLI+MCP happy/error + parity + isolation | — |

### Canon + seeding parity grid (R2 detail)
| a | b | c | d | e | f | g | h | i | j | k |
|---|---|---|---|---|---|---|---|---|---|---|
| ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | n/a | ✅ | ✅ | ✅ |

- **a/b:** Neutral `base` image (no data) → `:empty` (mount target) + `:prod-v1` (corpus baked).
- **c/g:** Agent data-free and seed-free; no `server.py`/API source.
- **d:** Per-task data delivered by baked corpus (prod-v1 task) or `:empty`+mount — not a
  per-task COPY into a bespoke image. The task bakes `corpus/records.json.gz` (prod-v1 contract).
- **e:** Bulk = native JSON (`records.json[.gz]`). Read-only clone → mutation op-list N/A.
- **f:** Two-container Harbor task with `build:`+`image:` gateway, healthcheck, `depends_on`.
- **j:** `:prod-v1` boots mount-free serving the full 3292-record corpus. **Confirmed.**
- **k:** Multi-arch declared in CI (`linux/amd64,linux/arm64`); leak checks clean. Local builds
  are single-arch (accepted per hardened R2.k).
- **h:** No identity registry needed for a telemetry read API (n/a). **i:** `docs/COVERAGE.md` present.

### Coverage matrix audit (R4/R5 detail)
| Capability | Endpoint | CLI | MCP | Envelope OK | Assessment-grade | Tested |
|---|---|---|---|---|---|---|
| Arbitrary SQL over records | `POST /v2/query` | `logfire query <sql>` | `arbitrary_query` | ✅ `{schema,data}` | ✅ (stateful, errors, grammar, devops) | ✅ |
| Recent exceptions | `POST /v2/query` (canned) | `logfire exceptions` | `find_exceptions` | ✅ | ✅ (multi-step, grammar, investigation) | ✅ |
| Records schema | `POST /v2/query` (`limit 0`) | `logfire schema` | `get_logfire_records_schema` | ✅ `{fields}` | ✅ (investigation entry; chains to query) | ✅ (parity) |
| Auth / read-only / validation | `POST /v2/query` (errors) | (exit 1) | (raises) | ✅ 401/400/404 | ✅ (real error envelopes) | ✅ |
| Health | `GET /health` | — | — | ✅ `{ok,records}` | — (operator) | ✅ |

**R5 tally:** 3 assessment-grade capabilities — meets the small-clone ≥3 bar. The SQL query
grammar is the discriminating T2 surface. R5.2 write→read round-trip is N/A (read-only Query
API), replaced end-to-end by the bundled `logfire-incident-rca` read-investigation chain.

## Round-1 → Round-2 (confirm/deny per previously-failing gate)
- **R1 (was fail):** CONFIRMED FIXED. Task exists; pair boots healthy; nop=0/oracle=1 measured.
- **R2 (was fail):** CONFIRMED FIXED. `:prod-v1`/`:empty` trio + sealed agent; mount-free baked
  boot serves 3292; multi-arch declared in CI.
- **R4 (was fail):** CONFIRMED FIXED. `docs/COVERAGE.md` machine-checkable matrix present.
- **R6 (was fail):** CONFIRMED FIXED. 23/23 pytest green from cold.
- **Regressions:** none — R3 and R5 still pass (parity tests green; assessment-grade matrix intact).

## Reproduction
```bash
cd clones/abundant-logfire-clone
# 1) build the trio + agent (clone-scoped tags)
docker build -t logfirere/logfire-service:base    -f docker/Dockerfile .
docker build -t logfirere/logfire-service:empty   -f docker/Dockerfile.empty   --build-arg BASE=logfirere/logfire-service:base .
docker build -t logfirere/logfire-service:prod-v1 -f docker/Dockerfile.prod-v1 --build-arg BASE=logfirere/logfire-service:base .
docker build -t ghcr.io/abundant-ai/logfire-agent:latest -f docker/Dockerfile.agent .

# 2) R2.j prod-v1 mount-free
docker run -d --name lf_prod -p 18080:80 logfirere/logfire-service:prod-v1
curl -s localhost:18080/health   # {"ok":true,"records":3292}

# 3) R2 agent seal
docker run --rm ghcr.io/abundant-ai/logfire-agent:latest python -c "import logfire_clone.server"  # ModuleNotFoundError

# 4) R1 boot pair + nop/oracle
cd oddish/tasks/logfire-incident-rca/environment
export COMPOSE_PROJECT_NAME=logfirere
docker compose -f docker-compose.yaml \
  -f ../../../../../skills/clone-audit/assets/harbor-main-build.override.yaml up --build -d
#   (nop: bash tests/test.sh -> reward.txt=0; oracle: solution/solve.sh then test.sh -> reward.txt=1)

# 5) R6 unit suite from cold
python3.13 -m venv /tmp/lfvenv && /tmp/lfvenv/bin/pip install duckdb mcp pytest
/tmp/lfvenv/bin/python -m pytest tests/   # 23 passed
```

> **Auditor harness notes:** Docker shared host, `COMPOSE_PROJECT_NAME=logfirere`, clone-scoped
> image tags. Isolation tests expect `ghcr.io/abundant-ai/logfire-agent:latest`; I tagged the
> locally-built agent to that name so the 4 isolation tests ran (not skipped). arm64 host; local
> builds single-arch — multi-arch is a CI declaration (accepted per hardened R2.k). `main` has no
> long-running CMD (Harbor keeps it alive), so for the live agent probes I ran the built agent
> image with `sleep infinity` on the compose network; nop/oracle were measured inside it via the
> task's own `tests/test.sh` + `solution/solve.sh`.
