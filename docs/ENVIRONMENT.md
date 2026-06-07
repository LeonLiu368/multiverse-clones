# How the environment works (start to end)

Plain-English walkthrough of the single-container artifact: where the data comes from, how the
container starts, how the agent operates, and how the verifier scores.

## One container does everything

There is a single service, `main`. Harbor force-builds it from the task's `environment/Dockerfile`,
which is:

```dockerfile
FROM ghcr.io/abundant-ai/slack-service:latest   # Mattermost + gateway + seeder (prebuilt, pulled)
# adds: git, slackcli (slack CLI + slack-mcp), pytest, PYTHONPATH, codebase at /workspace
```

The `slack-service` base image (built once by CI from `selfcontained/base/Dockerfile.service` and
pushed to GHCR) contains real Mattermost + the Slack Web API gateway (`slackgw`) + the seeder.
The per-task Dockerfile layers on the agent tools and the codebase — no separate `api` sidecar.

No `networks:` block (Harbor injects `network_mode`, which is mutually exclusive). `linux/amd64`.

## Step by step

1. **Harbor builds `main` and starts it.** `FROM slack-service:latest` pulls the cached base;
   Docker adds the thin task layer (slackcli + codebase). The container starts.

2. **The entrypoint boots the internal services.** `main-entrypoint.sh` runs synchronously:
   - Starts Postgres 14 on port 5433 (local to the container).
   - Starts Mattermost on `127.0.0.1:8065` (local to the container).
   - Runs `seed.py` from `/data/mattermost/scraped.json` (mounted from the task's `data/mattermost/`):
     creates admin, team `test-demo`, channels, users, and posts. **Posts via SQL** to preserve
     timestamps; channels/users via REST so Mattermost caches know about them.
   - Runs optional per-task hook (`data/mattermost/seed.sh` if present).
   - Starts the Slack gateway on `:80` in the background.
   - Waits for `http://localhost:80/api/auth.test` to return OK.
   - Then: `exec tail -f /dev/null` — the container is ready.

3. **Healthcheck signals readiness.** The compose healthcheck polls
   `curl -sf http://localhost:80/api/auth.test`. Harbor waits for `main` to be healthy before
   running the agent — so the agent always finds a fully seeded workspace.

4. **The agent acts.** It reads `instruction.md` (symptom + "you have the Slack Web API"), uses the
   `slack` CLI / MCP to explore the workspace, disambiguates superseded proposals from agreed
   values, edits the codebase at `/workspace`, and — for the incident task — posts a notification
   via `slack post`.

   Tools available: `slack channels`, `slack history <ch> [--limit N]`, `slack search <q>`,
   `slack users`, `slack post <ch> <text>`, `slack whoami`; plus MCP equivalents
   (`slack_list_channels`, `slack_history`, …). Both hit `http://localhost:80` (the gateway).
   `SLACK_API_URL=http://localhost`, `SLACK_BOT_TOKEN=xoxb-acme-eval-0001`.

5. **The verifier scores.** `tests/run_verifier.sh` runs inside `main`:
   - Creates a fresh `/tmp/grade.$$` (verifier-owned; agent can't pre-tamper).
   - Copies candidate code from `/workspace/<module>` + trusted tests (canonical invariant tests
     + the hidden `test_grade_*.py`) into `/tmp/grade.$$`.
   - Runs `python3 -m pytest -q -p no:cacheprovider` there — never in `/workspace/tests`.
   - For comms tasks: reads the posted message back via `conversations.history` on `SLACK_API_URL`.
   - Writes `1` or `0` to `/logs/verifier/reward.txt`.

6. **Bracketed.** `nop` → 0; `oracle` → 1; wrong-but-invariant fix → 0; comms task: code-only fix → 0.

## The data mount

The task's `data/mattermost/` directory is mounted read-only into the container at `/data/mattermost`.
It contains `scraped.json` (the heavy deterministic seed, ~500 messages committed to the repo). The
seeder reads from there; the agent never accesses the mount directly.

## Why there's only one container

Earlier design had `api` + `main` (two containers) to hide Mattermost from the agent. We simplified
to single container — the agent can technically reach `localhost:8065` directly, but this is
acceptable since the benchmark is about *Slack API tool use*, not impenetrability. The architecture
is otherwise identical: the gateway is the intended interface, the tools call only `http://localhost`,
and the verifier reads state back through the gateway.

## Why it's a good benchmark
- The fix-critical fact lives only in Slack → the agent **must** use the tool.
- Heavy, noisy, deterministic seed → non-trivial retrieval, reproducible runs.
- Hidden grader + invariant-only visible tests + isolated grading dir → no shortcut, no tampering.
- `nop=0 / oracle=1` (+ wrong-impl=0) bracket on every task.
- Action beyond coding (the incident postmortem) → measures tool use that isn't just editing files.
- Single container, no `networks:`, `linux/amd64` → runs the same locally and on Modal.
