# Clone Audit Report — `abundant-slack-clone`

- **Audited:** `2026-06-30` · **Auditor:** `clone-audit v1` · **Commit:** `36e78af` (working tree)
- **Fidelity tier (declared / observed):** `T2` / `T2` (SQLite gateway + real Slack search-operator grammar)
- **Verdict:** ❌ FAILS — *(meets = all gating reqs pass)*
- **Gating score:** ~3 / 6 gating requirement-groups pass cleanly (R1 partial, R3 partial, R4 fail, R6 fail, R2 fail on c/g/k for shipped tasks).

## TL;DR
A genuinely high-fidelity, handwritten Slack Web API clone: a FastAPI + SQLite gateway seeded from a
real Slack export, driven by a real `slack` CLI **and** the off-the-shelf korotovsky `slack-mcp`
server (5 tools, patched to hit the gateway). Envelope fidelity is excellent (`{ok:...}`, `C…`/`U…`
ids, `ts` strings, snake_case errors, Slack search operators), and all bundled tasks verified
`nop=0 / oracle=1` with reward-hack-resistant hidden graders. **But the shipped Oddish tasks run as
a single container (`main` = gateway + importer + raw export + SQLite corpus + agent tools all in
one), so the agent can `grep REFILL_RATE /data/slack-export` and read the answer key off disk** —
a hard R2.c/g/k + R6.3 isolation failure. The two-container `slack-agent` + `slack-gateway:prod-v1`
trio that would fix this **exists and is clean**, but no task uses it. The single most important
action item: **re-point the task composes at the two-container agent+gateway shape** (or otherwise
strip the export/DB/importer from `main`). Secondary: ship a `docs/COVERAGE.md` and an actual pytest
suite — there are currently **zero unit tests** in the clone.

## What it handles well
- **Real envelope fidelity** (gateway, verified live): `auth.test` returns a Slack-shaped
  `https://<ws>.slack.com/` URL; errors are real codes — `{"ok":false,"error":"channel_not_found"}`,
  `not_authed`, `unknown_method` (curl probes against a booted container), not 500s.
- **Real Slack search grammar** (T2): `_parse_search` honors `in:`/`from:`/`before:`/`after:`/`on:`
  operators + quoted phrases; search is deliberately *noisy* — a `slack search REFILL_RATE` surfaced
  both superseded (`CAPACITY=50`) and agreed (`CAPACITY=100`) values, exactly the disambiguation the
  tasks measure.
- **CLI + MCP both real and both reach one HTTP API**: `slack` CLI (6 cmds) uses `slack_sdk`
  `WebClient`; korotovsky `slack-mcp` enumerated **5 tools** over stdio and a live
  `conversations_search_messages` call returned the same rows as the CLI (parity confirmed for the
  shared capabilities).
- **Reward-hack-resistant verifiers**: graded in an isolated `/tmp` dir against a hidden
  `test_grade_*.py`; `incident-fix-report` additionally reads the agent's posted message back through
  `conversations.history` (a true write→read round-trip). Both audited tasks: `nop=0`, `oracle=1`.
- **The clean trio exists**: `slack-gateway:prod-v1` boots healthy and serves **88 channels from its
  baked DB with no mount** (R2.j infra works); `slack-agent` is a clean thin image — no `slackgw`,
  no `import_export.py`, importer not importable, no data on disk.

## Scorecard

