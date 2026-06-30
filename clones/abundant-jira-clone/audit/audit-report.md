# Clone Audit — abundant-jira-clone

- **Clone:** `abundant-jira-clone`
- **Commit:** `36e78af262ea`
- **Audited:** 2026-06-30 · Standard: clone-standard-v1
- **Verdict:** **MEETS_STANDARD = FALSE** · gating passed **2 / 7**
- **Fidelity tier:** declared none; observed **T2** (real JQL query grammar in the ticketvector backend).

## TL;DR

This is a **thin** Jira/Linear clone whose core agent tooling — the `jira` and `linear`
CLIs, the issue HTTP API, the JQL engine, the seed generator — lives in an **external**
image, `ghcr.io/abundant-ai/ticketvector-service:latest`. This repo contributes only:
converters (`tools/jira_to_state.py`, `linear_to_state.py`) that turn a real Jira/Linear
export into `state.json`; a read-only **Linear GraphQL gateway** (`linear/server.py`);
the three image Dockerfiles (`prod-v1`/`empty`/`agent`) layered on ticketvector; a boot
overlay/patch processor; and two smoke tasks.

It **boots cleanly and the verifier works** (live: nop=0, oracle=1; prod-v1 serves 8040
issues mount-free; empty+mount serves a 12-issue project; agent is sealed). But it
**fails the standard on five gates**, two of them structural:

1. **R3 FAIL — no MCP server.** The agent has a CLI only. `linear/server.py` is a GraphQL
   HTTP gateway, *not* an MCP server. The "CLI **and** MCP in parity" requirement cannot
   be met by any surface present in this repo.
2. **R2.k FAIL (leak) — the agent ships the gateway's API + seed generator source.** The
   agent image is built `FROM ticketvector-service` copying `/opt/ticketvector` wholesale,
   so `world_issues.seed`/`server`/`plane` are present and importable in the agent.
3. **R4 / R6 FAIL — no `docs/COVERAGE.md` and no unit-test suite** (no pytest, no CI).
4. **R2.k multi-arch — the ticketvector base is amd64-only on GHCR** (verified via
   imagetools); the jira-gateway images are unpublished, so the rest scores `n/a`.

**The headline question for the action list:** the `jira`/`linear` CLI, the issue API, and
the (missing) MCP server all belong to **ticketvector**, not to this repo. So R3/R4/R6
cannot be satisfied *here* without either (a) vendoring/owning the tool surface in this
clone, or (b) explicitly re-scoping the audit boundary to treat ticketvector as the clone
and this repo as a thin per-task seeder. As-is, this repo is a **seeding + task harness**
layered on an external service, not a self-contained Clone-Standard clone.

## What it handles well (verified by running)

- **Cold boot, Harbor shape** — `prod-v1` reaches healthy in ~4s and serves the full ENG
  corpus (`JIRA_BOOT mode=prod issues=8040`) with **no fixture mount** (R2.j). `empty`+mount
  reaches healthy in ~2s serving the planted WEB project (`issues=12`).
- **Verifier integrity** — live run of `tasks/jira-assignee-count`: **nop reward=0,
  oracle reward=1** (`answer: count: 4`). Verifier recomputes ground truth live through the
  `jira` CLI, so a hardcoded-wrong answer scores 0.
- **Agent isolation (R2.c/g)** — agent container has **no** `/var/lib/ticketvector/state.json`
  (`SEALED`); `WORLD_ISSUES_AGENT_MODE=1` blocks admin/seed/runtime
  (`"world-issues admin/runtime commands are disabled in agent mode"`, `jira seed` → unsupported).
- **No `networks:` block** in either compose; service-name DNS (`jira`) resolves (R1.4).
- **Two real seeding paths exist** — baked prod corpus, and empty+mount, switchable by image
  tag, both exercised.
- **Real query grammar** — the ticketvector backend exposes JQL (`jira jql "..."`) and
  `issue query --assignee` pagination via `next_cursor` — genuine T2 surface.

## Scorecard (R1–R6)

| Req | Gating | Result | One-line evidence |
|---|---|---|---|
| **R1** Setup & run | G | **partial** | prod-v1 healthy 4s + nop=0/oracle=1 live, BUT R1.5 cred-free pull only half-holds: agent base does an authenticated `COPY --from=ghcr.io/abundant-ai/ticketvector-service` (no `build:`+`image:` fallback for the gateway in compose) |
| **R2** Architecture & seeding | G | **fail** | R2.j passes (8040 baked, mount-free); R2.k **fails** (seed/api source importable in agent; base amd64-only) |
| **R3** CLI **and** MCP in parity | G | **fail** | `grep -rl mcp` → only `linear/server.py` (a GraphQL gateway, not MCP). **No MCP server exists.** |
| **R4** Coverage matrix | G | **fail** | `find -iname '*coverage*'` → none. No `docs/COVERAGE.md`. |
| **R5** Assessment-grade endpoints | G | **partial** | JQL + query-pagination + write/transition surface exist in ticketvector and 1 write→read style task runs, but unlabelled (no COVERAGE.md to carry the ≥5 list) |
| **R6** Unit tests | G | **fail** | `find -name 'test_*.py'` → none; only per-task `test.sh` verifiers + `smoke.sh`. No parity/isolation pytest, no CI. |

