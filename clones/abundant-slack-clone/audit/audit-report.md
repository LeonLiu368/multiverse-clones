# Clone Audit Report — `abundant-slack-clone`

- **Audited:** `2026-06-30` · **Auditor:** `clone-audit v1` (RE-AUDIT after fix pass) · **Commit:** `b2b2abd`
- **Fidelity tier (declared / observed):** `T2` / `T2`
- **Verdict:** ✅ MEETS STANDARD  — *(meets = all gating reqs pass)*
- **Gating score:** `6/6` gating requirements pass.

## TL;DR
A faithful T2 Slack Web API clone (handwritten SQLite gateway + real search-operator grammar),
operated through a `slack` CLI and the korotovsky `slack-mcp` server that are both thin HTTP clients
of one gateway. The Round-1 blocker — shipped tasks co-located the answer key with the agent — is
**fixed and independently re-confirmed**: all 5 Oddish tasks now run as the two-container
agent+gateway shape, and direct leak probes in the live `main` container come up clean. The clone is
**usable for agent assessment today**; remaining items are non-gating P2 polish (flip branch-scoped
image tags back to `:latest` and verify the published multi-arch manifests before merge).

## What it handles well
- **2-container isolation is real, not just declared.** In a booted `main` (incident-fix-report and
  buried-spec): no `/data/slack-export`, no `/tmp/slack.db`, `import import_export` and `import slackgw`
  both `ModuleNotFoundError`, and a full-disk grep for the policy answer (`0.05`/`should_page`) hits
  only OS libraries. The answer is reachable only via the gateway over HTTP.
- **Bundled task discriminates agents.** incident-fix-report: nop=0 (14 hidden-grader cases fail on the
  unimplemented `should_page`), oracle=1, requiring BOTH a code fix and a `slack post` write→read
  round-trip the verifier reads back via `conversations.history`.
- **prod-v1 ships its corpus.** Boots mount-free and serves 88 channels; `:empty` + mounted export is
  the same image minus the baked DB — switching is the tag alone.
- **Full cold-boot test suite.** `tests/test.sh` builds images fresh and runs 40 tests green (endpoint
  happy+error, CLI, MCP, parity, isolation).

## Scorecard

| Req | Area | Result | Evidence | Action item (if not full pass) |
|---|---|---|---|---|
| R1 | Setup & run (Harbor) | pass | 2 containers boot, gateway healthy, `nop=0 oracle=1`, prod-v1 88ch mount-free | — |
| R2 | Architecture canon a–k | pass | leak probes clean in `main` (2 tasks); CI multi-arch declared | P2: flip tags to `:latest`, verify published manifests |
| R3 | CLI + MCP parity | pass | CLI 7 cmds incl `replies`; MCP exactly 5 tools; live search parity | — |
| R4 | Functional coverage | pass | `docs/COVERAGE.md` machine-checkable, 10 caps | — |
| R5 | Assessment-grade endpoints | pass | 5 AG rows labelled; write→read round-trip confirmed live | — |
| R6 | Unit tests all surfaces | pass | `40 passed / 40` from cold boot | — |

### Canon + seeding parity grid (R2 detail)
| a | b | c | d | e | f | g | h | i | j | k |
|---|---|---|---|---|---|---|---|---|---|---|
| ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

- **c/g (no seed on agent):** `[ ! -e /data/slack-export ]` and `[ ! -e /tmp/slack.db ]` both PASS in `main`.
- **k (no recomputable leak + multi-arch):** importer/store not importable; answer not greppable;
  multi-arch declared in CI (`build-service-image.yml` PLATFORMS=linux/amd64,linux/arm64;
  `build-seed-image.yml --platform linux/amd64,linux/arm64`). Accepted locally per the hardened R2.k
  rule (registry manifest not re-pulled in this audit — see P2 item).
- **f (no networks:):** confirmed absent; Harbor injects `network_mode`; agent waits on gateway
  `depends_on: service_healthy`.
- **j (prod-v1 baked DB):** boots mount-free, `conversations.list` → 88 channels.

> **Auditor harness notes:** local host is arm64; task compose pins `platform: linux/amd64`, and the
> local `slack-agent`/`slack-service`/`slack-gateway:empty` images are arm64. Booted with a tiny
> `platform: linux/arm64` compose override to run on the host (registry arm manifest not re-pulled).
> This is exactly the hardened-R2.k "multi-arch CI declaration acceptable locally" allowance. Shared
> Docker host: used `COMPOSE_PROJECT_NAME=slackre`/`slackre2` and `:audit` tags throughout; all audit
> containers torn down.

