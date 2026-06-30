# Clone Audit Report — `gh-cli-clone`

- **Audited:** `2026-06-30` · **Auditor:** `clone-audit v1` · **Commit:** `36e78af`
- **Fidelity tier (declared / observed):** `T3` (Forgejo-backed) / `T3`
- **Verdict:** ❌ FAILS STANDARD — *(meets = all gating reqs pass)*
- **Gating score:** `4 / 7` gating requirement areas pass (R1, R3, R4, R5 pass; R2, R6 fail; R7 satisfied by this audit).

## TL;DR
`gh-cli-clone` ships a genuinely excellent, high-fidelity `gh` emulation (`ghc`, 41 agent-facing
commands across 9 groups) **and** a parity MCP server (`ghc-mcp`, 31 tools), both thin clients of one
`ForgejoClient` HTTP layer over a real self-hosted **Forgejo** forge (T3). It cold-boots as a
two-container agent+gateway task with strong isolation (the agent reaches the forge only by static IP,
carries no seed/source on disk, and `import ghclone` raises), and the bundled incident task scores a
clean **nop=0 / oracle=1** through a full clone→fix→PR→review→merge→close round-trip. It does **not**
meet Clone Standard v1 because it **inverts the canon seeding model**: there is **no `:prod-v1`/`:empty`
image trio and no baked-DB** (R2.b/j fail), per-task data is `COPY`d into a **per-task forge image**
rather than mounted (R2.d fail), the CI publish is **single-arch** (R2.k fail), and the pytest suite is
**missing the dedicated CLI↔MCP parity test and the isolation test** the standard mandates (R6.2/R6.3
fail). The single most important action item: ship the `ghc-service:{prod-v1,empty}` image pair with a
baked corpus DB and switch per-task data to a **mount into the gateway**.

## What it handles well
- **gh emulation fidelity (T3).** `ghc --help` and every group/leaf render gh-2.89 cobra layout;
  success strings match (`✓ Closed issue acme/webapp#3 (covtest issue)`, `✓ Squashed and merged pull
  request acme/webapp#2 (…)`), `--json` projects gh camelCase fields with `state:"OPEN"/"MERGED"/"CLOSED"`,
  errors print `gh: … (HTTP NNN)`. Verified live: `ghc issue list -R acme/webapp --json …` →
  `[{"number":1,"state":"CLOSED","title":"Incident: …"}]`. (`docs/GH-EMULATION-AUDIT.md`, 52 paths.)
- **One HTTP source of truth.** Both CLI (`ghclone/cli/main.py`) and MCP (`ghclone/mcp/server.py`) call
  the single `ForgejoClient` (`ghclone/forge/client.py`, ~60 methods). No business logic in either
  surface — parity is structural. Confirmed live: MCP `issue_list`/`pr_list`/`repo_view` hit the same
  `/api/v1/...` endpoints as the CLI against the same forge.
- **MCP server runs.** `ghc-mcp` starts over stdio and lists **31 tools** (`tools/list` returned them).
- **Strong agent/gateway isolation.** In the running `main` container: no forge DB on disk
  (`[ ! -e /var/lib/forgejo ]` → SEALED), `/opt/ghclone` absent, no `*.py` ghclone source, no `seed.sh`,
  `grep -rs split_bill /opt /app /usr/local` empty, `python3 -c import ghclone` → ModuleNotFoundError,
  `gh` is an ELF PyInstaller binary. Agent reaches forge only at `http://10.88.0.2` (no service-name
  tell; backend on :80 so no `:3000` Gitea tell — `docs/SIM-TELLS.md`).
- **Operator/agent boundary (R2.g).** `ghc` exposes no `hydrate`/`migrate`; world-building lives in a
  separate `ghc-hydrate` entrypoint (`ghclone/cli/admin.py`); MCP exposes no `repo_migrate`/`hydrate_*`.
- **Real verifier round-trip.** `incident-isolated` task: nop=0.0, oracle=1.0, measured by running
  `tests/test.sh` (writes `/logs/verifier/reward.txt`) before/after `solution/solve.sh` inside `main`.
- **Test suite green where it exists.** 47 offline unit tests pass; 21 live tests (client + integration)
  pass against the running forge.

## Scorecard

| Req | Area | Result | Evidence | Action item (if not full pass) |
|---|---|---|---|---|
| R1 | Setup & run (Harbor) | **pass** | `nop=0.0 oracle=1.0` on incident-isolated; 2-container cold boot healthy; agent reaches forge by IP over HTTP | — |
| R2 | Architecture canon a–g + seeding j–k | **fail** | no `:prod-v1`/`:empty` trio; per-task `COPY seed.sh`; single-arch CI | ship image trio + mount data + multi-arch (items 1–3) |
| R3 | CLI + MCP parity | **pass** | 41 CLI cmds + 31 MCP tools, both call one `ForgejoClient`; live calls hit identical `/api/v1` endpoints | add a *dedicated* parity test (R6.2) |
| R4 | Functional coverage | **pass** | `docs/COMMAND-COVERAGE.md` + `docs/PARITY.md` enumerate every command→gh→endpoint; envelopes verified live | rename/add `docs/COVERAGE.md` with endpoint+MCP columns |
| R5 | Assessment-grade endpoints | **pass** | incident round-trip (stateful+multi-step+devops); ci-artifact (dispatch→run→artifact); ≥5 such tasks | add explicit assessment-grade labels |
| R6 | Unit tests all surfaces | **fail** | 68 tests green, but **no CLI↔MCP parity test** and **no isolation test** in pytest | add parity + isolation tests (items 4–5) |
| R7 | Report & verdict | **pass** | this report + `audit-verdict.json` | — |

