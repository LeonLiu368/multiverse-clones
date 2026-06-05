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

| Task | Workspace | Surfaces flexed | Goal → verified by |
|---|---|---|---|
| [`slack-incident-triage`](tasks/slack-incident-triage/) | `acme-incident` | history, threads, search, **post** | Read the #incidents thread, post a `ROOT CAUSE:` summary naming the connection-pool cause. |
| [`slack-search-retrieval`](tasks/slack-search-retrieval/) | `globex-staging` | **search/retrieval** across channels w/ decoys, post | Find the *current* staging Postgres `host:port` (ignoring stale/decoy hosts) and answer in #ask-platform. |
| [`slack-thread-summary-pin`](tasks/slack-thread-summary-pin/) | `hooli-decisions` | threads (replies), post, **pins** | Read the decision thread, post a `DECISION:` summary and **pin** it in #design-decisions. |

`nop`→reward 0, `oracle`→reward 1, verified by reading workspace state back through the Slack API.

## Layout

```
workspaces/                        # canonical seeds (repo root, NOT under oddish/) — baked into the image
  {acme-incident,globex-staging,hooli-decisions}.json
docker/{Dockerfile,client.Dockerfile,entrypoint.sh}   # shared slack + client images (built once)
oddish/
  slack-clone-manifest.yaml        # create-oddish-task manifest (task_path, tasks, agents)
  sweep.yaml                       # oddish CLI sweep config
  tasks/
    slack-incident-triage/         # (and slack-search-retrieval/, slack-thread-summary-pin/)
      task.toml  instruction.md
      environment/
        docker-compose.yaml        # references shared images; sets SLACK_WORKSPACE  (NO data, NO vendored pkg)
      solution/solve.sh            # oracle
      tests/{test.sh, run_verifier.sh}   # split-harness verifier (reads state via the API)
```

## Run via Oddish

```bash
cd /path/to/oddish/oddish
uv run oddish run /path/to/abundant-slack-clone/oddish/tasks \
  -a gemini-cli -m google/gemini-3.1-pro-preview --n-trials 1
# or with the sweep config:
uv run oddish run .../oddish/tasks -c .../oddish/sweep.yaml
```

> Image availability: tasks reference the shared `abundant-slack-clone:latest` /
> `abundant-slack-client:latest` images. The composes also carry a `build:` (context = repo
> root) so plain `docker compose` builds them from a full checkout. If your Oddish runtime
> uploads only the task subtree, pre-build/publish these images first.

## Local validation (per task)

```bash
# build the two shared images once (from repo root)
docker build -f docker/Dockerfile        -t abundant-slack-clone:latest .
docker build -f docker/client.Dockerfile -t abundant-slack-client:latest .

cd oddish/tasks/slack-incident-triage/environment
docker compose up -d --build          # slack seeds 'acme-incident', goes healthy, then client
docker cp ../tests   client:/tests
docker cp ../solution client:/solution
docker compose exec -T client bash /tests/run_verifier.sh   # nop  -> reward 0
docker compose exec -T client bash /solution/solve.sh
docker compose exec -T client bash /tests/run_verifier.sh   # oracle -> reward 1
docker compose down -v
```

## Add a new task
1. Add a canonical workspace to [`workspaces/`](../workspaces/) (author it with
   `slack-cli seed generate|import-export|load --emit workspaces/<name>.json`) and rebuild the
   slack image so the catalog includes it.
2. Copy `tasks/slack-incident-triage`, set `SLACK_WORKSPACE=<name>` in
   `environment/docker-compose.yaml`, and rewrite `instruction.md` + `solution/solve.sh` +
   `tests/run_verifier.sh`. **No data files go in the task.**
3. Add the name to the manifest/sweep.
