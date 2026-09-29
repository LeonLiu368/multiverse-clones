# Task Creator — design plan

How spoink turns a captured company world into agent-eval tasks. The engine already
snapshots four surfaces (Slack, Linear, Logfire, GitHub) time-aligned to a moment **T** and
serves them through faithful clones. A *task* = **a served world at T + an instruction +
a verifier that reads final state back**. This plan attacks task creation from many angles
so we're not locked into the single "fix the bug from a resolution PR" shape.

The north star (don't break it): **the snapshot contains the answer**, so generation's hardest
job is *excising the answer from the served world* (the as_of/T cut) and *proving it's gone*.

---

## Axis 1 — Task archetypes (the WHAT)

Each maps to a verifier family (Axis 3). Listed roughly easy→hard.

| # | Archetype | Agent does | Surfaces | Verifier |
|---|---|---|---|---|
| A1 | **Diagnosis / triage** (read-only) | name the root cause: culprit PR / file / error class / service | Logfire + Slack + Linear | `readback` of a structured verdict |
| A2 | **Observability query** | answer a quantitative SRE question (regression window, blast radius, p99) | Logfire + gauge | numeric oracle computed from the snapshot |
| A3 | **Cross-surface correlation** | trace Slack thread → Linear ticket → PR → Logfire spike | all four | `readback` of the chain endpoints |
| A4 | **Integration / state mutation** | act through the clone CLIs: label an issue, post a summary, open/close/comment | Linear/Slack/GitHub clone | `readback` final state through the API |
| A5 | **Incident code-fix** (today's shape) | find & fix the real bug in the SUT | SUT + telemetry/Slack/issue context | `pytest_pr` (F2P/P2P) or `module_check` |
| A6 | **Ticket → fix end-to-end** | reproduce from a Linear ticket, fix code, update the ticket | Linear + SUT + clones | `pytest_pr` **and** `readback` ticket state |
| A7 | **Regression bisect** | "a metric regressed — find the commit" | GitHub history + Logfire | `readback` the offending SHA |
| A8 | **PR review** | flag the real defect a follow-up fix/revert addressed | GitHub diff | line/file match vs the fix PR |
| A9 | **On-call simulation** (long-horizon) | ack → diagnose → communicate → mitigate → file follow-up | all four | composite `readback` + code check |

Coverage goal: pick a first slice that exercises **all three verifier families** — e.g. {A5, A1, A4}.

---

## Axis 2 — Generation feeds (how we FIND tasks)

A `Feed` yields candidates `(incident_T, anchor, surfaces, ground_truth)`. Multiple feeds,
combinable:

- **B1 PR-mined** — scan merged PRs; a bugfix PR (revert/hotfix, "fix", linked issue, touches
  code + a test, small diff) → a code-fix task. Parent commit = incident tip; PR diff →
  F2P/P2P. *(`derive_pr_verifier` already does the empirical half.)* Rank candidates by signal.
- **B2 Incident-anchored** — start from a real incident: a Logfire error spike, a Slack
  "prod is down" thread, a Linear SEV. That moment defines **T** and the cross-surface context;
  the first resolving PR after T is the oracle. This is spoink's native model.
- **B3 Issue-mined** — Linear issues that are closed *with* a linked PR/commit → ticket-to-fix.
- **B4 Telemetry-anomaly-mined** — diff baseline vs incident window in Logfire; each new error
  signature → a diagnosis task whose ground truth is the signature + code path.
- **B5 Synthetic fault injection** — take a *healthy* snapshot and programmatically inject a
  known fault (revert a fix, flip a flag, drop an index). Guaranteed nop=0/oracle=1, full
  difficulty control, zero leakage risk. The volume complement to mined realism.
- **B6 Template parameterization** — one archetype × many `(org, repo, incident)` instances,
  fed by B1–B4.

Recommended primary mix: **B5 for gradeable volume + B1/B2 for realism**.

---

## Axis 3 — Verifier strategies (the GRADING)

Grade by reading final state back; never trust agent narration. (`verifier.py` already has the
first three.)

- **pytest_pr** — F2P (fails on bug, passes on fix) + P2P (regression guard), derived
  *empirically* by running the suite at base vs head SHAs. For A5/A6/A8.
- **module_check** — a bespoke smoke (e.g. `configure_mappers()`) when the PR shipped no test.
- **readback** — assertions run through the agent's CLIs / clone API; each `{cli, expect}`.
  For A1/A3/A4/A6/A7/A9.
- **numeric oracle** *(new)* — ground truth computed from the snapshot at build time (counts,
  windows, p99). For A2. Deterministic because the snapshot is frozen.
- **judge/rubric** — LLM-graded, **banned for scored tasks**; only for exploratory/open-ended,
  behind a flag, never the sole signal.

---

## Axis 4 — The leakage problem (cross-cutting, the make-or-break)

The served world must not contain the answer. The as_of/T model is the mechanism; the task
creator must *enforce and prove* it:

- **Code** anchored at the incident tip — resolution PR excluded (git bundle slice / `apply --as-of T`).
- **Slack/Linear/Logfire** sliced to `as_of < resolution` — messages/issues/comments that name
  the fix are cut by T.
- **Leakage audit (new build step):** grep every served surface for the answer's tokens
  (fix PR number, offending symbol, "root cause" phrasing). Fail generation if any survive.
- **Determinism:** same seed → byte-identical world (fixed ids/timestamps), or grading is flaky.

---

## Axis 5 — Difficulty dials

Per task, independently: context given (telemetry-only → +Slack → +ticket) · bug locality
(one file → cross-module) · surface count (1 → 4) · interaction (read-only → mutate → code) ·
horizon (single-step → multi-step on-call). Dials let one archetype span a difficulty curve.

---

## Pipeline architecture (extends the current seams) — IMPLEMENTED

```
discover(feed) -> Candidate{t, title, summary, required_data, resolution}   # discover.py
  -> spec_from_candidate(cand, attached)                                    # spec.py
       - slices the SUT bundle to the incident tip (fix EXCLUDED)           # _prepare_sut
       - reads the fix's changed files (base..head) -> verifier + leakage tokens
  -> generate_task(spec)                                                    # generate.py: preview-500s dir
  -> validate_task(...)                                                     # validate.py: the quality gate
  -> accept iff no CRITICAL gate fails
```

### Validation gates (validate.py) — the clone-task-builder non-negotiables, enforced
Grounded in the `clone-task-builder` skill. Every generated task carries a gate report; a task is
**accepted only if no CRITICAL gate fails** (shown per-task in the Tasks tab).

| Gate | Critical | Checks |
|---|---|---|
| **contract** | yes | Harbor structure: `custom_docker_compose`, no `networks:`, `linux/amd64`, healthcheck, `test.sh`->`reward.txt`, oracle present |
| **code_cut** | yes | the shipped SUT bundle does NOT contain the fix commit (agent can't `git log` the answer) — the T-slice |
| **surface_leakage** | yes | the answer (fix PR#, sha, changed-file names, title words) is absent from every served text overlay |
| **verifier** | no | tied to the real fix: changed test files for `pytest_pr` (exact F2P/P2P derived at build), else `module_check` |

Verified on real `abundant-ai/oddish#468`: the slice excludes the fix (`code_cut` pass), a planted
"fixed in #468" Slack line is caught (`surface_leakage` fail), and the contract lint caught a real
missing-`custom_docker_compose` bug in the generator.

### Promote gate (promote.py) — the empirical nop=0/oracle=1 proof, IMPLEMENTED
`validate` proves a task is well-formed; `promote` proves the **code contract** empirically in docker:
clone the shipped SUT at the incident tip, run the fix's tests (expect FAIL = nop), apply the oracle
patch (`solution/fix.patch`, the base..head diff generation now ships), re-run (expect PASS = oracle).
`proven` iff nop fails and oracle passes. Runs in one throwaway container (the code fix is what
nop/oracle grades; sidecar retrieval is a separate concern the validation gates cover). A SUT that
can't build reports `errored` — honest signal about which candidates yield runnable tasks. Wired as a
background **Promote (nop/oracle)** action; the Tasks tab shows proven/failed/errored.

Verified on a synthetic task: `nop_exit=1` (tests fail on the bug), `oracle_exit=0` (pass after the
patch) -> `proven`.

### Feeds (discover.py) — now three, live
- **github_revert** — merged revert/hotfix/fix PRs (base->head oracle, F2P from the PR's tests).
- **github_ci** — a CI run red-then-green on the default branch; the red commit is the tip, the green
  commit is the fix (the "bad deploy / CI failure" feed). Verified on real oddish Supabase/Modal reds.
- **logfire_anomaly** — distinct exception signatures become DIAGNOSIS candidates (no code oracle;
  ground truth = signature + service). Verified on real oddish-worker `asyncpg`/`daytona` errors.
Each declares its credential (`FEED_ENV`); the UI feed dropdown lists them + key presence.

Still deferred (honest): **multi-sidecar** promote (retrieval-dependent verifiers) + **exact F2P/P2P**
run at task BUILD (`derive_pr_verifier`); a determinism check; Slack/Linear feeds.

- **Feed interface**: `@feed("name")` -> `List[Candidate]`; discovery is a live lightweight scan.
- `validate_task` is the quality bar; `promote` is the empirical proof — both shown per task (Tasks tab).

### Diversity + farming (PoC, IMPLEMENTED)
Real SWE isn't one shape. `archetypes.py` routes each candidate to a task archetype with its own
instruction + verifier, so one incident stream yields DIVERSE tasks:

| Archetype | From feed | Verifier | Grounds |
|---|---|---|---|
| **code_fix** | github_revert (bugfix) | `pytest_pr` / `module_check` | correctness under buried context |
| **deployment** | github_ci (red→green) | `build_check` (build + checks pass) | release engineering |
| **optimization** | github_revert (perf/cost title) | `metric` (objective past threshold + regression) | optimization under a measured goal |
| **incident_response** | logfire/slack/linear | `readback` (structured diagnosis + mitigate) | on-call + tool usage |

`harness.py` — the reproducibility layer: probe a shipped `codebase.bundle` (build system, test-target
existence, optional build) — the honest signal for which mined incidents are *runnable*.

`farm.py` — the batch runner: `discover -> classify -> generate -> validate -> probe -> rank` over a
feed, emitting a ranked **task-bank.json** grouped by archetype with an accept/reject reason per task.
`python -m spoink.pipeline.farm --feed github_revert --org abundant-ai --limit 10 --out task-bank`.
Verified live: farmed 11 real abundant PRs -> code_fix + optimization, ranked (has-own-verifier first).

Still the bottleneck (honest): a *reliable* per-repo build/test env (the harness's `build=True` path is
best-effort); full-compose promote; the model-trial headroom gate.

---

## Dashboard UX — three automation levels

1. **Manual (today):** pick runs + code anchor (SUT repo, incident commit, resolution PR) → generate one spec.
2. **Assisted (next):** from a captured repo, a **Candidates** panel proposes PRs/incidents
   (ranked by feed signal); click one → autofills the anchor → generate + validate.
3. **Batch-mined:** point at `(repo, window)`; the feed proposes N candidates; triage in a list;
   generate + validate in bulk; accepted tasks land in a tray with their nop/oracle report.

Human-in-the-loop triage stays in 2–3 — leakage/quality needs eyes; full auto is a trap.

---

## Phasing

- **P0 (lands the loop):** generalize `spec_from_runs` → `spec_from_candidate`; add `validate_task`
  (nop/oracle in docker) + a leakage audit; ship archetypes A5 + A1 (covers pytest + readback).
- **P1:** Feeds B1 (PR-mined, ranked) + B5 (fault injection); numeric-oracle verifier + A2;
  the **Candidates** dashboard panel (assisted level).
- **P2:** B2 incident-anchored + A3 cross-surface + A6 ticket→fix; batch mining UI; difficulty dials.
- **P3:** A9 on-call simulation; org-agnostic parameterization; a curated task-bank export.

---

## Decisions to make (need your call)

1. **First archetype slice** — recommend {A5, A1, A4} to cover all verifier families up front.
2. **Primary feed** — recommend **both** B5 (guaranteed gradeable) + B1/B2 (realistic); pick which leads.
3. **Automation ceiling** — recommend *assisted* (level 2), not full auto, for v1.
4. **Judge grading** — recommend **banned** for scored tasks; structured ground truth only.
5. **Org-agnostic** — parameterize on `(org, repo, incident)` now, or hardcode abundant-ai for v1?
6. **Leakage strictness** — hard-fail on any token hit, or warn-and-review? (recommend hard-fail.)
