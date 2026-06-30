# Clone Audit Report — `figma-clone`

- **Audited:** `2026-06-30` · **Auditor:** `clone-audit v1` · **Commit:** `3f54f70` (working tree)
- **Fidelity tier (declared / observed):** `T1` / `T1` (stateful handwritten FastAPI+SQLite; derived `search` is substring, not a real query grammar → not T2)
- **Verdict:** ⚠️ PARTIAL — does **not** meet standard
- **Gating score:** `5 / 7` gating requirement-groups pass (R1, R2 j/k artifacts, R4, R5 pass; **R3 partial**, **R6 partial** on the isolation/leak gate).

## TL;DR
`figma-clone` is a genuinely strong, handwritten Figma REST clone: it cold-boots Harbor-style as an
agent+gateway pair, the bundled `figma-spec-recovery` task scores **nop=0 / oracle=1 / decoy=0** (the
verifier reads the posted comment back through the API and grades in an isolated dir, resisting the
plausible-wrong-values hack), and a real **multi-arch `:prod-v1` corpus image is published on GHCR and
boots mount-free**. Two gating gaps stop it short: (1) a **CLI↔MCP parity gap** — 5 CLI capabilities
(`comments delete`, `components sets`, `projects`, `project-files`, `me`) have no MCP tool; (2) the
**task agent image leaks the gateway's seed/API source** — `figmaclone.seed.generator` is importable and
the CTA-color answer `#1D4ED8` is grep-able in the agent's `site-packages`, and there is **no isolation
test**. The single most important fix: make the task's `environment/Dockerfile` strip `api/`+`seed/`
(as the already-correct top-level `docker/Dockerfile.agent` does) and add the R6.3 isolation test.

## What it handles well
- **Faithful Figma REST surface, verified live.** Every endpoint returns real Figma envelopes:
  `{"status","err"}` errors with matching HTTP codes (403 no-token, 404 unknown file/team, 400 missing
  `ids`), `1-19`↔`1:19` node-id normalization, `meta.{components,styles}`, ms-epoch ids for new
  comments. Verified by `curl` + `figma-cli` against a live uvicorn (`/v1/files`, `/nodes`, `/comments`,
  `/components`, `/styles`, `/versions`, `/images`, `/teams`, `/projects`, `/me`).
- **Real two-container cold boot.** `docker compose up` (task compose + harbor main-build override)
  reaches `figma … (healthy)`, `depends_on` gates `main`, and `main` reaches `http://figma:3000/health`
  by service name. No `unauthorized` pull — the `build:`+`image:` dual tags the image locally (R1.5).
- **Verifier is sound and hack-resistant.** `validate_local.sh` → `PASS ✓ nop=0 oracle=1 decoy=0`. The
  grader runs in `/tmp/grade.$$` (not `/workspace`), pins the exact spec, and reads the completion
  comment back over the API (`id > 1e12` = genuinely new).
- **GHCR image-DB seeding works.** `ghcr.io/abundant-ai/figma-service:prod-v1` is **published multi-arch
  (amd64+arm64)**, pullable, bakes a 39 MB corpus (real imported file `R1jno9FuCgYkNXayz8zglW`), and
  boots **healthy with no mount**. `:empty` is also published multi-arch. R2.j/R2.b/R2.k(multi-arch) ✓.
- **CLI and MCP are real thin clients of one HTTP API.** MCP stdio server lists **11 tools** and all
  calls round-trip through the live API (`figma_post_comment` → `figma_list_comments` shows the write);
  `figma_inspect_node` on a bad id returns a clean `{"err":"node_not_found"}` envelope.
- **15/15 unit tests pass** from a cold venv (`pytest -q`).

## Scorecard

| Req | Area | Result | Evidence | Action item (if not full pass) |
|---|---|---|---|---|
| R1 | Setup & run (Harbor) | **pass** | `validate_local.sh` → `nop=0 oracle=1 decoy=0`; compose boot `figma (healthy)`, `main`→`figma:3000/health` OK | — |
| R2 | Architecture canon a–g + seeding j–k | **partial** | parity grid below; j/k artifacts ✓ but **agent leaks seed/api** (k) and prod-v1 **not reproducible from repo** | strip `api/`+`seed/` in task Dockerfile; add `figma_corpus.db` build path |
| R3 | CLI + MCP parity | **partial** | MCP=11 tools, all call live API; **5 CLI caps have no MCP tool** | add `figma_delete_comment`, `figma_list_component_sets`, `figma_list_projects`, `figma_list_project_files`, `figma_me` |
| R4 | Functional coverage | **pass** | `docs/figma-api-coverage.md` present; every covered endpoint exercised live with faithful envelopes | (advisory) rename/restructure to machine-checkable `docs/COVERAGE.md` with per-row CLI/MCP/AG columns |
| R5 | Assessment-grade endpoints | **pass** | ≥6 AG capabilities; comment write→read round-trip exercised end-to-end by the task | — |
| R6 | Unit tests all surfaces | **partial** | `15 passed`; parity tests are helper-level not tool-level; **no isolation test** | add tool-level parity + R6.3 isolation test |

