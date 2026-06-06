# Harbor Task Audit — `buried-spec`

**Task:** Slack-observability + SWE. The agent must dig through a heavy, noisy seeded Slack
workspace to recover an *agreed* billing policy (several superseded proposals along the way),
implement `billing/fees.py::overdue_fee`, and make the `/workspace` pytest suite pass. A hidden
grading test pins the exact policy.

**Local validation:** `nop = 0`, `oracle = 1`; a **tamper test** (agent overwrites its visible
tests with trivial passes) still scores **0**; and a **wrong-but-invariant-satisfying** impl
(the *superseded* grace-7 / 2-4-6% policy) also scores **0** — confirmed end-to-end on the real
multi-service stack.

> **Bug found & fixed during audit:** the hidden grader was originally named `grade_fees.py`,
> which pytest does **not** auto-collect (only `test_*.py`), so the policy grading silently
> didn't run — a false-pass hole. Renamed to `test_grade_fees.py`; re-validated that a wrong
> policy now fails. (The reusable skill records this gotcha.)

## 1. Instruction clarity & real-worldness — PASS
- Reads like an engineering ticket: "tests are failing; the policy was agreed by the team but
  not written into the repo; recover it and make the suite pass." Names the deliverable
  (`billing/fees.py::overdue_fee`) and the command (`python -m pytest`).
- No leakage of grading/golden/hidden-test framing. The breadcrumb to the workspace lives in
  `README.md`, the `fees.py` docstring, and the `NotImplementedError` message — all natural.
- The hint "earlier proposals were revised, use the agreed values" is a fair real-world nudge;
  it does not reveal the values or their location. **Minimal hand-holding preserved.**

## 2. Verifier consistency & correctness — PASS
- `tests/test.sh` (orchestration) → `tests/run_verifier.sh` (deterministic). Reward is derived
  solely from the trusted suite's pytest exit code.
- Grading runs in a fresh **verifier-owned** dir (`/tmp/grade.$$`): it copies the candidate's
  `billing/` package + the **trusted** test files and runs there. The agent's `/workspace/tests`
  is never executed at grading time.
- Verifier runtime << `verifier.timeout_sec = 600`. Deterministic (fixed-seed data; pure-Python
  policy). No LLM/VLM judge, so no AgenticGrader JSONs required.
- *Note (non-blocking):* harness is the two-script shape (`test.sh`/`run_verifier.sh`) rather than
  the fuller `stage_data`/`run_candidate` split — appropriate here since there is no candidate
  execution phase (the agent edits code in place; the verifier only runs tests).

## 3. Golden solution — PASS
- `solution/solve.sh` writes only `/workspace/billing/fees.py` (an allowed path), implements the
  policy with `Decimal`/`ROUND_HALF_UP`, and matches the hidden reference exactly. It reads no
  hidden files and depends on no verifier-only paths. Full local pass via the real verifier.

## 4. Docker & dependency readiness — PASS
- Client image installs `python3` + `python3-pytest` and symlinks `python`; `decimal` is stdlib.
- `codebase/` is copied to `/workspace`; `workdir = /workspace`. Mattermost seeds the 566-message
  workspace at boot. `platform: linux/amd64` pinned; no explicit compose `networks:`.

## 5. Reward-hacking & trust-boundary resistance — PASS (hardened)
- **Can't read the answer from visible tests:** visible tests are invariant-only (non-negativity,
  monotonicity, zero-cases) and do **not** encode grace/rates/min/cap/rounding. Those parameters
  appear only in Slack and in the hidden `grade_fees.py` (staged at grade time, absent during the
  agent's run).
- **Can't game by editing tests:** verified — the verifier grades the candidate `billing/` against
  trusted tests in an isolated dir; overwriting `/workspace/tests` had no effect (still 0).
- **Can't special-case the grader:** the grading grid is broad and unknown to the agent; the
  policy is only obtainable from Slack.
- `reward.txt` is written by the trusted, runtime-staged verifier (not by candidate code).

## Tool-use criticality (the benchmark's core question) — STRONG
- Slack is **necessary**: the policy exists nowhere in the repo/tests; the hidden grader cannot be
  satisfied without it.
- Slack use is **non-trivial**: `search.messages "overdue fee"` returns *both* the superseded v0
  (2% / 7-day grace) and the final policy; the agent must read the discussion, distinguish
  superseded from agreed values (grace 7→5, rates 2/4/6→1.5/3/5, min $10→$5, late-added $250 cap,
  tier boundaries 0-30/30-60/60+ → 6-30/31-60/61+), and assemble the correct set — then implement
  it correctly (half-up rounding, min-then-cap, tier edges). It is not a single-hit lookup.

## Verdict
**Shippable.** No blocking findings. The golden solution was locally validated through the real
verifier (`nop=0`, `oracle=1`), and reward-hacking resistance (test tampering) was explicitly
tested. Only a non-blocking note on harness granularity.