| Req | Area | Result | Evidence | Action item (if not full pass) |
|---|---|---|---|---|
| R1 | Setup & run (Harbor) | **partial** | `nop=0 oracle=1` on buried-spec + incident-fix-report; boots healthy in 4–7s | Tasks are single-container, not 2-container agent+gateway (R1.1). Boots & scores fine, so partial not fail. |
| R2 | Architecture canon a–g + seeding j–k | **fail** | grid below; `grep REFILL_RATE=10.0 /data/slack-export` hits inside `main` | Shipped tasks leak export+DB+importer into the agent (c/g/k). Trio exists but unused. |
| R3 | CLI + MCP parity | **partial** | CLI 6 cmds, MCP 5 tools; search parity confirmed live | CLI-only `whoami`,`users`; MCP-only `conversations_replies`. Parity gap on 3 capabilities. |
| R4 | Functional coverage | **fail** | no `docs/COVERAGE.md` anywhere (`find` empty) | Write a machine-checkable `docs/COVERAGE.md`. |
| R5 | Assessment-grade endpoints | **partial** | search (operator grammar), history, post round-trip via gateway | ≥1 write→read round-trip ✅ (incident); but <5 *labelled* (no COVERAGE.md to label in) → blocked by R4. |
| R6 | Unit tests all surfaces | **fail** | no `tests/` pytest in clone; `find test_*.py` in selfcontained = empty | Ship endpoint/CLI/MCP/parity/isolation tests. |

### Canon + seeding parity grid (R2 detail) — a–i canon, j–k GHCR image DB seeding
| a | b | c | d | e | f | g | h | i | j | k |
|---|---|---|---|---|---|---|---|---|---|---|
| ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ | ⚠️ | ⚠️ | ✅ | ❌ |

Why:
- **a** ✅ base `slack-service` image exists + published (`ghcr.io/abundant-ai/slack-service`).
- **b** ✅ `slack-gateway:prod-v1` **and** `:empty` both exist (pulled locally; `Dockerfile.gateway`/`Dockerfile.empty`).
- **c** ❌ **In the shipped tasks the agent is NOT data-free**: `main` carries `/data/slack-export`,
  `/tmp/slack.db`, `/opt/slackgw`, `/opt/import_export.py`. (The separate `slack-agent` image *is* clean — but no task uses it.)
- **d** ✅ per-task data delivered by **mount** (`./data/slack-export:/data/slack-export:ro`), not a per-task image COPY of data; prod path uses overlay-by-layer.
- **e** ✅ bulk = native Slack-export format; mutations go through the shared store op-list.
- **f** ❌ shipped tasks are **single-container** (`main` only), not the 2-container agent+gateway Harbor shape; no documented isolation *exception* covers co-locating the answer key with the agent.
- **g** ❌ **operator/agent boundary broken**: the importer (`import_export.py`) is on the agent's PATH and importable; world-building is reachable from the agent.
- **h** ⚠️ identity not wired through `abundant-identity` (users are export-local). Advisory.
- **i** ⚠️ skill present (`skills/slack-clone-task-builder`) + PROD-OVERLAY doc; no `docs/COVERAGE.md` catalog. Advisory.
- **j** ✅ `slack-gateway:prod-v1` baked-DB boots **mount-free** and served 88 channels (verified live). The *tasks* don't use prod-v1 (they use `slack-service` + boot-time import), but the seeding infra passes its own probe.
- **k** ❌ **leak**: literal answer greppable in `/data/slack-export` inside `main`; `import_export`
  + `slackgw.store` importable from the agent (recomputable); **and** `slack-service`/`slack-gateway:prod-v1`
  are **amd64-only** (`docker manifest inspect` shows a single `amd64` platform + an `unknown` attestation, no `arm64`).

> **Auditor harness notes:** the trio images were already present locally
> (`slack-service:slack-mcp-oss`, `slack-gateway:prod-v1`, `:empty`, `slack-agent:slack-mcp-oss`), so
> no GHCR pull was needed. Tasks build `main` standalone from their own `environment/Dockerfile`
> (`FROM slack-service:slack-mcp-oss`), so no Harbor `main`-build override was needed — the compose
> already declares `build:`. Note the **branch-pinned tag** `slack-mcp-oss` in every task Dockerfile;
> the comment says to switch back to `:latest` on merge to main (currently still `slack-mcp-oss`).

