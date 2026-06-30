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

## The runtime model everything centers on: **agent + gateway**

Every clone runs as exactly **two containers** in a Harbor task:

- **agent** (`main`) — the thing under test. Harbor **always builds** it from
  `environment/Dockerfile`; it carries the per-task codebase + the clone's CLI/MCP tools on a
  **neutral base** (e.g. `python:slim`), and holds **no service data**. It reaches state only by
  calling the gateway over HTTP by service name (`http://<svc>:<port>`).
- **gateway** — the service sidecar: the clone's HTTP API + CLI/MCP thin clients + seeder, the single
  source of truth. Harbor does **not** build it (only `main` is force-built); the gateway is a
  **pulled image** (or a `build:`+`image:` service that builds locally and tags the pullable name).

The gateway is realized by an **image trio** (canon, R2): `<svc>-service` (base, no data) →
`<svc>-service:prod-v1` (corpus **DB baked in**) + `<svc>-service:empty` (no data, a mount target).
*(Some clones tag these `<svc>-gateway:{prod-v1,empty}`; the role is "gateway" either way.)*

## R1 — Setup & run, Harbor-style  (Gating)

A fresh checkout stands up and runs with **no manual steps beyond documented env vars**.

- **R1.1 (G)** Two-container **agent + gateway** Harbor shape: `main` (agent, built from
  `environment/Dockerfile`, neutral base, data-free) and the gateway sidecar
  (`image: ghcr.io/<org>/<svc>-service:{prod-v1|empty}`, optionally with a `build:` that tags the same
  name), wired by `depends_on` on a gateway **healthcheck**.
- **R1.2 (G)** Cold boot is clean: `docker compose up` reaches healthy with **zero hand-editing**;
  the gateway answers a health endpoint; the agent reaches it by service name over HTTP.
- **R1.3 (G)** `tests/test.sh` is the entrypoint and writes `/logs/verifier/reward.txt`;
  `solution/solve.sh` is the oracle. **nop = 0.0, oracle = 1.0** on at least one bundled task.
- **R1.4 (G)** No `networks:` block (Harbor injects `network_mode`) **unless** a documented isolation
  exception (e.g. pinned-subnet IP isolation) is recorded in the clone's `docs/`.
- **R1.5 (G)** **Gateway resolves without registry creds**: either the `:prod-v1`/`:empty` image is
  public on GHCR, or the gateway service carries both `build:` and `image:` so `compose build` builds
  and tags it locally (no `unauthorized` pull). A task that only works with private-registry auth
  fails portability.
- **R1.6 (A)** Determinism: rebuild from the same seed → byte-identical ids/names.

## R2 — Agent + Gateway architecture & image seeding  (Gating a–g + j–k, Advisory h–i)

Score the clone against the converged-canon parity checklist, **plus** the GHCR image-DB-seeding
gates (j, k) that make the gateway portable:

| Key | Property | Gate |
|---|---|---|
| a | base `<svc>-service` gateway image, published | G |
| b | `:prod-v1` + `:empty` pair both exist (the gateway image trio) | G |
| c | thin **agent**, **data-free** on a neutral base (smoke test asserts no seed on disk) | G |
| d | per-task data by **mount** into the gateway, never a per-task gateway image / `COPY data` | G |
| e | bulk = native format, mutations = shared op-list | G |
| f | Harbor 2-container agent+gateway, test.sh→reward.txt (or documented isolation exception) | G |
| g | **agent/operator boundary**: world-building (import/seed/hydrate) is a gateway-only entrypoint the agent can never call | G |
| h | identity registry wired (people resolve through `abundant-identity`) | A |
| i | skill + catalog + PROD-OVERLAY doc present | A |
| **j** | **GHCR image DB seeding**: `:prod-v1` bakes the corpus DB into the image and boots healthy **with no mount**, pulled as-is from GHCR (or build-tagged to the GHCR name) | **G** |
| **k** | **image hygiene**: gateway published **multi-arch** (`linux/amd64,linux/arm64`); agent on a neutral base; the gateway's **API/seed/generator source is stripped from the agent image** and the task answer is neither greppable nor recomputable from anything left on the agent | G |

### The two seeding paths (set per task, both required to exist)

The gateway carries data one of two ways — a clone must support **both** so any task family can run:

| Path | Image | Data delivery | Use when |
|---|---|---|---|
| **Baked-DB (GHCR)** | `<svc>-service:prod-v1` | corpus **DB baked into the image** (`COPY <corpus>.db → $…_DB`); served as-is, **mount ignored** | prod/realistic tasks that share one big corpus — layers cache across tasks (this is "ghcr image db seeding") |
| **Empty + mount** | `<svc>-service:empty` | base API, **no data**; per-task fixture **mounted** into the gateway (or pushed via the token-gated control plane) | tasks needing a custom/small workspace |

- **R2.j is gating.** The `:prod-v1` image must exist, bake the DB, and serve the full corpus from a
  cold `docker compose up` **without any fixture mount**. Switching a task `empty ↔ prod-v1` is the
  **image tag alone**. Verify by booting `:prod-v1` with no mount and querying seeded data.
- **GHCR publish contract:** CI builds the gateway on push-to-main, `permissions: packages: write`
  with the built-in `GITHUB_TOKEN`, tags `:latest`/`:<sha>`/`:prod-v1`/`:empty`, **multi-arch**. The
  package is public **or** the task uses the `build:`+`image:` dual so it never needs a pull (R1.5).
- **Scoring multi-arch when the package isn't pullable:** the `build:`+`image:` dual (R1.5) lets a
  clone pass R1 while its GHCR package stays private/unpublished — so multi-arch can be **locally
  unverifiable**. Score the multi-arch half of R2.k as **`n/a` (unverified)**, not `pass`, with the
  reason recorded; it stays a gating *blocker* only at publish time. A local build is single-arch by
  default and that alone is **not** an R2.k failure — the failure is shipping an amd64-only image to
  GHCR, or a CI workflow that doesn't declare both arches.
- **Leak rule (R2.k) — grep is necessary but NOT sufficient.** Because the agent's tools may ship
  `FROM <svc>-service` (or copy its source), the baked corpus/**seed generator** can ride along in the
  agent container. A deterministic generator is a leak even when the answer is a *computed* value no
  literal grep would find — the agent can just `import` it and regenerate the world. The agent
  Dockerfile must therefore **strip the gateway's API + seed/generator source** (`rm -rf` the
  `api/`/`seed/` packages, or build the agent from a neutral base with only the client+CLI+MCP). Three
  checks, all must hold:
  1. `docker run --rm <agent-image> grep -rs '<answer>' /opt /app /usr/local` finds nothing (literal);
  2. `docker run --rm <agent-image> python -c 'import <pkg>.seed'` **raises** ModuleNotFoundError
     (generator not importable — the leak that slipped past grep in the notion dogfood);
  3. no `api/`/`seed/` source dirs survive in the agent (`find /opt -path '*/seed/*' -o -path '*/api/*'`
     is empty).

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

- **R4.0 (G)** **Real-service declaration.** `docs/COVERAGE.md` opens with a `## Real service` block
  naming the real API the clone is measured against — `name`, `api_base`, `reference` (docs URL),
  `version`, `snapshot_date`. This is the **named comparison target**: R3 (parity), R4 (coverage), and
  R5 (realism) are all judged against *this* real API, not a vibe. A clone with a codename instead of a
  real-service identity (the old `gauge`) fails R4.0 — every clone maps to a real service. Mirror the
  same block as a `real_service:` field in `clone-spec.yaml`.
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
- **R6.3 (G)** **Isolation test**: asserts the agent has no seed data on disk (`[ ! -e <state path> ]`),
  can only reach state over HTTP, **and that the gateway's seed generator is not importable**
  (`import <pkg>.seed` raises) nor its `api/`/`seed/` source present — grep-for-the-answer alone is
  insufficient when the answer is recomputable (see R2.k).
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

> **A clone meets Clone Standard v1 when:** it runs as a two-container **agent + gateway** task that
> cold-boots Harbor-style (R1), satisfies canon gates a–g **and** GHCR image-DB-seeding gates j–k —
> `:prod-v1` bakes the corpus DB and serves it mount-free, published multi-arch (R2), exposes CLI
> **and** MCP in parity over one HTTP API (R3), documents and matches the real agent-used surface (R4)
> with ≥5 labelled assessment-grade capabilities (R5), and ships unit tests covering every
> endpoint/CLI/MCP surface including parity + isolation (R6).
