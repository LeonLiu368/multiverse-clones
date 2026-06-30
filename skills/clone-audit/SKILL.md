---
name: clone-audit
description: >-
  Audit a service CLONE (Slack, GitHub/gh, Jira/Linear, Figma, Google Workspace,
  Sentry, AWS, Grafana/Gauge, Logfire, …) against the Clone Standard so it can be
  used to evaluate agents. Use this whenever you need to verify a clone: that it
  cold-boots and runs Harbor-style; that it covers the real service's agent-used
  API surface through BOTH a CLI and an MCP server in parity, with a labelled set
  of high-fidelity, assessment-grade endpoints for testing an agent's tool-use and
  devops skill; that every endpoint, CLI command, and MCP tool is covered by unit
  tests; and that it ships a report (handles-well / action-items / meets-requirements
  verdict). Trigger on "audit this clone", "verify the clone works", "does the clone
  meet the standard", "test the clone's CLI/MCP", "is this clone ready for evals", or
  when running the creator↔auditor loop with `clone-creation`. This is the AUDITOR
  half of the loop; `clone-creation` is the builder half.
---

# Auditing a service clone

You are the **auditor** in a creator↔auditor loop. A clone was built (by `clone-creation`, or by
hand) and you must decide, with evidence, whether it **meets Clone Standard v1** and — if not — emit
an ordered, file-scoped action list the creator can act on. Your output is a feedback signal, not prose.

> **Read first:** `_shared/clone-standard.md` (the contract you score against) and, for architecture
> context, `~/.claude/skills/service-clone-builder/references/the-converged-canon.md`. Keep the
> standard's requirement IDs (R1–R7) in hand — every finding maps to one.

## The one rule

> **Trust nothing you didn't run.** A clone "has an MCP server" only if you started it and called a
> tool. It "covers search" only if you issued a query and checked the envelope. It "passes nop/oracle"
> only if you ran the verifier and read `reward.txt`. Read-the-README findings are hypotheses; the
> report records *observed* behavior. Every PASS cites a command you executed.

## The audit, in four phases

Run in order; each maps to standard requirements. The clone runs as **two containers: agent + gateway**
(the agent is built and under test; the gateway is the pulled/seeded service sidecar). Phases 1→3
gather evidence; phase 4 compiles it.

| Phase | You verify | Produces | Standard |
|---|---|---|---|
| 1. Stand up & run | agent+gateway cold-boots Harbor-style; `:prod-v1` serves its baked DB mount-free; verifier scores nop=0/oracle=1 | a live environment + boot evidence | R1, R2(c/d/f/g/j/k) |
| 2. Functional coverage | CLI **and** MCP cover the real agent-used surface, in parity, with ≥5 assessment-grade endpoints | an audited coverage matrix | R3, R4, R5 |
| 3. Unit-test every surface | each endpoint / CLI command / MCP tool passes happy + error paths; parity + isolation hold | a test run (counts, failures) | R6 |
| 4. Report & verdict | meets-standard decision + action items | `audit-report.md` + `audit-verdict.json` | R7 |

Read the matching reference when you reach a phase: `references/setup-and-run.md`,
`references/functional-coverage.md`, `references/unit-tests.md`, `references/reporting.md`.

### Phase 1 — Stand up & run (agent + gateway, Harbor-style)  → `references/setup-and-run.md`
1. Identify the **two containers**: the **agent** (`main`, built from `environment/Dockerfile`) and
   the **gateway** sidecar (`image: ghcr.io/<org>/<svc>-service:{prod-v1|empty}`, maybe `build:`+`image:`).
   Confirm the gateway **healthcheck** and `depends_on` wiring (R1.1).
2. **Cold boot**: `docker compose up` from a clean state with only documented env vars. It must reach
   healthy with zero hand-editing; the gateway must resolve **without registry creds** (public GHCR or
   `build:`+`image:` local tag — R1.5); and the agent must reach the gateway by name over HTTP (R1.2).
   Record commands + boot log for Reproduction.
3. **GHCR image DB seeding (R2.j):** boot the **`:prod-v1`** gateway with **no fixture mount** and query
   seeded data — it must serve the full baked corpus out of the box. Then confirm the **`:empty` + mount**
   path also stands up. Switching the two is the **image tag alone**.
4. Run the bundled verifier: confirm `tests/test.sh` writes `/logs/verifier/reward.txt`, then measure
   **nop = 0.0** and **oracle (`solution/solve.sh`) = 1.0** (R1.3). Oracle ≠ 1 or nop ≠ 0 fails R1.
5. Spot-check runtime canon gates: **agent has no seed on disk** (`[ ! -e <state> ]`, R2.g/c); **agent on
   a neutral base** with the answer **not greppable** in baked gateway source (R2.k leak check); **no
   `networks:`** unless a documented exception (R1.4/R2.f); gateway published **multi-arch** (R2.k).
6. Use `assets/audit_harness.sh` to automate standup → health-probe → seed-probe → teardown.

