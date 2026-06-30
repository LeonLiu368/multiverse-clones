# Clone Audit Report — `sentry-clone`

- **Audited:** `2026-06-30` · **Auditor:** `clone-audit v1` · **Commit:** `bf65a8e` (multiverse-clones; clone subtree)
- **Fidelity tier (declared / observed):** `T2` (undeclared) / `T2` — handwritten JSON store + a real Sentry issue-search query grammar.
- **Verdict:** ❌ FAILS — *(meets = all gating reqs pass)*
- **Gating score:** `4 / 6` gating requirement-groups pass (R3, R4, R5, R6 pass; R1 partial; R2 fail).

## TL;DR
`sentry-clone` is a clean, handwritten (stdlib-only) Sentry error-monitoring clone with a strong tool
surface: a `sentry` CLI and a 22-tool `sentry-mcp` MCP server, both verified live as thin clients of one
HTTP API and in parity, plus a verifier-visible mutation log that gives a real write→read assessment
signal. It is **not eval-ready as-is** because it ships **no `:prod-v1` / `:empty` GHCR image trio** — the
canon's GHCR-image-DB-seeding gates (R2.b/j) are absent, the published `:main` image is **amd64-only**
(R2.k multi-arch fail), the agent image still carries the gateway's `server/` API source (R2.k strip),
and there is **no bundled Harbor task** (`tests/test.sh`/`solution/solve.sh`), so nop/oracle (R1.3) cannot
be measured. The single most important action item: publish the `:prod-v1`+`:empty` multi-arch trio and
add a bundled task with `test.sh`/`solve.sh`.

## What it handles well
- **CLI + MCP both real and in parity (R3).** Live from the agent container, `sentry issues get
  PAYMENTS-501 --json` and the MCP `get_issue` tool both returned `1001 / PAYMENTS-501 / unresolved`.
  MCP `tools/list` returned **22 tools**; both surfaces are thin clients of `SentryClient` (HTTP only) —
  no business logic in either (`sentry_clone/cli/{sentry.py,mcp_server.py,client.py}`).
- **Real issue-search query grammar (T2 / R5).** `_filter_issues` in `sentry_clone/server/issues.py`
  implements `is:`, `level:`, `environment:`, `release:`, `assigned:none`, `project:`, and arbitrary
  tag filters plus `lastSeen/firstSeen/events/users` sorts. Verified `--query 'is:unresolved'` returns
  the correct single issue.
- **Write→read round-trip with verifier-visible mutation log (R5.2).** `sentry issues resolve … ` then
  read-back showed `resolved`; the admin-only `sentry-clonectl mutations` (gateway side) showed
  `['issue.resolve']` with before/after diffs. This is a strong, deterministic grading hook.
- **Sentry-shaped error envelopes + typed exit codes.** `sentry_error()` returns
  `{"detail","error","statusCode"}`; unknown issue → exit 2 (`Not found`), bad token → exit 3
  (`Forbidden`) — verified live, not 500s.
- **Clean runtime isolation (R2.c/g).** Agent reaches the gateway by name over HTTP
  (`http://sentry/api/healthz` → `{ok:true}`); **no seed on disk** in the agent (`/data` and `/var/lib`
  state both absent); `sentry-clonectl` correctly excluded from the agent image; admin token withheld.
- **Empty+mount seeding path works.** The gateway copies a read-only `/data` seed to a runtime
  `/var/lib` copy at boot and mutates only the copy (`SentryStore.from_runtime`).
- **18/18 unit tests pass** from a fresh checkout (py3.13).

## Scorecard

| Req | Area | Result | Evidence | Action item (if not full pass) |
|---|---|---|---|---|
| R1 | Setup & run (Harbor) | partial | task-pack `up --wait` → both healthy; agent→gateway HTTP OK; **but no `test.sh`/`solve.sh`, nop/oracle unmeasurable** | Add a bundled Harbor task w/ `tests/test.sh`→`reward.txt` + `solution/solve.sh`. |
| R2 | Architecture canon a–g + seeding j–k | fail | parity grid below | Publish `:prod-v1`+`:empty` trio; multi-arch; strip `server/` from agent. |
| R3 | CLI + MCP parity | pass | live CLI vs MCP `get_issue` agree; 22 MCP tools | — |
| R4 | Functional coverage | partial→pass* | `docs/API_COMPATIBILITY.md` lists all endpoints; **no machine-checkable `docs/COVERAGE.md`** | Add `docs/COVERAGE.md` matrix (endpoint·CLI·MCP·grade). |
| R5 | Assessment-grade endpoints | pass | issue search (grammar), resolve/ignore/assign (devops write), write→read mutation-log round-trip exercised live | Label them in COVERAGE.md (advisory). |
| R6 | Unit tests all surfaces | pass | `18 passed`; every CLI cmd + 22 MCP tools + every endpoint hit | Add explicit parity + isolation tests; more error paths. |