### Canon + seeding parity grid (R2 detail) — a–i canon, j–k GHCR image DB seeding
| a | b | c | d | e | f | g | h | i | j | k |
|---|---|---|---|---|---|---|---|---|---|---|
| ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ✅ | ❔ | ⚠️ | ✅ | ⚠️ |

- **a** ✅ base `figma-service` published (amd64). **b** ✅ `:prod-v1` + `:empty` both **published multi-arch** on GHCR.
- **c** ⚠️ the *thin* `docker/Dockerfile.agent` is data-free and strips `api/`+`seed/` (verified: `import figmaclone.seed` raises, no answer grep) — but the **task's `environment/Dockerfile` does NOT** use it; it installs the full package, so the real agent ships `seed/`+`api/`.
- **d** ✅ per-task data mounted into the **gateway only** (`./fixture.json:/srv/fixture.json:ro`); agent has no fixture/DB on disk (verified `SEALED`).
- **e** ✅ bulk = canonical seed JSON / file-dump import; mutations via shared store ops. **f** ✅ 2-container, `test.sh`→`reward.txt`, no `networks:`. **g** ✅ seeding is a gateway-only entrypoint; agent never gets `FIGMA_CONTROL_TOKEN`.
- **h** ❔ no `abundant-identity` wiring (advisory; users are inline `U1`/`U_AGENT`). **i** ⚠️ coverage doc present but no skill/PROD-OVERLAY doc (advisory).
- **j** ✅ `:prod-v1` bakes the corpus DB and boots healthy **mount-free** (verified: served `R1jno9FuCgYkNXayz8zglW` with no volume). **k** ⚠️ multi-arch ✅ for prod-v1/empty, but the **leak half fails on the task agent** (seed importable + `#1D4ED8` greppable).

> **Auditor harness notes:** the task `main` container has no long-running CMD (Harbor injects one), so
> `compose up` needs a `command: ["sleep","infinity"]` override in addition to the standard
> `harbor-main-build.override.yaml` to keep `main` alive for in-container probes. Also: a fresh checkout
> **cannot rebuild** `:prod-v1`/`:empty` — `docker/Dockerfile.prod-v1` requires a `figma_corpus.db` that
> is absent from the repo, no `:empty` Dockerfile/target exists, and CI builds only the amd64 base. The
> published images work but were produced out-of-band.

### Coverage matrix audit (R4/R5 detail)
| Capability | Endpoint | CLI | MCP | Envelope OK | Assessment-grade | Tested |
|---|---|---|---|---|---|---|
| Get file (tree+components+styles) | `GET /v1/files/{k}` (`?ids`,`?depth`) | `files get` | `figma_get_file` | ✅ | ✅ (multi-step, errors) | ✅ |
| Get nodes by id | `GET /v1/files/{k}/nodes?ids=` | `files nodes` | `figma_get_nodes` | ✅ (1-19↔1:19, 400) | ✅ (multi-step, errors) | ✅ |
| Walk node tree | (derived over get file) | `tree` | — (covered by get_file/get_nodes) | ✅ | — | ⚠️ partial |
| Inspect one node | (derived) | `node` | `figma_inspect_node` | ✅ (err envelope) | ✅ | ✅ |
| Extract TEXT | (derived) | `text` | `figma_get_text` | ✅ | — | ✅ |
| Search nodes | (derived) | `search` | `figma_search_nodes` | ✅ | ✅ (query, multi-step) | ⚠️ helper-level |
| List comments | `GET /v1/files/{k}/comments` | `comments list` | `figma_list_comments` | ✅ | ✅ (thread-mining, multi-step) | ✅ |
| **Post comment** | `POST …/comments` | `comments add` | `figma_post_comment` | ✅ (ms-epoch id) | ✅ **(write→read round-trip)** | ✅ |
| Delete comment | `DELETE …/comments/{id}` | `comments delete` | **— (no MCP)** | ✅ (404) | ✅ (stateful) | ⚠️ |
| List components | `GET …/components` | `components list` | `figma_list_components` | ✅ | — | ✅ |
| List component sets | `GET …/component_sets` | `components sets` | **— (no MCP)** | ✅ | — | ⚠️ |
| List styles | `GET …/styles` | `styles list` | `figma_list_styles` | ✅ | — | ✅ |
| List versions | `GET …/versions` | `versions` | `figma_list_versions` | ✅ | — | ✅ |
| Get images | `GET /v1/images/{k}?ids=` | `images` | `figma_get_images` | ✅ (unknown→null) | — | ✅ |
| Team projects | `GET /v1/teams/{t}/projects` | `projects` | **— (no MCP)** | ✅ (404) | — | ✅ |
| Project files | `GET /v1/projects/{p}/files` | `project-files` | **— (no MCP)** | ✅ (404) | — | ✅ |
| Me | `GET /v1/me` | `me` | **— (no MCP)** | ✅ | — | ⚠️ |

