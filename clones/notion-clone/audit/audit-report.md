# Clone Audit Report — `notion-clone` (re-check after P0 fix)

- **Audited:** `2026-06-29` · **Auditor:** `clone-audit v1` (independent re-check) · **Monorepo HEAD:** `a948c38` (clone tree is vendored/untracked)
- **Fidelity tier (declared / observed):** `T2` / `T2`
- **Verdict:** ✅ MEETS STANDARD — *(all gating requirement groups pass)*
- **Gating score:** `7/7` gating requirement groups pass. The prior P0 gating leak (R2.c/R2.k) is **closed and independently re-verified**.

## TL;DR

The single P0 blocker from the prior audit — the agent image leaking the gateway's seed source so the
answer was recomputable via `import notionclone.seed.generator` — is **fixed and verified**. The agent
Dockerfile (`oddish/tasks/notion-db-triage/environment/Dockerfile`) now `COPY`s the package to
`/tmp/notionclone-src`, `pip install`s it, then `rm -rf`s **both** the site-packages `api/`+`seed/`
**and** the `/tmp` source tree, with build-time asserts. Re-running all three hardened leak probes on a
freshly built image: the answer literal is not greppable, `import notionclone.seed` raises
`ModuleNotFoundError`, and no `api/`/`seed/` source dirs survive. `/opt` and `/tmp` are empty. The agent
tools still load (`notion-cli --help`, `notionclone.cli.main` / `mcp.server` / `client` import cleanly).
Nothing regressed: the 2-container pair cold-boots, `:prod-v1` serves the baked corpus mount-free,
nop=0.0 / oracle=1.0 in the real docker shape, MCP lists 13 tools live, and the clone's pytest is
**73 passed / 1 skipped** (unchanged). Two non-gating items carry forward (P1 `seed` subcommand cosmetics,
P2 isolation-test skip). Multi-arch remains scored `n/a` (GHCR package still not pullable) per the
hardened standard — not a fail, because the source-leak aspect of R2.k is what mattered and it now passes.

## The fix, verified (the three hardened leak probes)

Built fresh: `docker build -f Dockerfile -t notion-agent-recheck .` (from
`oddish/tasks/notion-db-triage/environment/`). The build's own RUN-step asserts passed (a non-stripped
tree would fail the build). Then, run directly on the image:

```
# (a) literal answer grep — must find nothing
$ docker run --rm notion-agent-recheck grep -rs 'Rotate prod database creds' /opt /app /usr/local
  → (no output; grep exit 2 = dirs empty/absent, nothing matched)
# bounded confirm over the real install dirs:
$ docker run --rm notion-agent-recheck sh -c \
    'SP=$(python -c "import notionclone,os;print(os.path.dirname(os.path.dirname(notionclone.__file__)))"); \
     grep -rs "Rotate prod database creds" "$SP" /usr/local/bin /workspace; echo grep_exit=$?'
  → grep_exit=1   (not found = PASS)

# (b) seed generator must NOT be importable — the leak that slipped past grep last time
$ docker run --rm notion-agent-recheck python -c "import notionclone.seed"
  → ModuleNotFoundError: No module named 'notionclone.seed'   (raised = PASS)
$ docker run --rm notion-agent-recheck python -c "import notionclone.seed.generator"
  → ModuleNotFoundError: No module named 'notionclone.seed'   (raised = PASS)

# (c) no api/ or seed/ source dirs survive in the agent
$ docker run --rm notion-agent-recheck sh -c 'find /opt /app -path "*/seed/*" -o -path "*/api/*"'
  → (empty)   (PASS)

# context fully gone:
$ docker run --rm notion-agent-recheck sh -c 'ls -la /opt; ls -la /tmp'
  → /opt empty, /tmp empty

# tools still load:
$ docker run --rm notion-agent-recheck notion-cli --help            → OK
$ docker run --rm notion-agent-recheck python -c \
    "import notionclone.cli.main, notionclone.mcp.server, notionclone.client"  → imports OK
```

All three probes also re-confirmed **inside the running agent container** (`environment-main-1`):
`import notionclone.seed` → `ModuleNotFoundError`; `find … seed/ api/` → empty; `[ ! -e /srv/notion.db ]`
→ `SEALED`.

## What it handles well (re-confirmed, not regressed)

- **Two-container Harbor shape boots clean (R1.1/R1.2).** `docker compose up --build` (task compose +
  `harbor-main-build.override.yaml`) → `notion` healthy, then `main` started on the health gate.
  `curl http://notion:3000/health` from inside `main` → `{"status":"healthy"}`.
- **`build:`+`image:` dual resolves with no registry creds (R1.5).** GHCR pull of
  `ghcr.io/abundant-ai/notion-service:prod-v1` → `not found`, so this is load-bearing — and it works:
  `compose build` tagged the image locally from `notion.Dockerfile`.