\* R4 behavior is correct and fully documented in `API_COMPATIBILITY.md`; it is scored **partial** only
because the standard (R4.1) requires a **machine-checkable `docs/COVERAGE.md`** matrix, which is absent.

### Canon + seeding parity grid (R2 detail) — a–i canon, j–k GHCR image DB seeding
| a | b | c | d | e | f | g | h | i | j | k |
|---|---|---|---|---|---|---|---|---|---|---|
| ✅ | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ⚠️ | ⚠️ | ❌ | ⚠️ |

*Why each non-✅:*
- **a ✅** base `sentry-clone-service` image exists and is published (`ghcr.io/abundant-ai/sentry-clone-service:main`, verified pullable via `imagetools inspect`).
- **b ❌** No `:prod-v1` + `:empty` pair. `imagetools inspect …:prod-v1` → **not found**; CI only tags `:main` / `:sha-<sha>`. The image **trio** does not exist.
- **c ✅** Agent is thin + data-free on `python:3.10-slim`; no seed on disk (verified `[ ! -e /data… ] && [ ! -e /var/lib… ]`).
- **d ✅** Per-task data is **mounted** into the gateway (`./data/...:/data/...:ro`), never `COPY`d into a per-task gateway image.
- **e ✅** Bulk = native JSON state; mutations recorded through a shared op-list (`mutation_log` via `_record_mutation_locked`).
- **f ⚠️** Two-container agent+gateway shape with healthcheck + `depends_on` works, **but no `test.sh`→`reward.txt`** verifier wiring is bundled (no Harbor task). Documented-isolation-exception N/A.
- **g ✅** World-building is gateway-only: seed mount + `from_runtime` boot copy live only in the gateway; the agent has no seed entrypoint and no `sentry-clonectl`.
- **h ⚠️** No `abundant-identity` registry wiring; users are inline JSON. (Advisory.)
- **i ⚠️** No skill/catalog/PROD-OVERLAY doc; `docs/` covers tools/state/API only. (Advisory.)
- **j ❌** **No `:prod-v1` baked-DB image.** The clone has no large baked corpus at all — the seed is a small static `state.json` (2 issues / 2 events) mounted into `:empty`-style gateway. The mount-free baked-corpus boot path does not exist. Could not boot `:prod-v1` (not found).
- **k ⚠️** Mixed: (1) literal grep for a seeded answer token in the agent install dirs = **clean** (`grep -rs 'retry_policy' /opt /usr/local` → no match); (2) **no recomputable-generator leak** — there is no seed generator at all, `import sentry_clone.seed` → `ModuleNotFoundError`, the corpus is a static JSON mounted only into the gateway; **BUT** (3) the agent image **still carries the gateway's full `server/` API source** (`find /opt -path "*/server/*.py"` non-empty: `app.py`, `state.py`, `issues.py`, …) — the standard wants `api/`/`seed/` stripped from the agent. **Multi-arch: FAIL** — published `:main` is **`linux/amd64` only** (`imagetools inspect` shows one real manifest + an `unknown/unknown` attestation; CI `build-push-action` has no `platforms:` key). Since the package IS pullable, multi-arch is verifiable and fails (not `n/a`).

> **Auditor harness notes:** Stood up via `examples/task-pack-compose/docker-compose.yaml` (agent +
> gateway). Shared-docker hazard observed: the default compose project name `task-pack-compose` collided
> with a parallel **gauge** audit using the same name — the `agent` container was transiently grabbed by
> gauge's compose before I re-`up`'d. Recommend per-clone `-p` project names or `COMPOSE_PROJECT_NAME`
> when running fleet audits in parallel. Did not measure nop/oracle: no `tests/test.sh` or
> `solution/solve.sh` is bundled (no Harbor task ships with the clone).

