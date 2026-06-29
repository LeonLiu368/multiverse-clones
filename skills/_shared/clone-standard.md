# Clone Standard v1 — the shared contract

This is the **single source of truth** that the `clone-creation` and `clone-audit` skills both
target. The creator builds *to* this standard; the auditor scores *against* it. Every requirement
below is **gating** (G) or **advisory** (A). A clone **meets the standard** when every G passes;
advisories shape the action-item list but don't block.

The standard is layered on the abundant **converged clone canon**
(`~/.claude/skills/service-clone-builder/references/the-converged-canon.md`). Where the canon and
this doc overlap, the canon wins on architecture; this doc adds the **functional + test + report**
requirements the canon leaves implicit, so a creator/auditor loop can run without a human in the middle.

---

## R1 — Setup & run, Harbor-style  (Gating)

A fresh checkout stands up and runs with **no manual steps beyond documented env vars**.

- **R1.1 (G)** Two-container Harbor shape: `main` (agent, `build: FROM <svc>-agent` + task codebase)
  and the service sidecar (`image: <svc>-gateway:prod-v1` or `:empty`), `depends_on` a **healthcheck**.
- **R1.2 (G)** Cold boot is clean: `docker compose up` reaches healthy with **zero hand-editing**;
  the service answers a health endpoint; the agent container can reach it by service name over HTTP.
- **R1.3 (G)** `tests/test.sh` is the entrypoint and writes `/logs/verifier/reward.txt`;
  `solution/solve.sh` is the oracle. **nop = 0.0, oracle = 1.0** on at least one bundled task.
- **R1.4 (G)** No `networks:` block (Harbor injects `network_mode`) **unless** a documented isolation
  exception (e.g. pinned-subnet IP isolation) is recorded in the clone's `docs/`.
- **R1.5 (A)** Determinism: rebuild from the same seed → byte-identical ids/names.

## R2 — Architecture canon (parity grid a–i)  (Gating a–g, Advisory h–i)

Score the clone against the converged-canon parity checklist verbatim:

| Key | Property | Gate |
|---|---|---|
| a | base `<svc>-service` image, published | G |
| b | `:prod-v1` + `:empty` pair both exist | G |
| c | thin `<svc>-agent`, **data-free** (smoke test asserts no seed on disk) | G |
| d | per-task data by **mount**, never a per-task gateway image / `COPY data` | G |
| e | bulk = native format, mutations = shared op-list | G |
| f | Harbor 2-container, test.sh→reward.txt (or documented isolation exception) | G |
| g | **agent/operator boundary**: world-building (import/seed/hydrate) is a separate entrypoint the agent can never call | G |
| h | identity registry wired (people resolve through `abundant-identity`) | A |
| i | skill + catalog + PROD-OVERLAY doc present | A |

## R3 — Tool surface: CLI **and** MCP, in parity  (Gating)

The agent operates the clone through **both** a CLI and an MCP server, and they cannot drift.

- **R3.1 (G)** Both a CLI and an MCP server ship and are wired into the agent image.
- **R3.2 (G)** Both are **thin clients of one HTTP API** — no business logic in either; the HTTP API
  is the only source of truth.
- **R3.3 (G)** **Parity**: every capability in the coverage matrix (R4) reachable from the CLI is also
  reachable from MCP and vice-versa, *unless* explicitly marked operator-only.
- **R3.4 (A)** Byte-faithfulness: CLI help/errors/output and MCP tool schemas are indistinguishable
  from the real product's tool (gh-clone's 52-path emulation audit is the gold standard).

## R4 — Functional coverage of the real API  (Gating)

There is a written **coverage matrix** (`docs/COVERAGE.md`, machine-checkable) enumerating the
real service's **agent-used surface** and mapping each capability to its endpoint + CLI command +
MCP tool + fidelity grade.

- **R4.1 (G)** The matrix exists and lists every capability an agent realistically needs (read paths
  at minimum; write paths where the task family requires mutation).
- **R4.2 (G)** Each row maps to a real HTTP endpoint **and** a CLI command **and** an MCP tool
  (or is marked N/A with a reason).