Counts: capabilities_total **17**, with_cli **17**, with_mcp **11**, parity_ok **11**, assessment_grade **6**, tested (happy+error somewhere) **~14**.

## Action items (ordered, for the creator loop)
1. **[R6 · gating · P0]** Add the isolation/leak test (R6.3). *Where:* `tests/test_isolation.py`.
   *Acceptance:* asserts in the **task agent image** that `import figmaclone.seed` raises
   `ModuleNotFoundError`, no `figmaclone/api` or `figmaclone/seed` dir survives, `grep -r '#1D4ED8'`
   over install dirs finds nothing, and `/srv/figma.db`/`/srv/fixture.json` are absent.
2. **[R2 · gating · P0]** Strip the gateway source from the task agent. *Where:*
   `oddish/tasks/figma-spec-recovery/environment/Dockerfile` — after `pip install`, `rm -rf` the
   installed `figmaclone/api` and `figmaclone/seed` (mirror `docker/Dockerfile.agent`), or build the task
   agent `FROM` the thin `figma-agent` image. *Acceptance:* the action-item-1 test passes inside `main`.
3. **[R3 · gating · P0]** Close CLI↔MCP parity. *Where:* `src/figmaclone/mcp/server.py` — add
   `figma_delete_comment`, `figma_list_component_sets`, `figma_list_projects`,
   `figma_list_project_files`, `figma_me` (thin wrappers of the existing endpoints). *Acceptance:* MCP
   `tools/list` returns ≥16 tools; a parity test green for each CLI leaf vs its MCP tool.
4. **[R2 · gating-adjacent · P1]** Make `:prod-v1`/`:empty` reproducible from the repo. *Where:* add a
   `:empty` Dockerfile (or reuse `docker/Dockerfile` as empty), a `scripts/build_corpus.py` that emits
   `figma_corpus.db` deterministically, and CI jobs that build+push `figma-service`, `:empty`, `:prod-v1`
   **multi-arch** (`linux/amd64,linux/arm64`) — current CI builds only the amd64 base. *Acceptance:* a
   clean `git clone` + `make images` produces all three tags; `imagetools inspect` lists both arches.
5. **[R6 · gating · P1]** Make parity tests tool-level, not helper-level. *Where:* `tests/test_mcp_parity.py`
   — drive the real MCP server via `tools/call` (stdio) and compare to the matching `figma-cli` output,
   instead of calling `mcp_server._get`/`_document` helpers. *Acceptance:* a parametrized parity test over
   every capability passes through the actual registered MCP tools.
6. **[R4 · advisory · P2]** Promote `docs/figma-api-coverage.md` to a machine-checkable `docs/COVERAGE.md`
   with one row per capability and explicit `endpoint | CLI | MCP | envelope | assessment-grade | tested`
   columns, and an explicit ≥5 assessment-grade label set (R5.1). *Acceptance:* a coverage-lint can parse
   it and the audited matrix above matches it row-for-row.

## Reproduction
```bash
# env (system py is 3.9; clone needs 3.11+)
cd clones/figma-clone && /usr/local/bin/python3.11 -m venv .venv
.venv/bin/pip install -U pip && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q                      # 15 passed

# live API + CLI/MCP exercise
.venv/bin/figma-cli seed generate --seed 42 --out /tmp/figma_audit.db
FIGMA_DB=/tmp/figma_audit.db .venv/bin/uvicorn figmaclone.api.app:app --port 3771 &
FIGMA_API_URL=http://localhost:3771 FIGMA_TOKEN=t .venv/bin/figma-cli files get <KEY>   # + node/text/search/comments/...
# MCP: stdio client → list_tools (11) + call figma_post_comment → figma_list_comments round-trip

# Harbor-style cold boot of the task
cd oddish/tasks/figma-spec-recovery/environment
docker compose -f docker-compose.yaml \
  -f <skills>/clone-audit/assets/harbor-main-build.override.yaml \
  -f /tmp/keepalive.override.yaml up --build -d            # figma (healthy), main up
docker exec environment-main-1 curl -fsS http://figma:3000/health             # OK
docker exec environment-main-1 sh -c '[ ! -e /srv/fixture.json ] && echo SEALED'   # SEALED
docker exec environment-main-1 python -c 'import figmaclone.seed.generator'   # IMPORTABLE  <-- leak

# nop / oracle / decoy
cd oddish/tasks/figma-spec-recovery && bash validate_local.sh                 # PASS nop=0 oracle=1 decoy=0

# GHCR image-DB seeding (mount-free) + multi-arch
docker run -d --name figmaprod -p 3781:3000 ghcr.io/abundant-ai/figma-service:prod-v1
curl -fsS http://localhost:3781/v1/teams/T1/projects                          # baked corpus, no mount
docker buildx imagetools inspect ghcr.io/abundant-ai/figma-service:prod-v1    # amd64 + arm64
```
