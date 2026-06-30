---
name: clone-creation
description: >-
  Create a new service CLONE (Slack, GitHub/gh, Jira/Linear, Figma, Google
  Workspace, Sentry, AWS, Grafana, Stripe, Notion, …) to a single standard so it
  can be audited and used to evaluate agents. Use this whenever you need to build,
  scaffold, or standardize a clone of a real SaaS/service API for agent evals or
  sandbox tasks: deciding whether to back it with an existing OSS engine or
  handwrite it, what fidelity tier to target, the required build shape (the
  three-image canon + thin agent), and — critically — how to expose BOTH a CLI and
  an MCP server in parity over one HTTP API with high-fidelity, assessment-grade
  endpoints. Trigger on "create a clone", "build a <service> clone", "standardize
  the clone build", "scaffold a new clone", "add CLI+MCP to a clone", or when
  running the creator↔auditor loop with `clone-audit`. This is the BUILDER half of
  the loop; `clone-audit` is the auditor half. It standardizes (and depends on) the
  deeper architecture in the `service-clone-builder` skill.
---

# Creating a service clone, to standard

You are the **builder** in a creator↔auditor loop. Your job is not just to make a clone that works —
it's to make one that **provably meets Clone Standard v1** so `clone-audit` returns
`meets_standard = true`. Build for the audit, not around it.

> **Read first, in order:**
> 1. `_shared/clone-standard.md` — the contract you must satisfy (R1–R6). This is your spec.
> 2. `~/.claude/skills/service-clone-builder/SKILL.md` + `references/the-converged-canon.md` — the
>    deep architecture and the canonical image/data/Harbor shape. **This skill does not repeat that
>    material; it standardizes the decisions around it and wires the result to the auditor.**

## What this skill adds on top of `service-clone-builder`
`service-clone-builder` teaches *how* to build a clone (phases 0–7, worked example, assets). This
skill makes the build **standard and loop-ready** by fixing four things up front and one at the end:

1. **The target** — Clone Standard v1, not "looks done".
2. **The fidelity tier** — an explicit T1/T2/T3 choice (`references/fidelity-and-oss.md`).
3. **The OSS-vs-handwrite decision** — a rubric, not a vibe (`references/fidelity-and-oss.md`).
4. **The CLI+MCP-in-parity mandate** — both surfaces, always, over one HTTP API (R3). Non-negotiable.
5. **The clone spec** — a machine-readable manifest the auditor reads (`references/clone-spec.md`).

## The five decisions to lock before writing code

### Decision 1 — Scope: the agent-used surface (R4)
Do the Stage-0 study (`service-clone-builder/references/study-the-real-service.md`). Produce
`docs/COVERAGE.md`, opening with a `## Real service` block (R4.0: `name`, `api_base`, `reference`,
`version`, `snapshot_date`) — the **named real API** this clone is measured against — then the matrix:
every capability an agent realistically uses → endpoint + intended CLI verb + MCP tool + read/write +
real envelope. **This file is also the audit's target list** — write it first, not last. Name the real
service explicitly (no codenames); bias toward the surface agents *actually* touch; don't clone the
whole product.

### Decision 2 — Fidelity tier (T1/T2/T3)  → `references/fidelity-and-oss.md`
- **T1** stateful handwritten (own HTTP API + embedded store) — the default; lean, deterministic.
- **T2** T1 + a real query grammar (JQL/PromQL/search operators/log SQL) — needed for assessment-grade.
- **T3** OSS-backed (real engine behind a translation layer) — when a good OSS engine exists and
  fidelity matters more than container weight.
- **T0** fixture echo is **not standard-compliant** — never ship it as a clone.
Record the tier in the spec and justify it against R5 (you must be able to reach ≥5 assessment-grade
capabilities at the tier you pick).

### Decision 3 — OSS or handwrite  → `references/fidelity-and-oss.md`
Use the rubric there. Short version: **adopt OSS** when a faithful engine exists and you'd otherwise
reimplement a large, well-specified surface (gh→Forgejo, AWS→LocalStack). **Handwrite** when the
agent-used surface is small, you need determinism/leanness/single-container isolation, or no faithful
OSS exists (Slack gateway, Figma, Sentry, Gauge, Logfire). Either way you still own the **translation
layer** + CLI + MCP; OSS only replaces the engine.

### Decision 4 — The build shape: **agent + gateway** (R1, R2) — follow the canon, don't improvise
Everything centers on **two runtime containers**:
- **agent** (`main`) — Harbor **always builds** it from `environment/Dockerfile`; **neutral base**
  (`python:slim`), carries the per-task codebase + CLI/MCP tools, **no service data**. Reaches the
  gateway only over HTTP by name.
- **gateway** — the service sidecar (your HTTP API + CLI/MCP thin clients + seeder). Harbor does
  **not** build it; it's a **pulled image** (or `build:`+`image:` so it builds locally and tags the
  pullable GHCR name — needs no registry creds, R1.5).

The gateway ships as the **image trio**: `<svc>-service` (base, no data) → `:prod-v1` (corpus **DB
baked in**) + `:empty` (mount target). Two seeding paths, **both required**:
- **GHCR image DB seeding (R2.j)** — `:prod-v1` bakes the corpus into the image
  (`COPY <corpus>.db → $…_DB`) and serves it **mount-free**; published to GHCR, pulled as-is. This is
  the path the standard makes you prove: boot `:prod-v1` with no mount → seeded reads work.
- **Empty + mount** — `:empty` + a per-task fixture mounted **into the gateway** (or control-plane
  seed). Bulk = native format; mutations = shared op-list. Switching paths = the **image tag alone**.

Also fixed up front:
- **Agent/operator boundary**: import/seed/hydrate is a **gateway-only** entrypoint the agent can never
  call — asserted in a smoke test.