### Coverage matrix audit (R4/R5 detail)
| Capability | Endpoint | CLI | MCP | Envelope OK | Assessment-grade | Tested |
|---|---|---|---|---|---|---|
| list orgs | `GET /api/0/organizations/` | `org list` | `list_organizations` | ✅ | — | ✅ |
| list projects | `GET …/organizations/{org}/projects/` | `projects list` | `list_projects` | ✅ | — | ✅ |
| list issues (query) | `GET …/projects/{org}/{proj}/issues/` & `…/organizations/{org}/issues/` | `issues list --query` | `list_issues` | ✅ | ✅ (query grammar, multi-step) | ✅ |
| get issue | `GET /api/0/issues/{id}/` | `issues get` | `get_issue` | ✅ | — | ✅ (parity verified live) |
| issue events | `GET /api/0/issues/{id}/events/` | `issues events` | `get_issue_events` | ✅ | — | ✅ |
| latest event | `GET …/events/latest/` | `issues latest-event` | `get_latest_event` | ✅ | — | ✅ |
| get event | `GET …/projects/{org}/{proj}/events/{id}/` | `events get` | `get_event` | ✅ | — | ✅ |
| stacktrace | (derived from latest event) | `issues stacktrace` | `get_stacktrace` | ✅ | ✅ (multi-step investigate) | ✅ |
| breadcrumbs | (derived from latest event) | `issues breadcrumbs` | `get_breadcrumbs` | ✅ | — | ✅ |
| issue tags | (derived from issue) | `issues tags` | `get_issue_tags` | ✅ | — | ✅ |
| suspect commits | `GET /api/0/issues/{id}/suspect-commits/` | `issues suspect-commits` | `get_suspect_commits` | ✅ | ✅ (root-cause investigate) | ✅ |
| list releases | `GET …/organizations/{org}/releases/` | `releases list` | `list_releases` | ✅ | — | ✅ |
| get release | `GET …/releases/{version}/` | `releases get` | `get_release` | ✅ | — | ✅ |
| release commits | (derived from release) | `releases commits` | `get_release_commits` | ✅ | — | ✅ |
| list comments | `GET /api/0/issues/{id}/comments/` | `issues comments` | `list_comments` | ✅ | — | ✅ |
| add comment (write) | `POST /api/0/issues/{id}/comments/` | `issues comment` | `add_comment` | ✅ | ✅ (stateful write→read) | ✅ |
| assign (write) | `PUT /api/0/issues/{id}/` | `issues assign` | `assign_issue` | ✅ | ✅ (devops write) | ✅ |
| resolve (write) | `PUT /api/0/issues/{id}/` | `issues resolve` | `resolve_issue` | ✅ | ✅ (devops write→read round-trip, mutation log) | ✅ |
| ignore (write) | `PUT /api/0/issues/{id}/` | `issues ignore` | `ignore_issue` | ✅ | ✅ (devops write) | ✅ |
| reopen (write) | `PUT /api/0/issues/{id}/` | `issues reopen` | `reopen_issue` | ✅ | — | ✅ |
| list activity | `GET /api/0/issues/{id}/activity/` | `issues activity` | `list_activity` | ✅ | — | ✅ |
| ownership rules | `GET …/projects/{org}/{proj}/ownership/` | `ownership list` | `list_ownership_rules` | ✅ | — | ✅ |
| whoami / config | `GET /api/0/user` | `whoami` / `config check` | *(none — config/identity)* | ✅ | — | ✅ |

Parity: every MCP tool maps to a CLI command. CLI-only `whoami`/`config check` are identity/config
helpers (not a parity gap); MCP has **22** action tools, CLI exposes the same 22 plus those two helpers.
Assessment-grade capabilities labelled: **≥8** (issue search, stacktrace, suspect-commits, add comment,
assign, resolve, ignore, reopen) — comfortably ≥5, with a write→read round-trip exercised live (R5.2 ✅).

## Action items (ordered, for the creator loop)
1. **[R2 · gating · P0]** Build & publish the **`:prod-v1` + `:empty` image trio**. *where:* new
   `Dockerfile.prod-v1` (bakes a corpus `state.json` into the image at `$SENTRY_CLONE_STATE_FILE`) +
   `.github/workflows/build-service-image.yml`. *acceptance:* `docker buildx imagetools inspect
   ghcr.io/abundant-ai/sentry-clone-service:prod-v1` resolves; booting `:prod-v1` with **no mount**
   serves seeded issues (`curl …/api/0/projects/acme/payments-api/issues/` returns the corpus);
   `:empty` boots and serves a mounted fixture. (Closes R2.b, R2.j.)