- **GHCR image-DB seeding, mount-free (R2.j).** Booted `:prod-v1` with **no fixture volume**; from
  inside `main`: `POST /v1/search` (filter object=database) → **1 `Tasks` database**; `GET /v1/users`
  → **5 users**.
- **nop=0 / oracle=1 in the real docker shape (R1.3).** Copied `tests/` + `solution/` into `main`. Ran
  `tests/test.sh` against the untouched world → `reward.txt` = **0.0**. Ran `solution/solve.sh`
  (notion-cli only) → marked the target page Done + posted the rotation comment → re-ran the verifier →
  **1.0**. The verifier reads state back through the public API.
- **CLI + MCP both live and in parity (R3).** `notion-mcp` over stdio inside `main` → `initialize` →
  `tools/list` returned **13 tools**. CLI/MCP remain thin clients of one `NotionClient` seam.
- **Unit tests green (R6).** Clean `python:3.12-slim` container, `pip install ".[mcp]" pytest`, then
  `pytest tests/` → **73 passed, 1 skipped** (the isolation test that needs `CLONE_STATE_PATH`).

## Scorecard

| Req | Area | Result | Evidence | Action item (if not full pass) |
|---|---|---|---|---|
| R1 | Setup & run (Harbor) | pass | `nop=0.0 oracle=1.0` in 2-container docker; notion healthy; main reaches `http://notion:3000/health`; build:+image: tagged with no creds | — |
| R2 | Architecture canon a–g + seeding j–k | **pass** | grid below; **leak CLOSED**: grep empty, `import notionclone.seed` raises, no api/seed dirs, `/opt`+`/tmp` empty. j PASS (baked corpus mount-free). Multi-arch **n/a** (GHCR not pullable) per hardened standard | P1 #1, P2 #2 (non-gating) |
| R3 | CLI + MCP parity | pass | 13 MCP tools listed live in agent; both thin clients of one `NotionClient`; 36 parity-suite tests green | — |
| R4 | Functional coverage | pass | `docs/COVERAGE.md` present, 14 caps each → endpoint+CLI+MCP; envelopes verified prior + live search/users | — |
| R5 | Assessment-grade endpoints | pass | 7 labelled (≥5); write→read round-trip exercised by `notion-db-triage` (oracle=1.0) | — |
| R6 | Unit tests all surfaces | pass | **73 passed / 1 skipped** in clean py3.12; every endpoint + CLI + MCP + parity + isolation, happy + error | P2 #2 (close the skip) |

### Canon + seeding parity grid (R2 detail) — a–i canon, j–k GHCR image DB seeding

| a | b | c | d | e | f | g | h | i | j | k |
|---|---|---|---|---|---|---|---|---|---|---|
| ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅* |

- **a** base `notion-service` image exists (`docker/Dockerfile`), CI publishes to GHCR. ✅
- **b** `:prod-v1` + `:empty` both exist (`Dockerfile.prod-v1`, `Dockerfile.empty`). ✅ (built locally)
- **c** thin data-free agent — **✅ FIXED**: the agent Dockerfile installs from `/tmp/notionclone-src`
  then `rm -rf`s the `/tmp` source tree **and** the site-packages `api/`+`seed/`; `/opt` and `/tmp` are
  empty; no answer is greppable and the seed generator is not importable.
- **d** per-task data by mount into the gateway, not COPY'd per-task image — ✅ (this task uses the
  baked-DB path; `:empty`+mount path also exists).
