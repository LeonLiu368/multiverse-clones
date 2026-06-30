# Clone Audit Report — `grafana-clone`

- **Audited:** `2026-06-30` · **Auditor:** `clone-audit v1` (independent re-audit, round 2) · **Commit:** `b2b2abd`
- **Fidelity tier (declared / observed):** `T2` / `T2` (handwritten stdlib HTTP + embedded PromQL/LogQL-style query engine over JSON state)
- **Verdict:** ✅ MEETS STANDARD — *(meets = all gating reqs pass)* — **6/6 gating pass**

## TL;DR

A fixer pass since round 1 (3/6 FAIL) addressed all three failing gates, and the fixes are real
— independently confirmed by building and booting images, running the bundled verifier, and running
the suite from a cold venv. R1 (no bundled task), R2 (no `:prod-v1` trio + leaky agent), and R6
(parity/isolation gated off) all now pass. Regressions R3/R4/R5 hold. The only remaining item is the
advisory: the GHCR gateway package is not yet published, so multi-arch is locally unverifiable
(scored `n/a`, not fail, per the hardened R2.k rule — the `build:`+`image:` dual makes the task run
without a pull).

## What it handles well

- **GHCR image-DB seeding done right.** `Dockerfile.prod-v1` bakes `examples/data/grafana/state.json`
  into the image at `/srv/grafana/state.json` and points `GRAFANA_STATE_FILE` at it; booted mount-free it
  serves the full corpus. Empty/prod-v1 differ by the tag + state-file alone.
- **Clean agent/gateway leak boundary.** The agent Dockerfile strips `grafana/server/*` down to
  `__init__.py` + the pure `links.py`, and self-asserts the strip at build time. `import
  grafana.server.state` raises; the answer keyword is not greppable.
- **Real write→read assessment task.** The annotation round-trip is read back over HTTP by the
  verifier; narration is not trusted, and a decoy (annotation missing the root-cause keyword) scores 0.

## Scorecard (R1–R6)

| Req | Result | Evidence (command run) |
|---|---|---|
| **R1** Setup & run | ✅ pass | `bash oddish/tasks/gauge-annotation-roundtrip/validate_local.sh` → `PASS nop=0 oracle=1 decoy=0 isolation=ok` |
| **R2** Agent+gateway / image seeding | ✅ pass | built `:empty` + `:prod-v1`; `docker run :prod-v1` (no mount) → `gcx dashboards search payment --json` returns `dash-payment-webhooks`; agent leak probes below |
| **R3** CLI + MCP parity | ✅ pass | `mcp_server.TOOLS` = 24 tools; 14 parity cases CLI==MCP; `--disable-write` 24→23 (drops `create_annotation`) |
| **R4** Functional coverage | ✅ pass | `docs/COVERAGE.md` 32-row matrix; behavioral calls to search/query/alert/annotations |
| **R5** Assessment-grade | ✅ pass | 8 AG rows (≥5 required); annotation write→read RT exercised by bundled task |
| **R6** Unit tests | ✅ pass | cold venv `pytest -q` → **54 passed** (parity + isolation by default, no `GRAFANA_RUN_DOCKER_SMOKE`) |
| **R7** Report & verdict | ✅ pass | this file + `audit-verdict.json` |

## Confirm/deny on the round-1 failing gates

### R2 — CONFIRMED FIXED
- `docker build -f Dockerfile.service -t :empty .` and `docker build -f Dockerfile.prod-v1 --build-arg BASE=:empty -t :prod-v1 .` both succeed.
- `docker run -d :prod-v1` (no volume) → healthy in 2s; `gcx dashboards search payment --json` returns the seeded `dash-payment-webhooks`. `/data/grafana` is empty — data comes from baked `/srv/grafana/state.json`. `:empty` mount-free crashes `FileNotFoundError` (it is a mount target) and serves the corpus once `fixture.json` is mounted. Tag/state-file swap only.
- Agent leak strip (built agent image): `grep -rs 'lock_conflict'` and `'dash-payment-webhooks'` over `/opt /app /usr/local` → nothing; `python -c 'import grafana.server.state'` → `ModuleNotFoundError`; `find grafana/server -name '*.py'` → only `links.py` + `__init__.py`; `gcx`/`mcp-grafana` still load; `grafanactl` absent.
- CI declares `platforms: linux/amd64,linux/arm64` for `:empty` and `:prod-v1`. Multi-arch half = `n/a (unverified)` because `docker manifest inspect ghcr.io/abundant-ai/grafana-service:prod-v1` → `manifest unknown` (package unpublished); not a fail per the hardened rule.

### R1 — CONFIRMED FIXED
- New `oddish/tasks/gauge-annotation-roundtrip/` ships `tests/test.sh` → `run_verifier.sh` (writes `/logs/verifier/reward.txt`) and `solution/solve.sh`.
- `validate_local.sh` builds both images, mounts `fixture.json` into the gateway only, runs: **nop=0**, **oracle=1** (write→read annotation round-trip), **decoy=0**, isolation OK.

### R6 — CONFIRMED FIXED
- Cold `python3.13 -m venv` + `pip install -e .[dev]`, then `pytest -q` → **54 passed**, no `GRAFANA_RUN_DOCKER_SMOKE`.
- `tests/test_parity.py` (16: 14 CLI==MCP parity + write→read roundtrip + disable-write control) and `tests/test_isolation.py` (12: 9 `import grafana.server.*` raises + no-source-survives + tools-still-import + links-pure + Dockerfile-asserts-strip) both run by **default**. Docker compose tests self-skip (early-return) when the gate is unset.

## Regressions (R3/R4/R5) — all hold
- **R3:** 24 MCP tools (mcp-grafana) + 9 gcx CLI groups, parity verified, thin clients of one HTTP API.
- **R4:** `docs/COVERAGE.md` machine-checkable 32-row matrix.
- **R5:** 8 assessment-grade rows; write→read round-trip exercised end-to-end.

## Ordered action items (all advisory — none gating)

1. **(R2, P1, advisory)** Publish the gateway trio to GHCR (CI already declares both arches) and make
   the package public, so multi-arch is independently verifiable. *Acceptance:* `docker manifest
   inspect ghcr.io/abundant-ai/grafana-service:prod-v1` lists amd64 + arm64.
2. **(R2, P2, advisory)** Wire `abundant-identity` and add `docs/PROD-OVERLAY.md` (R2.h/R2.i partial).

## Reproduction

```bash
cd clones/grafana
export COMPOSE_PROJECT_NAME=grafanare2
# R2: build trio + boot prod-v1 mount-free
docker build -t grafana-service:empty -f Dockerfile.service .
docker build -t grafana-service:prod-v1 --build-arg BASE=grafana-service:empty -f Dockerfile.prod-v1 .
docker run -d --name g grafana-service:prod-v1
docker exec -e GRAFANA_URL=http://localhost -e GRAFANA_TOKEN=test-token-acme-eval g gcx dashboards search payment --json
# R2.k: agent leak probes
docker build -t grafana-agent -f oddish/tasks/gauge-annotation-roundtrip/environment/Dockerfile oddish/tasks/gauge-annotation-roundtrip/environment
docker run --rm grafana-agent python -c "import grafana.server.state"   # ModuleNotFoundError
# R1: nop/oracle/decoy + isolation
bash oddish/tasks/gauge-annotation-roundtrip/validate_local.sh
# R6: cold-venv default suite
python3.13 -m venv /tmp/v && /tmp/v/bin/pip install -e ".[dev]" && /tmp/v/bin/python -m pytest -q
```
