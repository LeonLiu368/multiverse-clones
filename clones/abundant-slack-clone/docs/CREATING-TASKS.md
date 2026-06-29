# Creating a new task

These are **observability + codebase** tasks on the **single-container Slack artifact**: a failing
pytest suite at `/workspace` whose fix depends on a fact buried in heavy Slack chat that the agent
reaches via the Slack Web API. The full checklist lives in the **`slack-observability-task-builder`**
skill — invoke it when building one. Quick version:

## The two bars (non-negotiable)
1. **Tool use is CRITICAL** — the fact is only in chat; a hidden grader (params only in chat) makes
   it unobtainable from the repo/visible tests.
2. **Tool use is NON-TRIVIAL** — superseded/contradictory values, off-channel traps, a red herring;
   search surfaces the wrong hits too, so the agent must read & disambiguate.

## The backend is one prebuilt image (task builds FROM it)
The whole backend — the SQLite-backed Slack gateway, the importer, our `slack` CLI, and the
korotovsky `slack-mcp` binary — is the single image `ghcr.io/abundant-ai/slack-service`, built once
from `selfcontained/base/Dockerfile.service` and pushed by CI. The task's `Dockerfile` does
`FROM ghcr.io/abundant-ai/slack-service:latest` and adds only the codebase. No Mattermost/Postgres.
See [IMAGE-RELEASE.md](IMAGE-RELEASE.md).

## Anatomy (copy an existing task — e.g. `buried-spec`)
```
tasks/<name>/
  task.toml            # service="slack", tools=["slack-cli","slack-mcp"] + [[environment.mcp_servers]] stdio slack-mcp
  instruction.md       # symptom + "you have the slack CLI + MCP"; NEVER the buried fact
  environment/
    Dockerfile           # FROM slack-service:latest + codebase (Harbor builds `main`)
    main-entrypoint.sh   # imports the export -> SQLite, starts the gateway, keepalive
    docker-compose.yaml  # single `main` service: build + ./data/slack-export mount + healthcheck
    data/
      generate.py        ← YOU WRITE: builds the message list + planted fact; writes data/slack-export/
      slack-export/      ← GENERATED + COMMITTED: a real Slack export (channels.json, users.json, <ch>/<date>.json)
    codebase/          ← YOU WRITE: working module(s) [tests pass] + a stub/buggy target [fails] + a breadcrumb to Slack
  solution/solve.sh    ← YOU WRITE: oracle edits /workspace; for comms tasks also `slack post <channel> "..."`
  tests/
    test.sh            # orchestration — copy
    run_verifier.sh    ← YOU WRITE/ADAPT: grade in /tmp (candidate pkg + trusted tests, python3); comms via the gateway
    trusted/           ← YOU WRITE: canonical visible tests + the HIDDEN test_grade_*.py
```
The three build files (`Dockerfile`, `main-entrypoint.sh`, `docker-compose.yaml`) are identical
across tasks — **don't hand-copy them**: they live once in `selfcontained/base/`; run
`bash selfcontained/base/vendor.sh` to push them into every task.

## The seed is a real Slack export
`generate.py` builds the usual deterministic list of `{channel, author, content, timestamp}` dicts
(story arc + distractors + the planted fact), then calls the shared
[`slack_export_writer.write_export`](../selfcontained/base/slack_export_writer.py) helper to write a
**real Slack export** under `data/slack-export/` (committed). The importer ingests it at boot. To
build a seed from *real* workspace data instead, sample the export corpus with `import_export.py`
filters (`--channels`, `--start/--end`) and inject the planted thread — see
[REAL-SLACK-IMPORT.md](REAL-SLACK-IMPORT.md).

## The files you write (per task)
- **`data/generate.py`** → ~500 deterministic noisy messages; inject SUPERSEDED values early + the
  agreed values later + off-channel traps; call `write_export(...)`; commit `data/slack-export/`.
- **`codebase/`** → a working module (tests pass) + the stub/buggy target (tests fail) with a
  docstring/README/error breadcrumb pointing to the workspace chat.
- **`instruction.md`** → symptom + the two tool surfaces; never the buried fact.
- **`solution/solve.sh`** → oracle: edit `/workspace`; for comms, `slack post <channel> "..."`.
- **`tests/trusted/`** → invariant-only visible tests + the HIDDEN `test_grade_*.py`. **Must be
  `test_grade_*.py`** or pytest won't collect it (false-pass hole).
- **`tests/run_verifier.sh`** → copy candidate pkg + trusted tests to `/tmp/grade.$$`, run
  `python3 -m pytest` there; for comms, read back via `conversations.history` on `${SLACK_API_URL}`.
  **Use `python3`, not `python`** (the slim base has no `python` symlink).

## Two rules that keep it reliable
- **Key reward on the fixed state.** Confirm a deliberately-wrong-but-invariant impl still → 0.
- **Comms tasks:** the channel you post to must exist in the seed (seed at least one message there).

## Validate before shipping (always)
```bash
cd tasks/<name>/environment
docker compose up -d --build   # builds FROM slack-service:latest + codebase; single container
MAIN=$(docker compose ps -q main)
# wait for healthy (~3s)
docker exec -i "$MAIN" slack whoami                                      # CLI works
docker cp ../tests "$MAIN":/tests && docker cp ../solution "$MAIN":/solution
docker exec -i "$MAIN" bash /tests/run_verifier.sh                       # nop -> 0
docker exec -i "$MAIN" bash /solution/solve.sh
docker exec -i "$MAIN" bash /tests/run_verifier.sh                       # oracle -> 1
docker compose down -v
```
Also: `task.toml` validates against Harbor's `TaskConfig`; no `networks:`; `platform: linux/amd64`;
unique per-task image tags. On Apple Silicon, build a native (non-amd64) image locally — amd64
emulation hangs; CI builds amd64. Deeper QA: `skillz:harbor-task-audit`.
