# Clone Audit Report — `figma-clone`

- **Audited:** `2026-06-30` · **Auditor:** `clone-audit v1` (independent RE-AUDIT after fix pass) · **Commit:** `3f54f70` (working tree)
- **Fidelity tier (declared / observed):** `T1` / `T1` (stateful handwritten FastAPI+SQLite; derived `search` is substring, not a real query grammar → not T2)
- **Verdict:** ✅ PASS — **meets standard**
- **Gating score:** `6 / 6` gating requirement-groups pass (R1, R2, R3, R4, R5, R6 all pass).

## TL;DR
Round-1 was 4/6 (FAIL) on two gates: a CLI↔MCP parity gap (5 CLI caps with no MCP tool) and a leaking
task-agent image (seed generator importable, answer greppable, no isolation test). **Both are now
fixed, confirmed by commands I ran — not by reading the fixer's claims:**

- **R2.k leak — FIXED.** I built the task agent image (`oddish/.../environment/Dockerfile`) and ran the
  3 probes *inside it*: `grep '#1D4ED8'` over `/opt /usr/local` → empty; `import figmaclone.seed` →
  `ModuleNotFoundError`; `find` for `*/seed/* */api/*` under the installed package → empty. The
  Dockerfile now `rm -rf $PKG/api $PKG/seed` after install (mirroring `docker/Dockerfile.agent`) with a
  build-time smoke assertion. `/srv` carries no `figma.db`/`fixture.json`.
- **R3 parity — FIXED.** The MCP server registers **16 tools** including all 5 previously-missing
  (`figma_delete_comment`, `figma_list_component_sets`, `figma_list_projects`,
  `figma_list_project_files`, `figma_me`). I confirmed CLI↔MCP parity for each **live** against the
  booted `:prod-v1` server, including a stateful delete round-trip.
- **R6 — FIXED.** Cold `pytest` → **31 passed, 6 skipped**. A real isolation test
  (`tests/test_isolation.py`) passes **6/6 inside the agent image** (`FIGMACLONE_AGENT_IMAGE=1`), and the
  parity test (`tests/test_mcp_parity.py`) drives the **registered MCP tools via `call_tool`** (the
  `tools/call` path) against a live uvicorn — tool-level, not helper-level.
- **Regression — HOLDS.** `validate_local.sh` → **PASS nop=0 oracle=1 decoy=0**. `:prod-v1` boots
  mount-free and serves the baked corpus. R1/R4/R5 still pass.

## What it handles well
- **Real two-container artifact, cold-boots clean.** `validate_local.sh` builds the agent + the
  `figma-service` (from the vendored `figma.Dockerfile`, no registry pull — `build:`+`image:` dual) and
  scores nop=0 / oracle=1 / decoy=0; the grader runs in an isolated dir and reads the posted comment
  back through the API, resisting the plausible-wrong-values hack.
- **GHCR image trio is genuinely multi-arch and reproducible.** `ghcr.io/abundant-ai/figma-service:empty`
  and `:prod-v1` publish a manifest index with **linux/amd64 + linux/arm64**, pullable without creds.
  `:prod-v1` is reproducible from a clean checkout: `scripts/build_corpus.py` regenerates a deterministic
  `figma_corpus.db` (4 design-system files under team T1 / project P1) and `docker/Dockerfile.prod-v1`
  bakes it FROM `:empty`. I rebuilt the whole chain locally and booted it mount-free.
- **Faithful Figma REST envelopes, verified live.** Against the booted `:prod-v1`: `{"status","err"}`
  errors with matching codes (403 no-token, 404 unknown team), `1-7`↔`1:7` node-id normalization,
  unknown image → `null`, ms-epoch comment ids. `docs/COVERAGE.md` is now a machine-checkable matrix
  (Endpoint|CLI|MCP|Envelope|Assessment-grade|Tested), 17 capabilities.
- **Tight agent/operator boundary.** World-building (`seed`/generator, control-plane import) is
  gateway-only; the agent image is a thin client with the server source stripped, proven by an
  executable in-image isolation test (not just a build assertion).

## Scorecard (R1–R6)

| Req | Result | Evidence (command I ran) |
|---|---|---|
| **R1** | ✅ pass | `validate_local.sh` → `PASS nop=0 oracle=1 decoy=0`; `:prod-v1` standalone → `{"status":"healthy"}` in 3s |
| **R2** | ✅ pass | leak probes inside task agent image all clean; `:prod-v1` rebuilt + booted mount-free serves corpus; GHCR `:empty`/`:prod-v1` multi-arch (amd64+arm64) pullable |
| **R3** | ✅ pass | `list_tools()` → 16 tools incl. the 5 new ones; live CLI↔MCP parity for me/projects/project-files/component_sets + delete round-trip (status 200, gone=True; bogus→404) |
| **R4** | ✅ pass | `docs/COVERAGE.md` matrix (17 caps); live envelope checks (404/403, 1-7→1:7, unknown image→null) |
| **R5** | ✅ pass | 6 assessment-grade caps labelled; post-comment write→read round-trip exercised end-to-end by the oracle |
| **R6** | ✅ pass | cold `pytest` 31 passed / 6 skipped; isolation 6/6 inside agent image; tool-level parity via `call_tool` |

## R2 canon parity grid (a–k)
a pass · b pass · c pass · d pass · e pass · f pass · g pass · h n/a · i pass · **j pass** · **k pass**

- **k (leak):** all 3 checks hold inside the built task agent image (literal grep empty; `import
  figmaclone.seed` raises; no `api/`/`seed/` source dirs).
- **k (multi-arch):** **pass** (not just n/a) — GHCR `:prod-v1`/`:empty` publish an amd64+arm64 manifest
  index *and* are pullable; CI declares `PLATFORMS=linux/amd64,linux/arm64` + `setup-qemu`.
- **j:** rebuilt `figma_corpus.db` from `scripts/build_corpus.py`, baked `:prod-v1` FROM local `:empty`,
  booted with no mount → `/v1/me`, `/v1/teams/T1/projects` (P1), `/v1/projects/P1/files` (4 files) all served.

## Coverage matrix audit
17 capabilities; with_cli 17; with_mcp **16**; parity_ok **17**; assessment_grade 6; tested 17.
The single MCP "gap" is the `tree` walk, which is the *same* `GET /v1/files/{k}` HTTP read as
`figma_get_file` (CLI sugar over the same endpoint), so it is not a real parity hole — every distinct
HTTP capability has both a CLI command and an MCP tool. The `test_mcp_parity.py` suite parametrizes 14
read caps + the post/delete round-trip and asserts `tools/list >= 16`; all green.

## Tests
Cold `pytest` (fresh `uv` venv): **31 passed, 6 skipped** (the 6 skipped are the agent-image-only
isolation checks, which correctly skip in the dev venv and pass when run *inside* the agent image, where
I observed **6 passed / 4 skipped**). `validate_local.sh`: nop=0 / oracle=1 / decoy=0.

## Action items (all advisory — no gating blockers remain)
1. **(R3, P2)** `with_mcp` reads 16 vs 17 caps only because `tree` is CLI sugar over `figma_get_file`.
   Optionally add a `figma_walk_tree` alias, or note `tree` as get-file sugar in `COVERAGE.md`.
2. **(R3.4, P2, advisory)** Byte-faithfulness: CLI help/error text and MCP tool schemas are
   clone-authored; envelopes are faithful but the help strings haven't been diffed against Figma's
   documented surface (gh-clone's 52-path emulation is the bar).