### Coverage matrix audit (R4/R5 detail) — from `docs/COVERAGE.md`, spot-verified live
| Capability | Endpoint | CLI | MCP | Envelope OK | Assessment-grade | Tested |
|---|---|---|---|---|---|---|
| List channels | `conversations.list` | `slack channels` | `channels_list` | ✅ | ✅ AG | ✅ |
| Channel history | `conversations.history` | `slack history` | `conversations_history` | ✅ | ✅ AG | ✅ |
| Thread replies | `conversations.replies` | `slack replies` | `conversations_replies` | ✅ | ✅ AG | ✅ |
| Search messages | `search.messages` | `slack search` | `conversations_search_messages` | ✅ | ✅ AG (operator grammar) | ✅ |
| Post message | `chat.postMessage` | `slack post` | `conversations_add_message` | ✅ | ✅ AG (write→read) | ✅ |
| Identity/users/team/info | `auth.test`,`users.*`,`team.info`,`conversations.info` | partial (`whoami`,`users`) | — operator-only (note A) | ✅ | no | ✅ (HTTP/CLI) |

**5 assessment-grade** capabilities labelled; write→read round-trip (post → history) exercised
end-to-end and confirmed live in the oracle run.

## Action items (ordered, for the creator loop)
1. **[R2 · advisory P2]** Before merge to main, flip branch-scoped tags (`slack-mcp-oss`) back to
   `:latest` in `oddish/tasks/*/environment/Dockerfile` (FROM) and `selfcontained/base/Dockerfile.agent`
   + `Dockerfile.empty` (`SLACK_SERVICE` ARG), then `docker buildx imagetools inspect
   ghcr.io/abundant-ai/slack-gateway:prod-v1` to confirm the published manifest lists amd64 AND arm64.
2. **[R1 · advisory P2]** If a stale repo-root `slackgw/app.py` (dead Mattermost-translation gateway)
   still exists, remove it; the live gateway is `selfcontained/base/slackgw/app.py`.

## Reproduction
```bash
export COMPOSE_PROJECT_NAME=slackre
# arch override (host is arm64; compose pins amd64 — hardened R2.k local allowance)
printf 'services:\n  main: {platform: linux/arm64}\n  slack: {platform: linux/arm64}\n' > /tmp/ov.yaml

# --- R1/R2: boot the 2-container task + leak probes ---
cd clones/abundant-slack-clone/oddish/tasks/incident-fix-report/environment
APEX_TASK_DOCKER_CLIENT_IMAGE_NAME=slackre-incident-main:audit \
  docker compose -f docker-compose.yaml -f /tmp/ov.yaml up -d --build
M=slackre-main-1
docker exec $M sh -c '[ ! -e /data/slack-export ] && echo "PASS no export"'   # PASS
docker exec $M sh -c '[ ! -e /tmp/slack.db ] && echo "PASS no db"'             # PASS
docker exec $M python3 -c 'import import_export'                                # ModuleNotFoundError
docker exec $M python3 -c 'import slackgw'                                      # ModuleNotFoundError
docker exec $M sh -c 'grep -rIl -e "0.05" -e "should_page" / 2>/dev/null | grep -vE "^/(proc|sys)"'  # only OS libs

# --- prod-v1 mount-free 88 channels ---
docker run -d --name slackre-prodv1 --platform linux/amd64 ghcr.io/abundant-ai/slack-gateway:prod-v1
docker exec slackre-prodv1 sh -c 'curl -sS http://localhost:80/api/conversations.list?limit=1000 \
  -H "Authorization: Bearer xoxp-acme-eval-0001" | jq "{ok:.ok, n:(.channels|length)}"'  # {ok:true, n:88}

# --- nop / oracle on the re-pointed task ---
docker cp tests $M:/verifier
docker exec $M sh -c 'bash /verifier/test.sh; cat /logs/verifier/reward.txt'   # nop -> 0
docker cp solution/solve.sh $M:/tmp/solve.sh
docker exec $M sh -c 'bash /tmp/solve.sh && bash /verifier/test.sh; cat /logs/verifier/reward.txt'  # oracle -> 1

# --- R3: CLI tree + MCP tool list ---
docker exec $M slack --help            # whoami,channels,users,history,replies,search,post
docker exec $M slack replies --help    # present
# MCP tools/list over stdio -> 5 tools (channels_list, conversations_{history,replies,add_message,search_messages})

# --- R6: full suite from cold ---
cd clones/abundant-slack-clone && SLACK_TEST_TAG=slackre-audit bash tests/test.sh
# 34 passed (in-gateway: endpoints+cli+mcp+parity) + 6 passed (isolation) = 40/40, reward=1
```
