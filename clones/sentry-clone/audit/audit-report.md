# Clone Audit Report — `sentry-clone` (Round 2 re-audit)

- **Audited:** `2026-06-30` · **Auditor:** `clone-audit v1` (independent re-audit after fix pass) · **Commit:** `b2b2abd` + working tree
- **Fidelity tier (declared / observed):** `T2` / `T2` — handwritten stdlib JSON store + a real Sentry issue-search query grammar.
- **Verdict:** ✅ MEETS STANDARD — *(meets = all gating reqs pass)*
- **Gating score:** `6 / 6` gating requirement-groups pass (R1–R6 all pass).

## TL;DR
Round-1 failed 4/6 on two gating gaps: **R1** had no bundled task (nop/oracle unmeasurable) and **R2** had
no `:prod-v1`/`:empty` image trio. The fix pass closed both, and this independent re-audit **confirms every
previously-failing gate by running it** — nothing was taken on trust.

- **R2 trio now real and verified live.** `Dockerfile.prod-v1` (FROM the `:empty` base, `COPY corpus/state.json
  → $SENTRY_CLONE_CORPUS_FILE`) booted **healthy with NO mount** and served **5 seeded issues**
  (PAYMENTS-501/510/487, CHECKOUT-12/7). `:empty` booted healthy with a mounted fixture and served PAYMENTS-501.
  Switching empty↔prod-v1 is the image tag alone (the entrypoint serves the baked corpus only when no fixture
  is mounted).
- **R1 task now real and verified live.** `tasks/payments-incident` ships `tests/test.sh` → `run_verifier.sh`
  → `/logs/verifier/reward.txt` and `solution/solve.sh`. `run_local.sh` (build:+image dual, no `networks:`,
  healthcheck-gated `depends_on`) printed **`PASS: nop=0.0 oracle=1.0`**.
- **Agent image leak-clean (R2.k).** All three probes pass on the task agent image.
- **Regressions hold.** R3 (22 MCP tools, CLI↔MCP parity), R4 (COVERAGE matrix), R5 (8 assessment-grade +
  live write→read round-trip), R6 (**23/23 pytest**, up from 18) all still pass.

## Confirm / deny per previously-failing gate (with the command I ran)

### R2 — was FAIL, now **PASS**
- **`:prod-v1` bakes corpus, boots mount-free** — CONFIRMED.
  `docker run -d sentry-clone-service:sentryre-prod-v1` (no `-v`) → health=healthy;
  `GET /api/0/organizations/acme/issues/` → `issue count: 5`, shortIds
  `[PAYMENTS-501, PAYMENTS-510, CHECKOUT-12, CHECKOUT-7, PAYMENTS-487]`; `GET /api/0/issues/PAYMENTS-501/`
  → `PAYMENTS-501 / unresolved / 1001`.
- **`:empty` exists + serves a mounted fixture** — CONFIRMED. `docker run -v fixture.json:/data/sentry-clone/state.json:ro`
  → healthy; PAYMENTS-501 served. (Bare `:empty` with no mount correctly warns and refuses to serve data —
  it is a mount target only.)
- **Agent leak probes** — CONFIRMED clean:
  1. `find / -path '*sentry_clone/server*'` → empty.
  2. `python3 -c "import sentry_clone.server"` → `ModuleNotFoundError: No module named 'sentry_clone.server'`.
  3. `grep -rIl '<fix release|root cause|PAYMENTS-501>'` → only `/workspace/TASK.md` (the instruction prompt,
     which legitimately states the fix-release input; the *buried* signal — stacktrace + suspect-commit linking
     the regression — lives solely behind the API). Source-level `test_isolation.py` additionally asserts no
     `sentry_clone.seed` generator is importable (the recomputability leak).
- **Multi-arch (R2.k)** — CI `.github/workflows/build-service-image.yml` declares
  `platforms: linux/amd64,linux/arm64` for both `:empty` and `:prod-v1`. Per audit scope, the multi-arch CI
  declaration is accepted locally; the live `imagetools inspect` half is `n/a (unverified)` until the GHCR
  package is published.

### R1 — was PARTIAL, now **PASS**
- **Bundled task + nop/oracle** — CONFIRMED. `COMPOSE_PROJECT_NAME=sentryre bash tasks/payments-incident/run_local.sh`
  → `nop reward=0`, then oracle ran `sentry issues resolve PAYMENTS-501 --in-release payments-api@2026.06.07.2`
  + `sentry issues comment …` through the public CLI, → `oracle reward=1`, → **`PASS: nop=0.0 oracle=1.0`**.
- Compose shape: `main` (agent, server-stripped) + `sentry` gateway, `build:`+`image:` dual (no GHCR pull),
  no `networks:` block, healthcheck-gated `depends_on`. Verifier reads final state back through the Sentry API
  (`/api/0/issues/PAYMENTS-501/` status + `…/comments/`), never trusting narration.

### R4 — was PARTIAL, now **PASS**
- `docs/COVERAGE.md` is a machine-checkable matrix with **23 rows** (endpoint | CLI | MCP | envelope | AG | tested)
  and **8 assessment-grade** rows (≥5 required). Round-1's missing matrix is resolved.

## Regression checks (still hold)
- **R3** — 22 MCP tools (5 writes), CLI live `sentry issues get PAYMENTS-501` → `PAYMENTS-501/unresolved/1001`;
  `test_parity.py` asserts `normalize(cli)==normalize(mcp)` and passes.
- **R5** — 8 assessment-grade; live write→read round-trip via the bundled task (resolve + comment read back).
- **R6** — **23/23 pytest pass** in a clean `python:3.13-slim` container (round 1 was 18/18). New files close the
  round-1 advisory gaps: `test_parity.py`, `test_isolation.py`, `test_task_pack_compose.py`.

## Remaining blockers
**None gating.** Two non-gating follow-ups: (1) once the GHCR package is published, confirm `imagetools inspect`
lists both arch manifests for `:prod-v1`/`:empty` (P2); (2) `ENV SENTRY_AUTH_TOKEN` in the Dockerfiles trips the
buildkit `SecretsUsedInArgOrEnv` warning — a non-secret eval default, but could move to compose env (P3).
