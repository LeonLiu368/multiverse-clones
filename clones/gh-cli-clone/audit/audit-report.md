# Clone Audit Report — `gh-cli-clone`

- **Audited:** `2026-06-30` · **Auditor:** `clone-audit v1` (RE-AUDIT, round 2) · **Commit:** `b2b2abd`
- **Fidelity tier (declared / observed):** `T3` / `T3`
- **Verdict:** ✅ MEETS STANDARD — *(meets = all gating reqs pass)*
- **Gating score:** `6/6` gating requirements pass.

## TL;DR
`gh-cli-clone` is a GitHub/`gh` clone backed by a real self-hosted **Forgejo** engine (T3), operated
through a `gh`-faithful CLI **and** an MCP server, both thin clients of one `ForgejoClient`. Round 1
failed on R2 (no `:prod-v1`/baked-DB, per-task `COPY seed.sh` instead of a mount) and R6 (no parity /
isolation tests). **Both are now genuinely fixed and independently verified by run:** `ghc-service:prod-v1`
boots **mount-free** and serves its baked corpus over the API; the bundled task delivers per-task data
by **bind-mount into a task-independent gateway**; and `tests/test_parity.py` (7/7) + `tests/test_isolation.py`
(plus a test.sh isolation guard) codify the previously-missing behaviors. It is **usable for agent
assessment today**. The single most important remaining item is non-gating: the stale
`scripts/agent-coverage.sh` number-parsing bug that reddens `test_coverage_live.py`.

## What it handles well
- **Real Forgejo backend (T3).** No mock; the gateway runs the actual `forgejo` binary on :80 as a
  non-root user — no `:3000` Gitea tell, neutral `10.88.0.2` URLs in all clone/PR/error output.
- **`:prod-v1` baked-DB seeding works mount-free** — confirmed by booting the image with no fixture and
  reading the seeded repo, file contents, and incident issue over `/api/v1`.
- **Clean agent/operator boundary + sealed agent.** Agent is a PyInstaller `gh` ELF on a neutral base;
  `import ghclone` raises, no seed/api source survives, no forge state on disk, answer not greppable.
- **Real CLI↔MCP parity, now tested.** `test_parity.py` drives both surfaces against a live forge and
  asserts identical records per CLI group.
- **End-to-end devops round-trip** (clone→fix→PR→approve→squash-merge→close-issue) scored oracle=1, nop=0.

## Scorecard

| Req | Area | Result | Evidence | Action item (if not full pass) |
|---|---|---|---|---|
| R1 | Setup & run (Harbor) | pass | cold boot healthy; `gh auth status`→acme@10.88.0.2; **nop=0.0 oracle=1.0** | — |
| R2 | Architecture canon a–g + seeding j–k | pass | prod-v1 mount-free corpus served; mount not COPY; leak-clean; multi-arch CI | retire legacy `isolated/` (P2) |
| R3 | CLI + MCP parity | pass | `test_parity.py` 7/7 live | fix coverage-live parser (P1) |
| R4 | Functional coverage | pass | `docs/COVERAGE.md` ✓ machine-checkable matrix | doc the ghclone vendor step (P2) |
| R5 | Assessment-grade endpoints | pass | 11 AG capabilities; round-trip demo reward=1 | — |
| R6 | Unit tests all surfaces | pass | 85/86 (offline 78✓/15s; live parity 7✓); 1 advisory red | — |

### Canon + seeding parity grid (R2 detail) — a–i canon, j–k GHCR image DB seeding
| a | b | c | d | e | f | g | h | i | j | k |
|---|---|---|---|---|---|---|---|---|---|---|
| ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ✅ | ✅ |

*Why: (b) trio = base / `:empty` (==base) / `:prod-v1`. (d) bundled task `incident-isolated` now uses
`image: ghc-service:empty` + `build:` dual with `./fixture:/fixture:ro` bind-mount — no per-task gateway
image, no `COPY seed.sh`. (j) `:prod-v1` baked-DB boots healthy mount-free and serves the full corpus.
(k) leak rule's 3 checks all hold on the agent + CI declares `linux/amd64,linux/arm64` (declaration
accepted; package not pulled, build:+image: dual). (h/i) identity-registry / PROD-OVERLAY remain advisory
partials, unchanged from round 1.*