- **Harbor two-container** task: `tests/test.sh` → `reward.txt`, `solution/solve.sh` oracle, **no
  `networks:` block** (or a documented isolation exception).
- **GHCR publish contract (CI):** build the gateway on push-to-main with the built-in `GITHUB_TOKEN`
  (`permissions: packages: write`), tag `:latest`/`:<sha>`/`:prod-v1`/`:empty`, **multi-arch**
  (`linux/amd64,linux/arm64`). Make the package public or rely on `build:`+`image:`.
- **Leak rule (R2.k) — strip the generator from the agent.** If the agent is built `FROM <svc>-service`,
  the gateway's **seed generator** rides along, and a *deterministic* generator lets the agent recompute
  the answer even when no literal grep finds it (the notion dogfood shipped exactly this leak past its
  own tests). The agent Dockerfile **must** `rm -rf` the `api/`+`seed/` packages (or build from a neutral
  base with only client+CLI+MCP), AND pick task data disjoint from the clone's seed. Verify:
  `python -c 'import <pkg>.seed'` raises in the agent; `find /opt -path '*/seed/*'` is empty.
- **Build all three gateway images — don't drop `:empty`.** R2.b requires the full trio; the figma/canon
  reference assets ship only base + `:prod-v1`, so a creator copying them silently omits `Dockerfile.empty`.
  Write it explicitly (base image, no data, a mount target).

Baking task data into a per-task gateway image, building the agent per-task, or shipping an amd64-only
gateway are the canonical anti-patterns (gh-clone's gap; the figma multi-arch bug) — they fail R2.d/b/j/k.

### Decision 5 — CLI **and** MCP, in parity (R3) — the part people skip
Both surfaces ship, both are **thin clients of one HTTP API**, both expose every covered capability
(operator-only excepted). Build them together from the coverage matrix so they can't drift:
- one shared HTTP client module the CLI and MCP both import;
- one capability → one CLI command **and** one MCP tool, generated from the same matrix;
- a **parity test** per capability (CLI output == MCP output) in `tests/`.
A clone with a CLI but no MCP (today: `aws-clone`, `abundant-jira-clone`) or vice-versa **fails the
standard**. If you're retrofitting MCP onto a CLI-only clone, wrap the *same* HTTP API the CLI uses —
do not re-implement logic in the MCP server.

## Build order (standardized)
Follow `service-clone-builder`'s phases 0–7, but gated by the standard:

| Step | Do | Gate it satisfies |
|---|---|---|
| 1 | `docs/COVERAGE.md` (Decision 1) + pick tier/OSS (Decisions 2–3) | R4, fidelity recorded |
| 2 | canonical seed model + control-plane seeding (operator-only) | R2.e/g |
| 3 | the HTTP API — real envelopes, real errors, query grammar where assessment needs it | R4.3, R5 |
| 4 | CLI **and** MCP over the shared client, in parity (Decision 5) | R3 |
| 5 | gateway image trio (`:prod-v1` bakes the DB) + thin agent + Harbor task + multi-arch GHCR publish (Decision 4) | R1, R2.a–d/f/j/k |
| 6 | unit tests: every endpoint/CLI/MCP + parity + isolation (mirror `clone-audit/assets/test_clone_template.py`) | R6 |
| 7 | write the **clone spec** manifest + `docs/PROD-OVERLAY.md` + catalog | R7 input, R2.i |
| 8 | self-run `clone-audit` locally; fix P0s before handing off | converged |

## Design for the audit (so the loop converges fast)
- **Label assessment-grade capabilities in `docs/COVERAGE.md`** as you build (R5) — don't make the
  auditor guess. Make ≥1 a write→read round-trip a bundled task exercises.
- **Ship the tests you'd want the auditor to run.** If you write the R6 suite, the first audit is a
  formality, not a discovery. Include the **import-leak** test (`import <pkg>.seed` must raise in the
  agent) — a grep-only isolation test passes a recomputable-answer leak.
- **Make local self-validation possible.** `tests/test.sh` writes `/logs/verifier/reward.txt`, which
  isn't writable outside a container — honor a `REWARD_DIR` override so you can run nop/oracle locally
  without docker.
- **Hydrate derived response fields on write.** Real APIs return computed fields the client never sent
  (Notion's `plain_text` on rich text, timestamps, derived ids). A naive store that persists agent
  input verbatim silently breaks any verifier that reads that text back — hydrate on write, not just
  on the seed path.
- **Emit the clone spec** (`references/clone-spec.md`) — declared tier, image names, surfaces, state
  path, coverage-matrix location. The auditor reads it to orient; a missing/incorrect spec is itself
  an action item.
- **Keep CLI and MCP generated from one matrix** so parity holds by construction, not by luck.

## The loop
You emit a clone + spec; `clone-audit` returns `audit-verdict.json`. Work the `action_items` top-down
(P0/gating first), each has a `where` + `acceptance` — satisfy the acceptance check, rebuild, re-audit.
Converged when `meets_standard = true` with no P0 items. When you fix an item, fix it at the **HTTP-API
layer** when possible so the CLI and MCP both inherit it — that's the leverage the architecture buys.

## Reference map
- `references/fidelity-and-oss.md` — fidelity tiers in depth + the OSS-vs-handwrite decision rubric +
  the CLI/MCP-from-one-matrix pattern.
- `references/clone-spec.md` — the manifest the creator emits and the auditor consumes (+ example).
- `_shared/clone-standard.md` — the contract (R1–R7).
- `~/.claude/skills/service-clone-builder/` — the deep architecture, worked example, and copy-paste
  assets this skill builds on. Use its `assets/` skeletons; this skill standardizes their assembly.
