# Oddish tasks (Slack-clone)

Oddish-runnable, **data-free** multi-service tasks. Each task is the shared `slack` service
(seeded with a named workspace from its baked-in catalog) plus an agent container (`client`)
that has **`slack-cli`** and the **`slack-mcp`** MCP server pointed at it
(`SLACK_API_URL=http://slack:3000`). The agent operates the workspace only through the tools;
the verifier reads state back via the Slack API, so scoring is deterministic (`nop`=0,
`oracle`=1).

> **No seed data in any task directory.** Canonical workspaces live in the repo-level
> [`workspaces/`](../workspaces/) folder and are baked into the slack image. A task just names
> the one it wants (`SLACK_WORKSPACE=<name>`), so the answer key is never sitting next to the
> task. See [docs/architecture.md](../docs/architecture.md).

## Tasks

Instructions are deliberately **open-ended** — the agent gets a vague "something's wrong"
nudge and must discover the channel, the facts, and the fix using its Slack tools, with no
spelled-out commands. The "verifier checks" column below is what success looks like to the
grader, **not** what the agent is told.

| Task | Workspace | Surfaces flexed | Verifier checks (not shown to agent) |
|---|---|---|---|
| [`slack-incident-triage`](tasks/slack-incident-triage/) | `acme-incident` | history, threads, search, **post** | A new message in #incidents naming the connection-pool cause (phrasing-independent). |
| [`slack-search-retrieval`](tasks/slack-search-retrieval/) | `globex-staging` | **search/retrieval** across channels w/ decoys, post | A reply in #ask-platform with the *current* staging Postgres `host:port` (not the stale/decoy hosts). |
| [`slack-thread-summary-pin`](tasks/slack-thread-summary-pin/) | `hooli-decisions` | threads (replies), post, **pins** | A new **pinned** message in #design-decisions naming the chosen library (react-aria). |

`nop`→reward 0, `oracle`→reward 1, verified by reading workspace state back through the Slack API.

## Layout (self-contained, per the Harbor multi-container recipe)

Each task is **self-contained**: its `environment/` holds everything needed to build, so it
works in Harbor's per-task sandbox (Modal/DinD included), where only the task directory is
uploaded. Harbor auto-provides the agent (`main`) container and **merges** the task's
`docker-compose.yaml` on top — the task only overrides `main` and adds the `slack` service.

```
workspaces/                        # canonical seeds (source of truth; repo root, NOT under oddish/)
  {acme-incident,globex-staging,hooli-decisions}.json
docker/                            # standalone shared images + control plane (local dev / non-Harbor)
oddish/
  slack-clone-manifest.yaml  sweep.yaml
  tasks/
    slack-incident-triage/         # (and slack-search-retrieval/, slack-thread-summary-pin/)
      task.toml  instruction.md
      environment/
        Dockerfile                 # the agent (`main`) image: installs slack-cli + slack-mcp
        docker-compose.yaml        # overrides `main` (SLACK_API_URL + depends_on) and adds `slack`
        slackclone/                # vendored package CODE (kept in sync with ../../../../src)
        slack/
          Dockerfile               # service image: build context = environment/ (self-contained)
          entrypoint.sh            # seeds from the baked workspace.json, then serves
          workspace.json           # THIS task's single seed (copy of a workspaces/<name>.json)
      solution/solve.sh            # oracle
      tests/{test.sh, run_verifier.sh}   # split-harness verifier (reads state via the API)
```

> **Data location & anti-cheat.** Each task's one workspace seed lives at
> `environment/slack/workspace.json` so the service can build self-contained in the sandbox. It
> is COPYed **only** into the `slack` service image — never the agent image, and Harbor does not
> mount the task source into the agent — so the agent still can't read the answer; it must use
> the tools. (This is the tradeoff the Harbor recipe requires vs. a fully data-free task dir.)

## Run via Oddish

```bash
uv run oddish run /path/to/abundant-slack-clone/oddish/tasks \
  -a gemini-cli -m google/gemini-3.1-pro-preview --n-trials 1
# or:  uv run oddish run .../oddish/tasks -c .../oddish/sweep.yaml
```

## Local validation (per task)

Harbor supplies the `main` service, so for a plain `docker compose` run, simulate it with a
throwaway base file:

```bash
T=oddish/tasks/slack-incident-triage/environment
cat > "$T/docker-compose.base.yaml" <<'EOF'
services:
  main: { build: { context: ., dockerfile: Dockerfile }, command: ["sh","-c","sleep infinity"] }
EOF
dc() { docker compose -f "$T/docker-compose.base.yaml" -f "$T/docker-compose.yaml" --project-directory "$T" "$@"; }
dc up -d --build --wait
dc cp oddish/tasks/slack-incident-triage/tests    main:/tests
dc cp oddish/tasks/slack-incident-triage/solution main:/solution
dc exec -T main bash /tests/run_verifier.sh    # nop    -> reward 0
dc exec -T main bash /solution/solve.sh
dc exec -T main bash /tests/run_verifier.sh    # oracle -> reward 1
dc down -v && rm -f "$T/docker-compose.base.yaml"
```

## Add a new task
1. Author a canonical workspace (e.g. `slack-cli seed generate|load --emit workspaces/<name>.json`).
2. Copy an existing task dir. Replace `environment/slack/workspace.json` with your new workspace,
   refresh the vendored `environment/slackclone/` from `src/`, and rewrite `instruction.md` +
   `solution/solve.sh` + `tests/run_verifier.sh`.
3. Add the name to the manifest/sweep.
