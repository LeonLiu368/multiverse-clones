# Creating a new task

These are **observability + codebase** tasks on the **isolated Slack-gateway artifact**: a
failing pytest suite at `/workspace` whose fix depends on a fact buried in heavy Slack chat that
the agent reaches via the Slack Web API. The full checklist lives in the
**`slack-observability-task-builder`** skill — invoke it when building one. Quick version:

## The two bars (non-negotiable)
1. **Tool use is CRITICAL** — the fact is only in chat; a hidden grader (params only in chat)
   makes it unobtainable from the repo/visible tests.
2. **Tool use is NON-TRIVIAL** — superseded/contradictory values, off-channel traps, a red
   herring; `search.messages` surfaces the wrong hits too, so the agent must read & disambiguate.

## Anatomy (copy an existing task — e.g. `buried-spec`)
```
tasks/<name>/
  task.toml            # service="slack", tools=["slack-web-api","slack_sdk","curl"], workdir="/workspace"
  instruction.md       # symptom + "Slack at $SLACK_API_URL / $SLACK_BOT_TOKEN (curl or slack_sdk)"; NEVER the buried fact
  environment/
    Dockerfile.api, api-entrypoint.sh, seed.sh, slackgw/, seed.py   # backend — copy from selfcontained/isolated, unchanged
    Dockerfile.main, main-entrypoint.sh                              # agent  — copy; Dockerfile.main also COPYs codebase
    docker-compose.yaml                                              # copy; set unique image tags  <name>-api / <name>-main
    data/mattermost/{generate.py, scraped.json}   ← YOU WRITE generate.py; commit scraped.json (deterministic, heavy)
    codebase/          ← YOU WRITE: working module(s) [tests pass] + a stub/buggy target [fails] + a breadcrumb to Slack
  solution/solve.sh    ← YOU WRITE: oracle edits /workspace; for comms tasks also curl chat.postMessage to the gateway
  tests/
    test.sh            # orchestration — copy
    run_verifier.sh    ← YOU WRITE/ADAPT: grade in /tmp (candidate pkg + trusted tests); comms checks via the gateway
    trusted/           ← YOU WRITE: canonical visible tests + the HIDDEN test_grade_*.py
```
The backend/agent/compose files are identical across tasks (only image tags + the mounted
`data/` and `codebase/` differ) — copy them from `selfcontained/isolated/` and the buried-spec task.

## The files you write (per task)
- **`data/mattermost/generate.py`** → ~500 deterministic noisy messages; inject SUPERSEDED values
  early + the agreed values later + off-channel traps; commit `scraped.json`.
- **`codebase/`** → a working module (tests pass) + the stub/buggy target (tests fail) with a
  docstring/README/error breadcrumb pointing to the workspace chat.
- **`instruction.md`** → symptom + the Slack Web API creds; never the buried fact.
- **`solution/solve.sh`** → oracle: edit `/workspace`; for comms, `curl chat.postMessage` to
  `$SLACK_API_URL` (the agent can't reach Mattermost, only the gateway).
- **`tests/trusted/`** → invariant-only visible tests + the HIDDEN `test_grade_*.py` (reference
  impl / exact cases). **Must be `test_grade_*.py`** or pytest won't collect it (false-pass hole).
- **`tests/run_verifier.sh`** → copy candidate pkg + trusted tests to `/tmp/grade.$$`, run pytest
  there (never `/workspace/tests`); for comms, read back via `conversations.history`.

## Two rules that keep it reliable
- **Key reward on the fixed state.** Confirm a deliberately-wrong-but-invariant impl still → 0.
- **Seed via REST, mutate via REST** (the shared `seed.py` does this); raw-SQL entities misbehave.

## Validate before shipping (always)
```bash
cd tasks/<name>/environment && docker compose up -d --build
MAIN=$(docker compose ps -q main)
docker exec -i "$MAIN" sh -c 'curl -s -m5 http://api:8065/api/v4/system/ping -o /dev/null -w "MM:%{http_code}\n"'  # 000/refused
docker cp ../tests "$MAIN":/tests && docker cp ../solution "$MAIN":/solution
docker exec -i "$MAIN" bash /tests/run_verifier.sh          # nop -> 0
# wrong-but-invariant impl -> still 0
docker exec -i "$MAIN" bash /solution/solve.sh && docker exec -i "$MAIN" bash /tests/run_verifier.sh   # oracle -> 1
docker compose down -v
```
Also: `task.toml` validates against Harbor's `TaskConfig`; no `networks:`; `platform: linux/amd64`;
unique per-task image tags. Deeper QA: `skillz:harbor-task-audit`, `verifier-attack-lab`.
