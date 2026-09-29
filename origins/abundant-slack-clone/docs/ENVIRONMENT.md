# How the environment works (start to end)

Plain-English walkthrough of the single-container artifact: where the data comes from, how the
container starts, how the agent operates, and how the verifier scores.

## One container does everything

There is a single service, `main`. Harbor force-builds it from the task's `environment/Dockerfile`:

```dockerfile
FROM ghcr.io/abundant-ai/slack-service:latest   # SQLite gateway + importer + slack CLI + korotovsky slack-mcp
# adds: ENV (token/url), main-entrypoint.sh, codebase at /workspace
```

The `slack-service` base image (built once by CI from `selfcontained/base/Dockerfile.service`,
pushed to GHCR) is a lightweight `python:slim` image — **no Mattermost, no Postgres** (~112 MB). It
contains the FastAPI Slack gateway over a **SQLite** store, the **importer**, our **`slack` CLI**,
and the off-the-shelf **[korotovsky `slack-mcp`](https://github.com/korotovsky/slack-mcp-server)**
binary (patched only to point its base URL at our gateway).

No `networks:` block (Harbor injects `network_mode`, mutually exclusive). `linux/amd64`.

## Step by step

1. **Harbor builds `main` and starts it.** `FROM slack-service:latest` + the codebase layer.

2. **The entrypoint imports the seed and starts the gateway** (`main-entrypoint.sh` →
   `slack-boot.sh`):
   - Runs `import_export.py` on the mounted seed. Priority: a **real Slack export** at
     `/data/slack-export` (the normal case) → a legacy `scraped.json`. It loads channels, users, and
     messages (with threads, reactions, real `C…`/`U…` ids, display names) into SQLite at `/tmp/slack.db`.
   - Starts the gateway (`uvicorn slackgw.app:app`) on `:80` in the background.
   - Waits for `http://localhost:80/api/auth.test`, then keeps the container alive.

3. **Healthcheck signals readiness.** The compose healthcheck polls `/api/auth.test`; Harbor waits
   for `main` healthy before running the agent — so the agent always finds a fully seeded workspace.
   Boot is a few seconds (no Mattermost/Postgres).

4. **The agent acts.** It reads `instruction.md`, then explores the workspace via:
   - **`slack` CLI:** `slack channels`, `slack history <ch> [--limit N]`, `slack search <q>`,
     `slack post <ch> <text>`, `slack whoami` (`--json` on any).
   - **korotovsky `slack-mcp` (stdio):** `channels_list`, `conversations_history`,
     `conversations_replies`, `conversations_search_messages`, `conversations_add_message`.
   Both hit the gateway at `http://localhost`. It disambiguates superseded proposals from agreed
   values, fixes `/workspace`, and — for the incident task — posts a notification.

5. **The verifier scores.** `tests/run_verifier.sh` runs inside `main`: copies the candidate code +
   trusted tests (canonical invariant tests + the hidden `test_grade_*.py`) into a fresh
   `/tmp/grade.$$`, runs `python3 -m pytest` there (never `/workspace/tests`). For comms tasks it
   reads the posted message back through the gateway (`conversations.history`). Writes `1`/`0` to
   `/logs/verifier/reward.txt`.

6. **Bracketed.** `nop` → 0; `oracle` → 1; wrong-but-invariant → 0; comms task: code-only fix → 0.

## The seed: a real Slack export

The task's `data/slack-export/` directory is a **real Slack export** (`channels.json`, `users.json`,
`<channel>/<YYYY-MM-DD>.json`), mounted read-only at `/data/slack-export` and ingested into SQLite at
boot. It's authored by the task's `generate.py` via the shared `slack_export_writer.py` helper (story
arc + distractors + the planted fact, written out in real-export shape). The importer also accepts
genuine workspace exports — both the complete shape and the anonymized variant (no top-level files).

## How the korotovsky MCP reaches our gateway

The MCP is the real, unmodified-in-spirit korotovsky server, with a tiny patch so
`SLACK_MCP_API_URL` retargets its slack-go client at `http://localhost/api/` instead of
`api.slack.com`. It runs in **xoxp (user-token) mode** (so its search tool is enabled) and is
restricted to the tools our gateway backs. The `slack-mcp` wrapper recovers the token from PID 1
(stdio strips env) and sets the korotovsky env. The gateway's `auth.test` returns a Slack-shaped
workspace URL so korotovsky's workspace parsing succeeds.

## Why it's a good benchmark
- The fix-critical fact lives only in the chat → the agent **must** use the tool.
- Heavy, noisy, deterministic seed (real-export-shaped) → non-trivial retrieval, reproducible runs.
- Hidden grader + invariant-only visible tests + isolated grading dir → no shortcut, no tampering.
- `nop=0 / oracle=1` (+ wrong-impl=0) bracket on every task.
- Action beyond coding (the incident notification) → measures tool use that isn't just editing files.
- Single container, no `networks:`, `linux/amd64` → runs the same locally and on Modal.
