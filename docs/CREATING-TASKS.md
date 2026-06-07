# Creating a new task

These are **observability + codebase** tasks on the **single-container Slack artifact**: a
failing pytest suite at `/workspace` whose fix depends on a fact buried in heavy Slack chat that
the agent reaches via the Slack Web API. The full checklist lives in the
**`slack-observability-task-builder`** skill — invoke it when building one. Quick version:

## The two bars (non-negotiable)
1. **Tool use is CRITICAL** — the fact is only in chat; a hidden grader (params only in chat)
   makes it unobtainable from the repo/visible tests.
2. **Tool use is NON-TRIVIAL** — superseded/contradictory values, off-channel traps, a red
   herring; `search.messages` surfaces the wrong hits too, so the agent must read & disambiguate.

## The backend is one prebuilt image (task builds FROM it)
The whole backend — Mattermost + the Slack gateway + the seeder — is the single image
`ghcr.io/abundant-ai/slack-service`, built once from `selfcontained/base/Dockerfile.service` and
pushed by CI. The task's `Dockerfile` does `FROM ghcr.io/abundant-ai/slack-service:latest` and
adds only the agent tools + codebase. Harbor builds this thin layer per task; no separate `api`
sidecar. See [IMAGE-RELEASE.md](IMAGE-RELEASE.md).

## Anatomy (copy an existing task — e.g. `buried-spec`)
```
tasks/<name>/
  task.toml            # service="slack", tools=["slack-cli","slack-mcp"] + [[environment.mcp_servers]], workdir="/workspace"
  instruction.md       # symptom + "you have the slack CLI + MCP"; NEVER the buried fact
  environment/
    Dockerfile           # FROM slack-service:latest + slackcli (slack CLI+MCP) + codebase (Harbor builds `main`)
    main-entrypoint.sh   # boots PG+MM+seed+gateway, then keepalive
    docker-compose.yaml  # single `main` service: build + data mount + healthcheck
    data/mattermost/{generate.py, scraped.json}   ← YOU WRITE generate.py; commit scraped.json (deterministic, heavy)
    codebase/          ← YOU WRITE: working module(s) [tests pass] + a stub/buggy target [fails] + a breadcrumb to Slack
  solution/solve.sh    ← YOU WRITE: oracle edits /workspace; for comms tasks also `slack post <channel> "..."`
  tests/
    test.sh            # orchestration — copy
    run_verifier.sh    ← YOU WRITE/ADAPT: grade in /tmp (candidate pkg + trusted tests); comms checks via SLACK_API_URL
    trusted/           ← YOU WRITE: canonical visible tests + the HIDDEN test_grade_*.py
```
The three build files (`Dockerfile`, `main-entrypoint.sh`, `docker-compose.yaml`) are identical
across tasks. **Don't hand-copy them**: they live once in `selfcontained/base/`; run
`bash selfcontained/base/vendor.sh` to push them into every task (also copies `slackcli/`).
Edit shared logic in `selfcontained/base/`, never in a task.

## The files you write (per task)
- **`data/mattermost/generate.py`** → ~500 deterministic noisy messages; inject SUPERSEDED values
  early + the agreed values later + off-channel traps; commit `scraped.json`.
- **`codebase/`** → a working module (tests pass) + the stub/buggy target (tests fail) with a
  docstring/README/error breadcrumb pointing to the workspace chat.
- **`instruction.md`** → symptom + the Slack Web API creds; never the buried fact.
- **`solution/solve.sh`** → oracle: edit `/workspace`; for comms, `slack post <channel> "..."`
  (uses `SLACK_API_URL=http://localhost` baked in the image).
- **`tests/trusted/`** → invariant-only visible tests + the HIDDEN `test_grade_*.py` (reference
  impl / exact cases). **Must be `test_grade_*.py`** or pytest won't collect it (false-pass hole).
- **`tests/run_verifier.sh`** → copy candidate pkg + trusted tests to `/tmp/grade.$$`, run
  `python3 -m pytest` there (never `/workspace/tests`); for comms, read back via
  `conversations.history` on `${SLACK_API_URL:-http://localhost}`.

## Two rules that keep it reliable
- **Key reward on the fixed state.** Confirm a deliberately-wrong-but-invariant impl still → 0.
- **Seed via REST, mutate via REST** (the shared `seed.py` does this); raw-SQL entities misbehave.

## Validate before shipping (always)
```bash
cd tasks/<name>/environment
docker compose up -d --build   # builds FROM slack-service:latest + task layer; single container
MAIN=$(docker compose ps -q main)
# wait for healthy (~30s — Mattermost boot + seed + gateway)
docker cp ../tests "$MAIN":/tests && docker cp ../solution "$MAIN":/solution
docker exec -i "$MAIN" slack whoami                                      # CLI works
docker exec -i "$MAIN" bash /tests/run_verifier.sh                       # nop -> 0
# wrong-but-invariant impl -> still 0
docker exec -i "$MAIN" bash /solution/solve.sh
docker exec -i "$MAIN" bash /tests/run_verifier.sh                       # oracle -> 1
docker compose down -v
```
Also: `task.toml` validates against Harbor's `TaskConfig`; no `networks:`; `platform: linux/amd64`;
unique per-task image tags; verifier uses `python3`, not `python`. Deeper QA: `skillz:harbor-task-audit`.