### Phase 2 — Functional coverage: CLI + MCP vs the real API  → `references/functional-coverage.md`
1. **Establish the target surface.** From the clone's `docs/COVERAGE.md` (R4.1) — or, if missing,
   reconstruct it from a Stage-0 study of the real service — list the capabilities an agent actually
   uses. *Missing/insufficient `COVERAGE.md` is itself an R4 action item.*
2. **Enumerate what the clone actually exposes.** Dump the CLI command tree (`<cli> --help` recursively)
   and the MCP tool list (start the server, list tools). Map each to a real HTTP endpoint.
3. **Build the audited matrix** (one row per capability): `endpoint | CLI cmd | MCP tool | envelope-OK |
   assessment-grade | tested`. Fill **by calling each**, not by reading code.
4. **Parity (R3.3):** for each capability call the CLI path and the MCP tool and confirm they return
   the same underlying data. Any CLI-only or MCP-only capability (not marked operator-only) is a
   parity gap — an R3 action item. **This is the heart of the "both CLI + MCP" goal.**
5. **Envelope fidelity (R4.3):** check ids/prefixes, error codes, pagination shape against the real
   product for each covered endpoint.
6. **Assessment-grade labelling (R5):** mark capabilities that satisfy ≥3 of {stateful, multi-step,
   realistic errors, query grammar, side-effecting devops shape}. Require **≥5** (≥3 for small clones)
   and **≥1 write→read round-trip** exercised end-to-end. Too few = R5 fail: the clone can't
   discriminate agents, which is the whole point.

### Phase 3 — Unit-test every endpoint, CLI command, and MCP tool  → `references/unit-tests.md`
1. If the clone ships tests, **run them from a cold boot** and read pass/fail counts (R6.4). If it
   doesn't, or coverage is partial, **generate them** from `assets/test_clone_template.py`.
2. Coverage bar (R6.1): **every** covered endpoint, **every** CLI command, **every** MCP tool gets a
   happy-path test **and** ≥1 error-path test.
3. **Parity tests (R6.2):** assert CLI-output and MCP-tool-output agree per capability.
4. **Isolation test (R6.3):** assert no seed on disk in the agent image and state is reachable only
   over HTTP.
5. Report the numbers (`<passed>/<total>`), and list every red test as an action item with its
   requirement tag.

### Phase 4 — Report & verdict  → `references/reporting.md`
1. Write `audit-report.md` from `_shared/audit-report-template.md`: TL;DR, **what it handles well**,
   the scorecard (R1–R6), the canon parity grid, the coverage-matrix audit, and **ordered action
   items**.
2. Write `audit-verdict.json` conforming to `_shared/audit-verdict.schema.json`: per-requirement
   `pass|partial|fail`, coverage/test counts, and the action list. This is what `clone-creation`
   consumes to iterate.
3. Set `meets_standard = true` **iff every gating requirement passes**. Be honest: a clone that boots
   and looks nice but has an MCP/CLI parity gap, <5 assessment-grade endpoints, or untested surfaces
   **does not meet the standard** — say so, and make the gaps the top action items.

## Scoring rules (don't fudge these)
- `pass` = verified working with evidence. `partial` = works but with a gap that has a clear fix.
  `fail` = absent, broken, or unverifiable.
- **Gating** requirements (R1, R2.a–g + j–k, R3, R4, R5, R6) must all be `pass` for `meets_standard`.
  Advisories (R1.5, R2.h–i, R3.4, R4.4, R5.3, R6.5) only generate action items.
- One `fail` on any gate ⇒ `meets_standard = false`. No partial credit on the verdict bit.

## How this closes the loop
`clone-creation` reads your `audit-verdict.json`, works the `action_items` top-down (P0/gating first),
rebuilds, and re-invokes you. Convergence = an audit where `meets_standard = true` with no P0 items.
Keep action items **file-scoped and falsifiable** (`where` + `acceptance`) so the creator can act
without guessing and the next audit can confirm the fix.

## Reference & asset map
- `references/setup-and-run.md` — Harbor standup, health probes, nop/oracle measurement, isolation recon.
- `references/functional-coverage.md` — building & auditing the coverage matrix; assessment-grade rubric.
- `references/unit-tests.md` — what to test per surface; parity + isolation tests; generating missing tests.
- `references/reporting.md` — filling the report + verdict; the meets-standard decision.
- `assets/audit_harness.sh` — standup → health → baked-DB seed → leak → teardown helper (auto-merges
  the main-build override).
- `assets/harbor-main-build.override.yaml` — merge to boot a `custom_docker_compose` task standalone
  (reproduces Harbor's injected `main` build).
- `assets/test_clone_template.py` — pytest template for endpoint / CLI / MCP / parity / isolation tests.
- `_shared/clone-standard.md` — the contract. `_shared/audit-report-template.md`,
  `_shared/audit-verdict.schema.json` — output formats.
