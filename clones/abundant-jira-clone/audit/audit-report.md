# Clone Audit (RE-AUDIT, round 2) — abundant-jira-clone

- **Clone:** `abundant-jira-clone`
- **Commit:** `b2b2abd`
- **Audited:** 2026-06-30 · Standard: clone-standard-v1
- **Verdict:** **MEETS STANDARD** — gating **7 / 7** (round-1 was 2/7)
- **Fidelity:** declared T2, observed T2
- **Docker:** shared daemon; ran with clone-specific tags (`jira-agent:jirare-audit`, `jirare-rt-*`, network `jirare-net`); all temp containers/images/network cleaned up.

## TL;DR

Round-1 failed 2/7 (no MCP, the `world_issues.seed` leak in the agent, no COVERAGE.md, no
pytest). The fixer made an explicit **boundary decision** (`docs/PROD-OVERLAY.md`): this repo is
*"the jira/linear tooling layered on the external ticketvector engine"* — the `/rpc` API + JQL +
seed generator live in `ghcr.io/abundant-ai/ticketvector-service`; this repo owns the converters,
the image-trio Dockerfiles, the tasks, **and now the MCP server + agent hardening**. I independently
ran every previously-failing gate. **The boundary decision genuinely satisfies R3/R4/R6 in this
repo**, and the R2.k leak is closed. The only residual is the multi-arch publish, which I confirmed
is an **upstream** ticketvector blocker (amd64-only base) — per the brief, not grounds to fail.

## Per-requirement (re-)confirmation

### R3 — MCP server + CLI↔MCP parity — round-1 FAIL → **CONFIRMED PASS**
A real `mcp/` server now exists (`server.py` + self-contained `client.py` + `jql.py`). It is a thin
`/rpc` client and **imports nothing from `world_issues`** — verified by running it *inside the
stripped agent image* where `world_issues.server/seed` are gone.
- Tool count: **11** (matches claim).
- Evidence (live, against `jira-gateway:empty` + WEB fixture):
  - `tools/list` → 11 tools.
  - `search_issues(limit=3)` → `[WEB-1, WEB-10, WEB-11]`; `get_issue(WEB-1)` → state Done, assignee priya.singh.
  - **write round-trip:** `transition_issue(WEB-1,"In Progress")` then `get_issue` → readback `In Progress`.
  - **CLI↔MCP parity, head-to-head:** `jira project list`==`list_projects`; JQL `priority in (high,medium)` ids + `next_cursor` identical; `jira issue query --assignee priya.singh`==`search_issues(assignee=...)`; `jira issue view WEB-1`==`get_issue` on identifier/state/assignees/priority/title/labels. All `True`.
  - In-suite `test_parity.py` (8 tests) all **RAN and passed** (not skipped — the upstream CLI was extracted from the service image and compared).
- In the agent image: `JIRA_MCP_FORCE_FALLBACK=1 python3 -c '... server.TOOL_NAMES'` → 11 tools.

### R2.k — agent leak (the round-1 headline) — round-1 FAIL → **CONFIRMED PASS** (single-arch)
`Dockerfile.agent` no longer ships the gateway wholesale: it COPYs the package then runs
`strip_agent_tooling.py` (deletes `server/seed/plane/demo/runtime/snapshot.py`, rewrites `cli.py`
imports to raising shims). The build itself asserts the strip worked (lines 32-34). Verified on a
**fresh rebuild** (`jira-agent:jirare-audit`):

| Probe | Command | Result |
|---|---|---|
| seed RAISES | `python3 -c 'import world_issues.seed'` | `ModuleNotFoundError` ✓ |
| server/plane/demo/runtime/snapshot RAISE | same per module | all `ModuleNotFoundError` ✓ |
| no seed/server source | `find /opt -name seed.py -o -name server.py ...` | empty (only `END`) ✓ |
| no state.json | `test -e /var/lib/ticketvector/state.json` | `SEALED` ✓ |
| answer not greppable | `grep -rl 'Priya Fischer' /opt /var /workspace /usr`; same for `ENG-2016` | no hits ✓ |
| tools retained | `import world_issues.cli`; `command -v jira` | CLI_OK ✓ |

**Multi-arch half:** `docker buildx imagetools inspect ticketvector-service:latest` → `linux/amd64`
only (second manifest is an attestation, not arm64). So the arm64 leg **cannot** be produced from
this repo → scored `n/a (unverified)`, owned upstream. Not failing the clone on this alone.

### R4 — COVERAGE.md — round-1 FAIL → **CONFIRMED PASS**
`docs/COVERAGE.md` is a machine-checkable matrix: 14 rows (capability → `/rpc` method → CLI → MCP →
R/W → envelope → assessment-grade → tested), all 14 with CLI+MCP, **5 labelled assessment-grade**
(JQL, issue query+pagination, transition, add comment, get issue) with the ≥3-of-5 criteria table,
plus an explicit out-of-scope list. Consistent with observed behavior.

### R6 — pytest incl parity + isolation — round-1 FAIL → **CONFIRMED PASS**
`pytest -v` against a freshly booted `jira-gateway:empty` + WEB fixture: **38 passed, 0 skipped, 0
failed**. Per-file dot-progress: `test_isolation.py ..........` (10), `test_mcp_tools.py
....................` (20), `test_parity.py ........` (8). Parity and isolation tests genuinely ran.
CI workflow (`.github/workflows/ci.yml`) builds the trio + runs pytest on push/PR; publish job is
multi-arch with arm64 `continue-on-error`.

### R1 — regression (nop=0/oracle=1) — **STILL HOLDS**
Reconfirmed live on the new `jira-transition-roundtrip` task (gateway sidecar on `jirare-net`, agent
built FROM `jira-agent:latest`):
- **nop** (empty `answer.txt`, no mutation) → verifier reads `state='To Do', comments=0` → `reward=0`.
- **oracle** (`solve.sh`: `jira issue transition WEB-7 Done` + `jira issue comment add` over HTTP) →
  verifier reads `state='Done', comments=1, answer=WEB-7` → `reward=1`.

### R5 — assessment-grade + write→read task — round-1 PARTIAL → **PASS**
≥5 assessment-grade capabilities documented; the bundled `jira-transition-roundtrip` task is a real
write→read round-trip (oracle reward=1 above proves the write is observed on a later read through
the same API).

### R1.5 — round-1 half-failure → **RESOLVED**
All 3 task composes now carry the `build:+image:` dual (`context: selfcontained/base`). Both the
ticketvector base and `jira-gateway:{prod-v1,empty}` are **anonymously pullable** from GHCR, so a
clean machine resolves the gateway with no auth and no manual `build.sh`.

## Residual action items (none gating)

1. **(R2, P1, upstream)** Multi-arch publish blocked on amd64-only `ticketvector-service` base — fix
   belongs in the ticketvector repo. CI already declares both arches (arm64 continue-on-error).
2. **(R1, P2)** `Dockerfile.agent` still `COPY --from`s the GHCR ticketvector base with no
   local-build fallback; fine while that package is public, brittle if it goes private.
3. **(R4, P2)** Stale README task table: claims ENG-2016 assignee "Felix Martin"; live prod-v1 corpus
   returns "Priya Fischer" (Done).

## Honest read on the boundary decision

The boundary call (this repo = jira/linear tooling on ticketvector) is defensible and the fixer
implemented it for real, not on paper: the MCP server, parity, COVERAGE matrix, pytest suite, and
isolation hardening **all live in and are verifiable from this repo**, and the one thing that can't
be done here (arm64) is provably an upstream limitation. R3/R4/R6 are satisfied in-repo. Meets
standard, 7/7.
