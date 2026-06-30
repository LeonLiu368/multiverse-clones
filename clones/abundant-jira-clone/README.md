# abundant-jira-clone

A self-contained **Jira clone** for agent-eval tasks, mirroring the
[Slack clone](../abundant-slack-clone-mattermost/) infrastructure but backed by the
**ticketvector** issue service + the **`jira` CLI**.

The model is identical to the Slack clone's: a task is two containers — a **thin agent** (tools
only, no data) plus a **service sidecar** holding the issue data — and the agent reaches the data
**only over HTTP via the `jira`/`linear` CLI**, never off disk. A verifier reads the agent's answer
and recomputes ground truth through the same tool.

## The three images

Built on `ghcr.io/abundant-ai/ticketvector-service:latest` (the published ticketvector service;
currently **linux/amd64** — see "Architecture note"). Build them with
`selfcontained/base/build.sh`.

| Image | What it is | Slack analogue |
|---|---|---|
| **`jira-gateway:prod-v1`** | ticketvector service with the real **ENG** Jira corpus (8040 issues / 14997 comments / 22 users) BAKED in at `/var/lib/ticketvector/state.json`. Served on `:8765`. | `slack-gateway:prod-v1` |
| **`jira-gateway:empty`** | ticketvector service with **no data** (the stock image's demo `PAY` state is deleted). A task MOUNTS its own `state.json` at `/var/lib/ticketvector/state.json:ro`. | `slack-gateway:empty` |
| **`jira-agent:latest`** | the THIN AGENT base: `jira` + `linear` CLI **and** the `jira-mcp` MCP server, **no service, no data, no state.json, and no gateway API/seed source**. Tasks build their `main` FROM this + their codebase. Both surfaces run in `WORLD_ISSUES_BACKEND=remote` mode and POST to the sidecar at `PLANE_BASE_URL=http://jira:8765`. | `slack-agent` |

The agent never receives a gateway image — only HTTP access to one.

## Tool surface: CLI **and** MCP, in parity (R3)

The agent operates the clone through **two** surfaces, both thin clients of the **same**
ticketvector `POST /rpc` HTTP API on the `jira` sidecar:

- **CLI** — `jira` / `linear` (from the ticketvector image), e.g. `jira jql "<JQL>"`,
  `jira issue view <ID> --comments`, `jira issue transition <ID> "Done"`,
  `jira issue comment add <ID> --body "..."`.
- **MCP** — `jira-mcp` (this repo's `mcp/`), a stdio MCP server mirroring the CLI 1:1:
  `get_issue`, `search_issues` (JQL + filters), `get_comments`, `list_projects/states/labels`,
  `issue_mine`, `list_links`, `issue_history`, `transition_issue`, `add_comment`.

The full capability → endpoint → CLI → MCP map is in **`docs/COVERAGE.md`** (14 capabilities,
5 labelled assessment-grade). CLI↔MCP parity is proven by `tests/test_parity.py` (the real CLI
dispatch vs the matching MCP tool return identical data). The `mcp/` package imports **nothing**
from `world_issues` — it is a self-contained `/rpc` client — which is what lets the agent image
strip the gateway source (below).

## Leak-stripped agent (R2.k)

`selfcontained/base/Dockerfile.agent` no longer copies the ticketvector package wholesale. It runs
`strip_agent_tooling.py`, which **deletes** the gateway's API + world-builder source
(`server/seed/plane/demo/runtime/snapshot.py`) and patches `cli.py` so the remaining thin-client
CLI still imports. Verified in the agent image: `import world_issues.seed` raises
`ModuleNotFoundError`, no `seed`/`server` source survives on disk, and a literal grep for any answer
finds nothing. The corpus DB was never in the package, so nothing is greppable **or** recomputable.

## The prod corpus (ENG)

`selfcontained/base/data/eng-prod-state.json` is the "Jira prod corpus": project **ENG**, produced
by `tools/jira_to_state.py` from the real native Jira XML export
(`/Users/leonliu/Downloads/jira/entities.xml`). It is the runtime `state.json` shape the ticketvector
service serves. Regenerate with:

```bash
python3 tools/jira_to_state.py --entities /path/to/entities.xml --project ENG \
    --out selfcontained/base/data/eng-prod-state.json
# -> 8040 issues / 14997 comments / 22 users
```

The converter's synthetic naming (deterministic `First Last` / `first.last` handles, hashed on a
cross-system person key) is used **as-is**. A shared cross-clone identity registry is being built in
parallel and will unify Slack/Jira names later; the hook is the `name:<n>` registry key in
`jira_to_state.py` (`_person_key`), which is the same id that appears in the Slack corpus. Don't
block on it.

## Per-task seeding: two mechanisms

ticketvector loads a **single** `state.json` — there is no boot-time overlay-merge like the Slack
gateway. So a task seeds its data one of two ways:

1. **Prod corpus, baked (no mount):** use `jira-gateway:prod-v1` as the sidecar as-is. Best for read
   tasks over the real ENG corpus. (Task: `jira-status-lookup`.)
2. **Custom project, mounted on empty:** use `jira-gateway:empty` and mount a full
   `state.json` at `/var/lib/ticketvector/state.json:ro`. Best for clean, low-cardinality,
   deterministic tasks. (Task: `jira-assignee-count`.)

   A third path — bake prod-with-planted-issues into a per-dataset gateway tag — is available if a
   task needs the heavy ENG corpus *plus* its own planted issues; just `COPY` a merged state into a
   new `jira-gateway:<dataset>` tag. (Not needed by the two smoke tasks.)

## Isolation model

- The agent container has **no `state.json` on disk** (verified in the smoke test). The issue data
  lives only in the sidecar.
- The agent reaches issues only through the `jira`/`linear` CLI, which is a thin HTTP client of the
  sidecar's `/rpc` endpoint. `WORLD_ISSUES_AGENT_MODE=1` blocks the admin/seed/runtime subcommands.
- The verifier recomputes ground truth live through the same CLI — it never trusts the agent's
  narration, so a hardcoded-but-wrong answer scores 0.

## Tasks

Harbor-shaped (`custom_docker_compose = true`), two containers, no `networks:` block:

```
tasks/<name>/
  task.toml                       custom_docker_compose=true
  instruction.md
  environment/
    Dockerfile                    FROM jira-agent:latest + COPY codebase
    docker-compose.yaml           main + jira sidecar (prod-v1 or empty+mount)
    codebase/                     /workspace contents
    data/state.json               (empty-gateway tasks only) the mounted project
  tests/test.sh                   writes /logs/verifier/reward.txt
  solution/solve.sh               oracle
```

| Task | Sidecar | Question | Answer | Seeding |
|---|---|---|---|---|
| `jira-status-lookup` | `jira-gateway:prod-v1` | status + assignee of **ENG-2016** | `Done` / `Priya Fischer` | prod corpus baked |
| `jira-assignee-count` | `jira-gateway:empty` | # WEB issues assigned to **Priya Singh** | `4` | custom state mounted |
| `jira-transition-roundtrip` | `jira-gateway:empty` | close the checkout-bug issue (transition→Done + comment) | `WEB-7` | custom state mounted; **write→read** (R5.2) |

## Smoke test

```bash
selfcontained/base/build.sh     # build the three images
selfcontained/smoke.sh          # run both tasks end-to-end on a docker network
```

The smoke runner, for each task: builds `main`, starts the sidecar + agent on a network, asserts the
agent has **no `state.json`**, runs **nop → reward 0**, runs **oracle (`solve.sh`) → reward 1**.
Last run (native arm, amd64 emulation): **pass=2 fail=0, ALL GREEN**.

## Architecture note

`ghcr.io/abundant-ai/ticketvector-service:latest` is currently **linux/amd64-only**. On arm it runs
under emulation (verified: boots healthy in ~2-4s, serves RPC). All builds pin `--platform
linux/amd64`. Once the base is republished multi-arch, drop the pins / build the gateway+agent
multi-arch.

## Follow-up (not done here)

- **GHCR push:** `jira-gateway:prod-v1`, `jira-gateway:empty`, `jira-agent:latest` are built
  **locally only**. Tag/push to `ghcr.io/abundant-ai/*` (multi-arch via buildx) before any Harbor /
  Oddish cloud run, then point the task composes at the GHCR refs (already the default
  `${JIRA_GATEWAY_IMAGE}` value).
- **Harbor / Oddish run:** the two tasks are smoke-tested locally; run them through Harbor + an
  Oddish oracle/nop sweep to confirm in the cloud harness.
- **Identity registry:** wire the cross-clone Slack/Jira name unification when it lands (hook noted
  above).