2. **[R2 · gating · P0]** Publish the gateway image **multi-arch**. *where:*
   `.github/workflows/build-service-image.yml` `build-push-action` step. *acceptance:* add
   `platforms: linux/amd64,linux/arm64`; `imagetools inspect …:main` lists both `linux/amd64` **and**
   `linux/arm64` real manifests. (Closes the multi-arch half of R2.k.)
3. **[R1 · gating · P0]** Bundle a Harbor task so nop/oracle is measurable. *where:* `tests/test.sh`
   (writes `/logs/verifier/reward.txt`) + `solution/solve.sh` (oracle) + an `environment/` compose.
   *acceptance:* nop run → `reward.txt` = `0.0`; `solve.sh` then verifier → `1.0`. (Closes R1.3; lifts
   R2.f.)
4. **[R2 · gating · P1]** **Strip the gateway's `server/` API source from the agent image.** *where:*
   `examples/task-pack-compose/Dockerfile.agent` (and the README sidecar snippet). *acceptance:* in the
   agent, `find /opt -path "*/server/*"` is empty (copy only `cli/` + the client, or `rm -rf
   sentry_clone/server` after copy); `import sentry_clone.server.app` raises. (Hardens R2.k check #3.)
5. **[R4 · gating · P1]** Add a machine-checkable **`docs/COVERAGE.md`** matrix (endpoint · CLI · MCP ·
   envelope · assessment-grade · tested), promoting `API_COMPATIBILITY.md`. *acceptance:* `docs/COVERAGE.md`
   exists with one row per capability and ≥5 rows flagged assessment-grade. (Closes R4.1.)
6. **[R6 · advisory · P2]** Add explicit **parity** and **isolation** tests. *where:* `tests/`.
   *acceptance:* a parity test asserts `normalize(cli_out) == normalize(mcp_out)` for ≥5 capabilities;
   an isolation test asserts the state path is absent, `import sentry_clone.seed` raises, and (after
   item 4) no `server/`/`api/` source survives. Add ≥1 error-path test per surface. (Strengthens R6.2/R6.3.)

## Reproduction
```sh
# Unit tests (py>=3.10 required; system py3.9 fails install)
python3.13 -m venv /tmp/sc-venv && /tmp/sc-venv/bin/pip install -e ".[dev]"
/tmp/sc-venv/bin/python -m pytest tests -q          # -> 18 passed

# Two-container agent+gateway standup
docker build -f Dockerfile.service -t sentry-clone-service:local .
CF=examples/task-pack-compose/docker-compose.yaml
docker compose -f "$CF" up -d --build --wait --wait-timeout 90    # both Healthy

# Agent->gateway HTTP by name + isolation
docker compose -f "$CF" exec -T agent python -c \
  "import urllib.request,json;print(json.load(urllib.request.urlopen('http://sentry/api/healthz')))"
docker compose -f "$CF" exec -T agent sh -lc \
  '[ ! -e /data/sentry-clone/state.json ] && [ ! -e /var/lib/sentry-clone/state.json ] && echo NO_SEED'

# CLI vs MCP parity (both -> 1001 PAYMENTS-501 unresolved); MCP lists 22 tools
docker compose -f "$CF" exec -T agent sentry issues get PAYMENTS-501 --json
docker compose -f "$CF" exec -T -e SENTRY_MCP_FORCE_FALLBACK=1 agent python3 <mcp jsonrpc client>

# Write->read round-trip + mutation log (verifier signal)
docker compose -f "$CF" exec -T agent sentry issues resolve PAYMENTS-501 --in-release payments-api@2026.06.07.2 --json
docker compose -f "$CF" exec -T -e SENTRY_URL=http://localhost \
  -e SENTRY_CLONE_ADMIN_TOKEN=test-admin-token-acme-eval sentry sentry-clonectl mutations  # ['issue.resolve']

# Error paths: unknown issue -> exit 2; bad token -> exit 3
# Image trio / multi-arch
docker buildx imagetools inspect ghcr.io/abundant-ai/sentry-clone-service:prod-v1   # NOT FOUND (R2.b/j fail)
docker buildx imagetools inspect ghcr.io/abundant-ai/sentry-clone-service:main      # linux/amd64 only (R2.k fail)

docker compose -f "$CF" down -v
```