### Coverage matrix audit (R4/R5 detail) — reconstructed (no `docs/COVERAGE.md` exists)
| Capability | Endpoint | CLI | MCP | Envelope OK | Assessment-grade | Tested |
|---|---|---|---|---|---|---|
| identity | `auth.test` | `slack whoami` | ❌ (not in enabled set) | ✅ | no | ❌ |
| list channels | `conversations.list` / `users.conversations` | `slack channels` | `channels_list` | ✅ | partial (stateful read) | ❌ |
| channel info | `conversations.info` | ❌ | ❌ | ✅ | no | ❌ |
| channel history | `conversations.history` | `slack history` | `conversations_history` | ✅ | ✅ (multi-step, paged read) | ❌ |
| thread replies | `conversations.replies` | ❌ | `conversations_replies` | ✅ | ✅ (multi-step) | ❌ |
| search messages | `search.messages`/`search.all` | `slack search` | `conversations_search_messages` | ✅ | ✅ (query grammar + stateful + multi-step) | ❌ |
| list users | `users.list` | `slack users` | ❌ | ✅ | no | ❌ |
| user info | `users.info` | ❌ | ❌ | ✅ | no | ❌ |
| team info | `team.info` | ❌ | ❌ | ✅ | no | ❌ |
| post message | `chat.postMessage`/`conversations.add_message` | `slack post` | `conversations_add_message` | ✅ | ✅ (write→read round-trip, devops comms) | ✅ (oracle exercises it) |

Counts: capabilities_total=10, with_cli=6, with_mcp=5, parity_ok=4 (channels/history/search/post),
assessment_grade≈4 (search, history, replies, post) — meets the ≥3 small-clone bar substantively,
but **R5.1 requires them *labelled* in `docs/COVERAGE.md`**, which doesn't exist → R5 blocked on R4.
tested=1 (post, via the oracle path only; no unit tests).

## Action items (ordered, for the creator loop)
1. **[R2 · gating · P0]** *Stop leaking the answer key into the agent.* **Where:** every
   `oddish/tasks/*/environment/docker-compose.yaml` + `Dockerfile`. **Fix:** split into the
   two-container shape that already exists — `main` builds `FROM ghcr.io/abundant-ai/slack-agent`
   (clean, verified) + codebase only; add a `slack` gateway service `image:
   ghcr.io/abundant-ai/slack-gateway:{prod-v1|empty}` with the export mounted into the **gateway**,
   wired by `depends_on: condition: service_healthy`. **Acceptance:** in `main`,
   `grep -rs '<answer>' /data /opt` finds nothing, `[ ! -e /data/slack-export ]`, `[ ! -e /tmp/slack.db ]`,
   and `python3 -c 'import import_export'` / `import slackgw.store` both raise ModuleNotFoundError.
2. **[R6 · gating · P0]** *Ship a unit-test suite.* **Where:** new `tests/` (clone root) or
   `selfcontained/base/tests/`. **Fix:** cover every endpoint (happy + error envelope), every CLI
   command, every MCP tool, a **parity** test (CLI vs MCP same data), and an **isolation** test
   (no seed on disk, importer not importable). Wire into CI. **Acceptance:** `pytest -q` green from a
   cold boot, counts reported, isolation test asserts the R6.3 conditions.
3. **[R4 · gating · P1]** *Add `docs/COVERAGE.md`.* **Where:** `docs/COVERAGE.md`. **Fix:** one row
   per capability mapping endpoint ↔ CLI ↔ MCP ↔ envelope ↔ assessment-grade ↔ tested (use the matrix
   above as the seed); mark the ≥5 assessment-grade rows. **Acceptance:** matrix exists, ≥5 rows
   labelled assessment-grade, each maps to a real endpoint + CLI + MCP or is marked N/A with reason.