### Coverage matrix audit (R4/R5 detail) — sample rows from `docs/COVERAGE.md`
| Capability | Endpoint | CLI | MCP | Envelope OK | Assessment-grade | Tested |
|---|---|---|---|---|---|---|
| list issues | `GET /repos/{o}/{r}/issues` | `issue list` | `issue_list` | ✅ `state:"OPEN"/"CLOSED"` | ✅ (filter+state grammar) | ✅ parity |
| close issue | `PATCH …/issues/{n}` | `issue close` | `issue_set_state` | ✅ | ✅ (write→read round-trip) | ✅ oracle |
| create PR | `POST …/pulls` | `pr create` | `pr_create` | ✅ prints URL | ✅ (stateful devops) | ✅ oracle |
| merge PR | `POST …/pulls/{n}/merge` | `pr merge` | `pr_merge` | ✅ `Squashed and merged` | ✅ (side-effecting) | ✅ oracle |
| raw api | `* /…` | `api` | `api` | ✅ | — | ✅ parity |

41 CLI commands (9 groups) / 31 MCP tools; 11 capabilities flagged assessment-grade (≥5 required).

> **Auditor harness notes:** Docker shared. Used `COMPOSE_PROJECT_NAME=ghre` and clone-local tags
> `ghc-service:ghre-{base,prod-v1}` / `ghre-main` to avoid colliding with concurrent clone audits.
> Pre-existing `ghc-runner` / `ghc-forgejo` (another context) were not touched and remain up.
> `ghclone` had to be vendored into the task `environment/` (gitignored; normally done by
> `migrate-isolated.sh`) for `compose build main` to succeed — recorded as a P2 doc item. The live
> parity/integration tests were reached via an `alpine/socat` proxy from host→`10.88.0.2:80`.
> All audit images/containers/networks were removed at teardown.

## Action items (ordered, for the creator loop)
1. **[R3 · advisory · P1]** Fix `scripts/agent-coverage.sh` number extraction — `ghc create` prints a
   trailing URL, not `#N`; the grep `'#[0-9]+'` misses it, reddening `test_coverage_live.py`. Parse the
   trailing number from the URL. *Acceptance:* `pytest tests/test_coverage_live.py` green against a live gateway.
2. **[R2 · advisory · P2]** Retire or repoint the legacy `selfcontained/isolated/` scaffold (still
   `COPY seed.sh` into a forge image, non-canon) and `migrate-isolated.sh` step-1 so migrated tasks can't
   regress to the per-task-image model. *Acceptance:* migrate produces the gateway+mount compose.
3. **[R4 · advisory · P2]** Document the `ghclone` vendor-into-`environment/` prerequisite for
   `compose build main` (agent `COPY ghclone` needs it in context). *Acceptance:* fresh-checkout
   `compose build` of a bundled task succeeds without a manual `cp`.

## Reproduction
```
cd clones/gh-cli-clone
# build the gateway trio (clone-local tags, shared-docker-safe)
docker build -f selfcontained/gateway/Dockerfile -t ghc-service:ghre-base .
docker build -f selfcontained/gateway/Dockerfile.prod-v1 --build-arg BASE=ghc-service:ghre-base -t ghc-service:ghre-prod-v1 .

# R2.j — boot :prod-v1 MOUNT-FREE on the baked ROOT_URL, query the corpus
docker network create --subnet=10.88.0.0/24 ghre-net
docker run -d --name ghre-prodv1 --network ghre-net --ip 10.88.0.2 ghc-service:ghre-prod-v1
TOKEN=$(docker exec ghre-prodv1 cat /shared/token)
docker exec ghre-prodv1 curl -fsS -H "Authorization: token $TOKEN" \
  http://localhost/api/v1/repos/acme/webapp/issues?state=all   # -> #1 Incident: /split … [open]

# R1 — cold boot bundled task; nop / oracle  (vendor ghclone first)
cd examples/oddish-tasks/incident-isolated/environment
cp -r ../../../../ghclone ./ghclone
COMPOSE_PROJECT_NAME=ghre docker compose build && COMPOSE_PROJECT_NAME=ghre docker compose up -d
docker compose exec -T main gh auth status                       # Logged in to 10.88.0.2 account acme
docker compose cp ../tests/test.sh main:/tmp/test.sh; docker compose exec -T main bash /tmp/test.sh   # -> 0 (nop)
docker compose cp ../solution/solve.sh main:/tmp/solve.sh; docker compose exec -T main bash /tmp/solve.sh
docker compose exec -T main bash /tmp/test.sh                    # -> 1 (oracle)

# R2.k — leak checks on the agent image
docker run --rm ghre-main python3 -c 'import ghclone'            # ModuleNotFoundError
docker run --rm ghre-main grep -rs 'if people == 0\|def split_bill\|Incident: /split' /opt /app /usr/local   # nothing

# R6 — tests
uv run --extra dev pytest -q                                     # 78 passed, 15 skipped (offline)
GHC_HOST=http://127.0.0.1:18080 GHC_TOKEN=$TOKEN uv run --extra dev pytest tests/test_parity.py   # 7 passed
```