### Canon + seeding parity grid (R2 detail) — a–i canon, j–k GHCR image DB seeding
| a | b | c | d | e | f | g | h | i | j | k |
|---|---|---|---|---|---|---|---|---|---|---|
| ✅ | ❌ | ✅ | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ❌ | ⚠️ |

- **a ✅** base `ghc-service` published and **pullable without creds** (`docker manifest inspect ghcr.io/abundant-ai/ghc-service:latest` → PULLABLE).
- **b ❌** no `:prod-v1` / `:empty` tags exist anywhere in the repo or registry (`grep -rl 'prod-v1|:empty'` → none). The image trio is absent.
- **c ✅** agent is a neutral `python:3.11-slim` with only the compiled `gh` binary; data-free on disk (verified in running container).
- **d ❌** per-task data is delivered by **`COPY seed.sh` into a per-task forge image** (`Dockerfile.forge:14`) + first-boot run, **not** a mount into the gateway. This is the canon-inverse the build flags: the forge (and the agent) are **built per task**.
- **e ✅** bulk hydration uses native Forgejo migrate; mutations go through the shared `ForgejoClient` op set.
- **f ✅** Harbor 2-container agent+gateway; `tests/test.sh` → `/logs/verifier/reward.txt`; documented static-IP isolation exception (`docs/SIM-TELLS.md`), so the `networks:` block is allowed (R1.4).
- **g ✅** hydration/migration unreachable from `ghc`/MCP (separate `ghc-hydrate`); asserted by `tests/test_smoke.py`.
- **h ⚠️** no `abundant-identity` wiring; identities are local forge users (`acme`). Advisory.
- **i ⚠️** rich docs (PARITY, COMMAND-COVERAGE, GH-EMULATION-AUDIT, HARBOR, SIM-TELLS) but no `COVERAGE.md`/PROD-OVERLAY by canon name. Advisory.
- **j ❌** no `:prod-v1` baked-DB image; cannot boot a mount-free corpus by tag swap. The only seeding path is per-task `seed.sh`.
- **k ⚠️** **leak half passes** (3/3: no greppable answer, `import ghclone` raises, no `seed/`/`api/` source on agent). **Multi-arch half fails**: `.github/workflows/publish-images.yml` build-push step declares **no `platforms:`** → single-arch publish (amd64). Per the standard this is a fail (CI doesn't declare both arches), not `n/a`.

> **Auditor harness notes:** the `selfcontained/isolated/` Dockerfiles `COPY ghclone` but ship it
> gitignored; I re-vendored `ghclone` into `examples/oddish-tasks/incident-isolated/environment/` (per
> `scripts/migrate-isolated.sh`) to build. To run host-side CLI/MCP/live-tests I exposed the forge with a
> one-off `alpine/socat` proxy on the compose network (`10.88.0.2:80 → host:3399`). Both reconstructions
> are auditor-side, not clone defects.

### Coverage matrix audit (R4/R5 detail) — representative rows (full surface: 41 CLI cmds / 31 MCP tools)
| Capability | Endpoint | CLI | MCP | Envelope OK | Assessment-grade | Tested |
|---|---|---|---|---|---|---|
| view repo | `GET /repos/{o}/{r}` | `repo view` | `repo_view` | ✅ (gh `--json`) | — | ✅ |
| list issues | `GET /repos/{o}/{r}/issues` | `issue list` | `issue_list` | ✅ `state:"CLOSED"` | ✅ (filter+state) | ✅ |
| create issue | `POST …/issues` | `issue create` | `issue_create` | ✅ prints URL | ✅ (stateful) | ✅ |
| close issue | `PATCH …/issues/{n}` | `issue close` | `issue_set_state` | ✅ `✓ Closed …#n (T)` | ✅ (write→read) | ✅ |
| create PR | `POST …/pulls` | `pr create` | `pr_create` | ✅ prints URL | ✅ (multi-step) | ✅ |
| review PR | `POST …/reviews` | `pr review` | `pr_review` | ✅ `✓ Approved …` | ✅ (devops) | ✅ |
| merge PR | `POST …/pulls/{n}/merge` | `pr merge` | `pr_merge` | ✅ `✓ Squashed and merged …` | ✅ (write→read) | ✅ |
| dispatch workflow | `POST …/actions/workflows/{w}/dispatches` | `workflow run` | `workflow_run` | ✅ `✓ Created workflow_dispatch …` | ✅ (side-effecting) | ✅ |
| view run / logs | `GET …/actions/runs/{id}` | `run view`/`run log` | `run_view`/`run_log` | ✅ | ✅ (investigation) | ✅ |
| raw api + `--jq` | any | `api` (`-q`) | `api` | ✅ jq engine bundled | ✅ (query grammar) | ✅ |

## Action items (ordered, for the creator loop)
1. **[R2 · gating · P0]** Build and publish the `ghc-service:prod-v1` (corpus DB baked) **and**
   `ghc-service:empty` image pair. *Where:* `selfcontained/`, `scripts/images.sh`,
   `.github/workflows/publish-images.yml`. *Acceptance:* `docker compose up` of `:prod-v1` with **no
   fixture mount** answers a seeded read; switching `:empty↔:prod-v1` is the image tag alone.
2. **[R2.d · gating · P0]** Deliver per-task data by **mounting a fixture into the gateway** (or via a
   token-gated control plane), not `COPY seed.sh` into a per-task forge image. *Where:*
   `selfcontained/isolated/Dockerfile.forge` + `docker-compose.yaml`. *Acceptance:* the gateway image is
   task-independent; task data arrives as a bind mount applied to a runtime copy at boot.
3. **[R2.k · gating · P0]** Publish the gateway **multi-arch**. *Where:* `publish-images.yml` build-push
   step. *Acceptance:* `platforms: linux/amd64,linux/arm64` declared; `docker buildx imagetools inspect`
   lists both arches.
4. **[R6.2 · gating · P0]** Add a **CLI↔MCP parity test**: for each capability, assert
   `normalize(ghc … --json) == normalize(mcp_tool(...))`. *Where:* `tests/test_parity.py` (new).
   *Acceptance:* a green parametrized parity test covering ≥1 row per CLI group.
5. **[R6.3 · gating · P0]** Add a pytest **isolation test** that runs against the agent image: assert no
   state on disk, `import ghclone` raises `ModuleNotFoundError`, and no `seed/`/`api/` source survives.
   *Where:* `tests/test_isolation.py` (new), wired into `test.sh`. *Acceptance:* green from a cold boot.
6. **[R4/R5 · advisory · P1]** Add a machine-checkable `docs/COVERAGE.md` with one row per capability
   (`endpoint | CLI | MCP | envelope | assessment-grade | tested`) and explicitly **label ≥5
   assessment-grade** capabilities. *Acceptance:* file exists; ≥5 rows flagged; matches the live surface.
7. **[R3/docs · advisory · P1]** Fix the stale **"41/41 passing"** claim. `scripts/agent-coverage.sh`
   extracts issue/PR numbers with `grep -oE '#[0-9]+'`, but `ghc … create` faithfully prints a **URL**
   (e.g. `http://10.88.0.2/acme/webapp/issues/3`, no `#N`) — so a clean run yields **23/41**, with 18
   *cascading* failures from empty `$ISS`/`$PR` (each command works given a real number, verified
   manually). *Where:* `scripts/agent-coverage.sh`, `docs/PARITY.md`, `README.md`. *Acceptance:* harness
   extracts the trailing number from the URL; re-run prints `0 failed`.

## Reproduction
```bash
# CLI/MCP (host)
uv venv -p 3.11 /tmp/ghc-venv && uv pip install --python /tmp/ghc-venv/bin/python -e .
/tmp/ghc-venv/bin/ghc --help                      # gh-faithful help
/tmp/ghc-venv/bin/python /tmp/mcp_list.py          # MCP tools/list -> 31 tools

# Offline + live tests
/tmp/ghc-venv/bin/python -m pytest tests/test_cli_unit.py tests/test_hydrate_unit.py \
  tests/test_actions_overlay.py tests/test_smoke.py -q          # 47 passed
# (with forge up, GHC_HOST/GHC_TOKEN set):
/tmp/ghc-venv/bin/python -m pytest tests/test_client.py tests/test_integration.py -q   # 21 passed

# Two-container standup (Harbor-style)
D=examples/oddish-tasks/incident-isolated/environment
cp -r ghclone $D/ghclone                            # re-vendor (gitignored)
docker compose -p ghcaudit -f $D/docker-compose.yaml up --build -d
# forge healthy: exec api -> curl localhost/api/healthz -> {"status":"pass"}
# agent authed:  exec main -> gh auth status -> ✓ Logged in to 10.88.0.2 account acme

# Isolation (in main)
docker compose -p ghcaudit exec main sh -c '[ ! -e /var/lib/forgejo ] && echo SEALED'   # SEALED
docker compose -p ghcaudit exec main python3 -c 'import ghclone'                          # ModuleNotFoundError
docker compose -p ghcaudit exec main grep -rs split_bill /opt /app /usr/local            # empty

# nop / oracle (in main)
docker cp tests/test.sh <main>:/tmp/; docker cp solution/solve.sh <main>:/tmp/
exec main: bash /tmp/test.sh  -> reward 0    (nop)
exec main: bash /tmp/solve.sh && bash /tmp/test.sh -> reward 1   (oracle)

# GHCR
docker manifest inspect ghcr.io/abundant-ai/ghc-service:latest   # PULLABLE (base only; no prod-v1/empty)
```