- **R4.3 (G)** Response envelopes match the real product (ids, prefixes, error codes, pagination
  shape) for every covered endpoint.
- **R4.4 (A)** Coverage breadth is justified against Stage-0 study of the real service — no
  unexplained gaps in the surface agents actually use.

## R5 — Assessment-grade endpoints (tool-use / devops signal)  (Gating)

A clone is only useful if it can *discriminate* agents. It must carry a labelled subset of
**assessment-grade** capabilities — endpoints rich enough to test tool-use and devops skill:

An endpoint/tool is **assessment-grade** when it has ≥3 of:
1. **Stateful** — a write the agent makes is observable on a later read (round-trip).
2. **Multi-step** — realistic use requires chaining ≥2 calls (list → filter → act).
3. **Realistic errors** — wrong input returns the product's real error envelope/code, not a 500.
4. **Filtering/pagination/query grammar** — the agent must construct a non-trivial query
   (JQL, Slack search operators, PromQL, Drive `q`, Sentry issue search…).
5. **Side-effecting devops shape** — mirrors real ops work (deploy/dispatch, resolve/assign,
   redeliver, rotate, query logs to find a cause).

- **R5.1 (G)** ≥ 5 capabilities are labelled assessment-grade in `docs/COVERAGE.md` (small clones: ≥3).
- **R5.2 (G)** At least one is a **write→read round-trip** exercised end-to-end by a bundled task.
- **R5.3 (A)** The assessment set spans both read-investigation and write-action shapes.

## R6 — Unit tests for every surface  (Gating)

- **R6.1 (G)** A test suite (`tests/` pytest or equivalent) covers **every** covered endpoint,
  **every** CLI command, and **every** MCP tool — happy path + at least one error path each.
- **R6.2 (G)** **Parity tests**: for each capability, a CLI call and the matching MCP tool call
  return the same underlying data (proving R3.3).
- **R6.3 (G)** **Isolation test**: asserts the agent image has no seed data on disk
  (`[ ! -e <state path> ]`) and can only reach state over HTTP.
- **R6.4 (G)** The suite runs green from a cold `docker compose up` and is wired into CI or `test.sh`.
- **R6.5 (A)** Envelope-shape assertions pin id prefixes, error codes, and pagination cursors.

## R7 — Report & loop closure  (Gating for the auditor)

- **R7.1 (G)** The auditor emits both a human report (`audit-report.md`, see
  `_shared/audit-report-template.md`) **and** a machine verdict (`audit-verdict.json`, see
  `_shared/audit-verdict.schema.json`).
- **R7.2 (G)** The verdict states, per requirement R1–R6: `pass | partial | fail`, evidence, and an
  ordered action-item list — so `clone-creation` can consume it and iterate.

---

## Fidelity tiers (vocabulary shared by both skills)

| Tier | Name | What it is | Good for |
|---|---|---|---|
| **T0** | Fixture echo | canned responses, no state | smoke demos only — **not** standard-compliant |
| **T1** | Stateful handwritten | own HTTP API + embedded store (SQLite/JSON/DuckDB), real envelopes | most clones; deterministic, lean, single-container |
| **T2** | Handwritten + real query grammar | T1 plus a real query engine (JQL/PromQL/search operators) | assessment-grade evals |
| **T3** | OSS-backed | real engine behind a translation layer (Forgejo, LocalStack, …) | maximum fidelity where an OSS backend exists |

The standard is **tier-agnostic**: a clean T1 clone can fully meet the standard. Tier choice is a
**creation decision** (see `clone-creation`), not a pass/fail axis — but the chosen tier must be
recorded in the clone spec and justified against the assessment-grade requirement (R5).

## The verdict in one line

> **A clone meets Clone Standard v1 when:** it cold-boots Harbor-style (R1), satisfies canon gates
> a–g (R2), exposes CLI **and** MCP in parity over one HTTP API (R3), documents and matches the real
> agent-used surface (R4) with ≥5 labelled assessment-grade capabilities (R5), and ships unit tests
> covering every endpoint/CLI/MCP surface including parity + isolation (R6).