- **e** bulk = native (SQLite), mutations via the shared op-list (`store.py`/`client.py`). ✅
- **f** Harbor 2-container, test.sh→reward.txt, no `networks:` block. ✅
- **g** agent/operator boundary — **✅ FIXED**: `/_control/*` is token-gated (agent has no
  `NOTION_CONTROL_TOKEN`) AND the seed generator is now physically absent, so the prior re-`import`
  bypass is gone. (`notion-cli seed` is still *advertised* but cannot run — `ModuleNotFoundError`; see P1 #1.)
- **h** identity registry (`abundant-identity`) not wired — advisory, users are local. ⚠️
- **i** skill/catalog/PROD-OVERLAY — `docs/PROD-OVERLAY.md` present. ✅
- **j** `:prod-v1` bakes the corpus DB and serves it mount-free — ✅ verified (search→Tasks, users→5,
  no fixture mounted, agent disk SEALED).
- **k** image hygiene — **✅ on the source-leak aspect** (grep empty + import raises + no api/seed dirs).
  Multi-arch: **`n/a` (unverified)** — `ghcr.io/abundant-ai/notion-service:prod-v1` is `not found`
  (private/unpublished), so `buildx imagetools inspect` can't confirm the manifest; the CI workflow
  (`.github/workflows/notion-service-image.yml`) **does** declare `platforms: linux/amd64,linux/arm64`
  with `packages: write` + `GITHUB_TOKEN`. Per the hardened standard this is `n/a`, not fail; it stays a
  gating blocker only at publish time. `*` = source-leak pass + multi-arch n/a.

### Coverage matrix audit (R4/R5) — unchanged from prior audit, spot-re-verified

14 capabilities, 14 with CLI, 13 with MCP (archive folds into `notion_update_page`, documented),
14 parity-OK, 7 assessment-grade, 14 tested. Search (Tasks db) and users (5) re-confirmed live this run;
query-database grammar / typed-error envelopes verified in the prior audit and unchanged in source.

## Action items (ordered, non-gating — the P0 is resolved)

1. **[R2.g · advisory · P1]** `notion-cli seed` is still a registered agent subcommand and exits 0 on
   its `ModuleNotFoundError` traceback.
   - **where:** `src/notionclone/cli/main.py` (the `seed` Typer group) + the agent strip step.
   - **note:** harmless — the module is gone so it *cannot* seed (`import notionclone.seed` raises);
     this is purely a confusing world-building affordance still advertised in `--help`.
   - **fix:** gate the `seed` group out when `notionclone.seed` is absent, or exit non-zero with a clean
     "operator-only, unavailable in agent" message.
   - **acceptance:** in the agent, `notion-cli --help` does not advertise `seed` and `notion-cli seed
     generate` exits non-zero with a clear message.

2. **[R6.3 · advisory · P2]** The isolation unit test skips by default (needs `CLONE_STATE_PATH`) and
   its world-building check is narrow.
   - **where:** `tests/test_cli_mcp_parity.py::test_isolation_no_seed_on_disk` (line ~268, skips without
     `CLONE_STATE_PATH`) and the world-building-absent check.
   - **fix:** add an agent-image test that asserts `import notionclone.seed` raises and
     `grep -rs <answer> /opt` is empty (the exact regression this audit caught manually); wire
     `CLONE_STATE_PATH` so the isolation test runs in CI.
   - **acceptance:** suite runs with 0 skips in the agent container; a new test fails on a pre-fix image
     and passes on the post-fix image.

3. **[R2.k · publish-time · note]** Make the GHCR package public (or grant a read token) so multi-arch
   can be inspected. The `build:`+`image:` dual keeps R1.5 portability today; only the multi-arch
   *verification* is blocked. Not gating per the hardened standard (scored `n/a`).
   - **acceptance:** `docker buildx imagetools inspect ghcr.io/abundant-ai/notion-service:prod-v1` lists
     both `linux/amd64` and `linux/arm64`.

## Reproduction

```bash
ENV=clones/notion-clone/oddish/tasks/notion-db-triage/environment
OVR=skills/clone-audit/assets/harbor-main-build.override.yaml

# --- the P0 leak re-check (build the agent, run all three probes) ---
cd $ENV
docker build -f Dockerfile -t notion-agent-recheck .
docker run --rm notion-agent-recheck grep -rs 'Rotate prod database creds' /opt /app /usr/local   # nothing
docker run --rm notion-agent-recheck python -c "import notionclone.seed"                           # ModuleNotFoundError
docker run --rm notion-agent-recheck sh -c 'find /opt /app -path "*/seed/*" -o -path "*/api/*"'    # empty
docker run --rm notion-agent-recheck notion-cli --help >/dev/null                                  # OK

# --- nothing-regressed: boot the pair standalone, probe, nop/oracle ---
docker compose -f docker-compose.yaml -f ../../../../../../$OVR up --build -d   # notion healthy, main up
docker exec environment-main-1 curl -fsS http://notion:3000/health             # {"status":"healthy"}
docker exec environment-main-1 sh -c "curl -fsS -X POST http://notion:3000/v1/search \
  -H 'Authorization: Bearer notion-clone-token' -H 'Content-Type: application/json' \
  -d '{\"query\":\"Tasks\",\"filter\":{\"property\":\"object\",\"value\":\"database\"}}'"          # 1 Tasks db
docker exec environment-main-1 sh -c "[ ! -e /srv/notion.db ] && echo SEALED"                      # SEALED
# nop/oracle: copy tests+solution into main, run test.sh -> 0.0, then solve.sh + verifier -> 1.0

# --- unit tests, clean py3.12 ---
docker run --rm -v "$PWD":/repo -w /repo python:3.12-slim sh -c \
  'pip install -q ".[mcp]" pytest && python -m pytest tests/ -q'                                    # 73 passed, 1 skipped
```