4. **[R3 · gating · P1]** *Close the CLI↔MCP parity gaps.* **Where:** `slackcli/slackcli/cli.py`
   (+ `client.py`) and `mcp/slack-mcp.sh` `SLACK_MCP_ENABLED_TOOLS`. **Fix:** add a `slack replies`
   CLI command (MCP has `conversations_replies`, CLI doesn't); decide whether `whoami`/`users` are
   operator-only (document) or add MCP equivalents. **Acceptance:** every non-operator capability has
   both a CLI command and an MCP tool; a parity test passes for each.
5. **[R2.k · gating · P1]** *Publish multi-arch.* **Where:** `.github/workflows/build-service-image.yml`
   (and the gateway/seed build paths). **Fix:** `platforms: linux/amd64,linux/arm64`. **Acceptance:**
   `docker buildx imagetools inspect ghcr.io/abundant-ai/slack-gateway:prod-v1` lists both arches.
6. **[R1 · advisory · P2]** *Remove the stale Mattermost gateway.* **Where:** repo-root `slackgw/app.py`
   is a dead Mattermost-translation copy (httpx to `MM_URL`) that contradicts the README's "no
   Mattermost" claim; the live gateway is `selfcontained/base/slackgw/app.py` (SQLite). Delete or
   clearly mark the dead copy. **Acceptance:** only the SQLite gateway remains; README matches.

## Reproduction
```bash
# Build + boot buried-spec (single-container), confirm health + CLI + envelopes
cd oddish/tasks/buried-spec/environment
docker build -t buried-spec-main:audit .          # FROM slack-service:slack-mcp-oss (local)
docker run -d --name bs-audit -v "$PWD/data/slack-export:/data/slack-export:ro" buried-spec-main:audit
docker exec bs-audit curl -sf http://localhost:80/api/auth.test         # healthy ~7s
docker exec bs-audit slack channels                                     # C… ids, # names
docker exec bs-audit slack search REFILL_RATE                           # noisy: superseded + agreed
docker exec bs-audit sh -c 'curl -s "http://localhost:80/api/conversations.info?channel=C_NOPE" -H "Authorization: Bearer xoxp-acme-eval-0001"'  # {"ok":false,"error":"channel_not_found"}

# MCP: 5 tools over stdio, search reaches the gateway (parity)
docker exec -i bs-audit sh -c 'printf "%s\n" <initialize> <initialized> <tools/list> | slack-mcp'   # 5 tools
# -> channels_list, conversations_add_message, conversations_history, conversations_replies, conversations_search_messages

# Isolation LEAK (the R2.k/R6.3 failure)
docker exec bs-audit sh -c '[ -e /data/slack-export ] && echo LEAK; [ -e /tmp/slack.db ] && echo LEAK'  # both LEAK
docker exec bs-audit python3 -c 'import import_export'                  # imports OK (recomputable)
docker exec bs-audit sh -c "grep -rs 'REFILL_RATE=10.0' /data/slack-export | head -1"  # answer on disk

# nop / oracle (R1.3) — buried-spec and incident-fix-report
docker cp ../tests bs-audit:/tests; docker cp ../solution bs-audit:/solution
docker exec bs-audit bash /tests/run_verifier.sh; docker exec bs-audit cat /logs/verifier/reward.txt   # nop=0
docker exec bs-audit bash /solution/solve.sh; docker exec bs-audit bash /tests/run_verifier.sh         # oracle=1

# R2.j: prod-v1 baked DB serves mount-free
docker run -d --name gw-prod ghcr.io/abundant-ai/slack-gateway:prod-v1
docker exec gw-prod curl -s http://localhost:80/api/conversations.list -H "Authorization: Bearer xoxp-acme-eval-0001"  # 88 channels, no mount

# slack-agent thin image is clean (the trio that tasks SHOULD use)
docker run --rm --entrypoint sh ghcr.io/abundant-ai/slack-agent:slack-mcp-oss -c 'ls /opt/slackgw'   # No such file
docker run --rm --entrypoint python3 ghcr.io/abundant-ai/slack-agent:slack-mcp-oss -c 'import import_export'  # ModuleNotFoundError
```
