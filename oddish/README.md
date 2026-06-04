# Oddish tasks (Slack-clone)

Oddish-runnable, **self-contained** multi-service tasks. Each task is a seeded Slack
workspace (the `slack` service, built from the vendored slackclone package) plus an agent
container (`client`) that has **`slack-cli`** pointed at it (`SLACK_API_URL=http://slack:3000`).
The agent operates the workspace only through the tools; the verifier reads state back via
the Slack API, so scoring is deterministic (`nop`=0, `oracle`=1).

> Self-containment: build contexts live inside `tasks/<name>/environment/` (the slackclone
> package is vendored there), so `oddish run` uploads and builds each task with **no**
> references outside the task directory.

## Layout

```
oddish/
  slack-clone-manifest.yaml      # create-oddish-task manifest (task_path, tasks, agents)
  sweep.yaml                     # oddish CLI sweep config
  tasks/
    slack-incident-triage/
      task.toml  instruction.md
      environment/
        Dockerfile               # client (agent) image — installs slack-cli
        docker-compose.yaml      # client + slack
        slack/{Dockerfile,entrypoint.sh}
        slackclone/              # vendored package (src + pyproject)
        data/slack/workspace.json
      solution/solve.sh          # oracle
      tests/{test.sh, run_verifier.sh}   # split-harness verifier (reads state via the API)
```

## Run via Oddish

```bash
cd /path/to/oddish/oddish
uv run oddish run /path/to/abundant-slack-clone/oddish/tasks \
  -a gemini-cli -m google/gemini-3.1-flash-preview --n-trials 1
# or with the sweep config:
uv run oddish run .../oddish/tasks -c .../oddish/sweep.yaml
```

## Local validation (per task)

```bash
cd oddish/tasks/slack-incident-triage/environment
docker compose config                 # renders client + slack
docker compose up -d --build          # slack goes healthy, then client
docker cp ../tests   client:/tests
docker cp ../solution client:/solution
docker compose exec -T client bash /tests/run_verifier.sh   # nop  -> reward 0
docker compose exec -T client bash /solution/solve.sh
docker compose exec -T client bash /tests/run_verifier.sh   # oracle -> reward 1
docker compose down -v
```

## Add a new task
Copy `tasks/slack-incident-triage`, swap `environment/data/slack/workspace.json` (author it
with `slack-cli seed generate|import-export|load --emit workspace.json`), rewrite
`instruction.md` + `solution/solve.sh` + `tests/run_verifier.sh`, and add the name to the
manifest/sweep. Keep the `environment/slackclone/` vendored copy in sync with the repo's `src/`.