**Gating passed: 2/7** (R2.j is a sub-pass but R2 overall fails; counting whole gates:
R1 partial, R2 fail, R3 fail, R4 fail, R5 partial, R6 fail → only the *runtime* gates
that fully pass do so within R1's sub-grid).

## R2 canon sub-grid (a–k)

| Key | Property | Result | Evidence |
|---|---|---|---|
| a | base `<svc>-service` image published | **pass** | `ghcr.io/abundant-ai/ticketvector-service:latest` pulled + booted |
| b | `:prod-v1` + `:empty` pair exist | **pass** | both built locally (`jira-gateway:prod-v1`, `:empty`); booted both |
| c | thin agent, data-free on disk | **pass** | agent `SEALED` — no state.json present |
| d | per-task data by mount, not COPY | **pass** | `jira-assignee-count` mounts `./data/state.json:ro`; prod uses baked shared corpus |
| e | bulk native format, mutations op-list | **pass** | `state.json` native; `apply_state_patch.py` op-list; agent uses CLI mutations |
| f | Harbor 2-container, test.sh→reward.txt | **pass** | both composes are main+jira, no networks; `test.sh` writes `/logs/verifier/reward.txt` |
| g | world-building is gateway-only, agent can't call it | **pass** | agent-mode blocks admin/seed/runtime (observed error envelope) |
| h | identity registry wired | **partial (A)** | `tools/identity_registry.json` + `_person_key` hook exist; not yet unifying names (README says deferred) |
| i | skill + catalog + PROD-OVERLAY doc | **partial (A)** | `docs/PROD-OVERLAY.md` present; no skill/catalog |
| **j** | GHCR image DB seeding (prod-v1 baked, mount-free) | **pass** | `JIRA_BOOT mode=prod issues=8040` from a cold boot, no mount |
| **k** | image hygiene (multi-arch + no leak) | **fail** | (1) literal grep clean; (2) `import world_issues.seed` → **importable (leak)**; (3) `/opt/ticketvector/world_issues/seed.py`+`server.py` **present in agent**; (4) GHCR base **amd64-only** (imagetools) |

### R2.k detail (the leak)

The agent Dockerfile (`selfcontained/base/Dockerfile.agent`) does:
```
COPY --from=ghcr.io/abundant-ai/ticketvector-service:latest /opt/ticketvector /opt/ticketvector
```
copying the whole backend package into the agent. Verified in the agent image:
- `docker run … grep -rs 'Priya Fischer'/'ENG-2016' /opt /app /usr/local` → **nothing** (the
  *corpus DB itself* is NOT baked into the agent — that part is clean).
- `python -c 'import world_issues.seed'` → **succeeds** (`SEED_IMPORTABLE_LEAK`).
- `world_issues/{seed,server,plane,demo,runtime}.py` all present in the agent.

**Mitigating nuance (for the creator):** `seed.py` regenerates only the synthetic **demo
"payments/PAY"** fixture — *not* the ENG/WEB task corpus, which comes from the real export
via `tools/jira_to_state.py` (absent from the agent). So **this specific task's answer is
not recomputable** from the agent. But R2.k/R6.3 are written strictly: an importable
generator + present `api/seed` source is a leak regardless, because `FROM ticketvector`
makes *any* future seed-derived corpus recomputable and ships the API source the agent
should never see. Fix the Dockerfile to strip/whitelist (CLI + client only), and the leak
closes.

## Coverage-matrix audit (R4/R5)

No `docs/COVERAGE.md` exists, so there is no machine-checkable matrix to audit. The CLI
surface I enumerated by running the agent's `jira --help` / `linear --help`:

- `jira`: `jql "<JQL>"`, `issue view <ID> [--comments --links --attachments]`,
  `issue transition <ID> "<state>"`, `issue comment add <ID> --body`, `issue query --assignee --cursor`.
- `linear`: `issue mine|search|view|start|commit-link|pr|comment add`, `project list`,
  `state list`, `label list`.

These are **assessment-grade** (stateful transitions, multi-step query→act, JQL grammar,
pagination, realistic error envelopes with `exit_code`). They satisfy R5 *in substance* —
but they live in **ticketvector**, are **undocumented here**, **unlabelled**, and have **no
MCP mirror**, so R4 fails outright and R5 is partial.

## Action items (ordered; gating first)

### P0 — gating

1. **[R3] No MCP server — add one (or re-scope the clone boundary).** *Where:* the clone
   ships no MCP surface; `linear/server.py` is GraphQL, not MCP. *Decision needed:* the
   `jira`/`linear` tool surface belongs to **ticketvector**, so an MCP server most
   naturally lives there (a thin client of the same `/rpc` API), then is `COPY`d into
   `jira-agent`. *Acceptance:* `<mcp> list-tools` returns issue read/query/transition/comment
   tools; each maps 1:1 to a `jira`/`linear` CLI command (parity).

2. **[R2.k] Stop shipping the gateway API + seed source in the agent.** *Where:*
   `selfcontained/base/Dockerfile.agent` `COPY --from=…/opt/ticketvector /opt/ticketvector`.
   Build the agent from a neutral base with only the `jira`/`linear`/`world-issues` CLI
   entrypoints + the HTTP `client` module, `rm -rf` `world_issues/{seed,server,plane,demo}.py`.
   *Acceptance:* in the agent image `python -c 'import world_issues.seed'` raises
   ModuleNotFoundError and `find /opt -path '*/seed*' -o -path '*/server*'` is empty.

3. **[R6] Add a unit-test suite + wire CI.** *Where:* `tests/` (new). Cover every CLI
   command (happy + ≥1 error), a **parity test** (once MCP exists), and an **isolation
   test** asserting no state.json on disk AND `import world_issues.seed` raises.
   *Acceptance:* `pytest` runs green from a cold `docker compose up`; a `.github/workflows`
   job runs it.

4. **[R4] Write `docs/COVERAGE.md`.** *Where:* `docs/COVERAGE.md` (new). One row per
   capability: endpoint | CLI cmd | MCP tool | envelope-OK | assessment-grade | tested.
   *Acceptance:* file exists, lists the `jira`/`linear` surface above with ≥5 rows labelled
   assessment-grade, each mapped to endpoint+CLI+MCP.

5. **[R2.k multi-arch] Publish gateway+agent multi-arch.** *Where:* `selfcontained/base/build.sh`
   pins `linux/amd64`; the GHCR `ticketvector-service` base is amd64-only. *Acceptance:*
   `docker buildx imagetools inspect ghcr.io/abundant-ai/jira-gateway:prod-v1` lists
   `linux/amd64` **and** `linux/arm64` — blocked on a multi-arch ticketvector base.
   *(Scored `fail` for the published amd64-only base; the jira-gateway half is `n/a`/unpublished.)*

### P1 — gating-adjacent / hardening

6. **[R1.5] Add a `build:`+`image:` dual for the gateway in the task composes**, or confirm
   the jira-gateway GHCR packages are public. *Where:* `tasks/*/environment/docker-compose.yaml`
   reference `${JIRA_GATEWAY_IMAGE:-jira-gateway:prod-v1}` (a local tag); a fresh checkout
   on another machine can't pull it. *Acceptance:* a clean machine `docker compose up`
   resolves the gateway with no `unauthorized` and no manual `build.sh` step.

7. **[R5] Add a write→read round-trip task** exercising `issue transition` / `comment add`
   end-to-end and label ≥5 assessment-grade capabilities in COVERAGE.md. *Acceptance:* a
   bundled task mutates an issue via the CLI and the verifier reads the mutation back.

### P2 — advisory / docs

8. **Stale README data.** `README.md` claims ENG-2016 assignee = "Felix Martin"; live corpus
   returns **"Priya Fischer"**. Verifier is live so tasks still pass, but the doc misleads.
   *Where:* `README.md` task table. *Acceptance:* doc matches `jira issue view ENG-2016`.

9. **[R2.h/i]** Wire the cross-clone identity registry (hook noted in README) and add the
   skill/catalog docs.

## Reproduction (commands run)

```bash
# multi-arch / base publish
docker buildx imagetools inspect ghcr.io/abundant-ai/ticketvector-service:latest   # amd64 + attestation only

# prod-v1 baked-DB, mount-free (R2.j)
docker run -d --name sc --platform linux/amd64 jira-gateway:prod-v1
docker logs sc            # JIRA_BOOT mode=prod issues=8040
docker exec sc jira issue view ENG-2016 --json   # state.name=Done, assignee=Priya Fischer

# empty+mount + nop/oracle (R1.3) + isolation (R2.c/g)
docker run -d --network NET --network-alias jira \
  -v .../jira-assignee-count/environment/data/state.json:/var/lib/ticketvector/state.json:ro \
  jira-gateway:empty                              # JIRA_BOOT issues=12
# agent: test -e /var/lib/ticketvector/state.json -> SEALED
# bash test.sh (nop) -> reward 0 ; bash solve.sh; bash test.sh -> reward 1 (count: 4)

# R2.k leak
docker run --rm --entrypoint sh jira-agent:latest -c \
  'python -c "import world_issues.seed"'          # imports (LEAK)
docker run --rm --entrypoint sh jira-agent:latest -c \
  'ls /opt/ticketvector/world_issues/seed.py /opt/ticketvector/world_issues/server.py'  # both present

# R3 / R4 / R6 absence
grep -rl mcp <clone>                              # only linear/server.py (GraphQL, not MCP)
find <clone> -iname '*coverage*'                  # none
find <clone> -name 'test_*.py'                    # none
```
