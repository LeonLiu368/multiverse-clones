# Data pipeline: from Slack export to live agent workspace

This document explains the full end-to-end process — how chat data gets from a source (either a
real Slack export or a generated synthetic dataset) into a live, query-able Slack-compatible
workspace that an agent can read through the Slack Web API. It covers authoring, building, running,
and testing.

---

## Big picture

```
Source data                Images                       Run                   Test
──────────────             ──────────                   ────────────          ────────────────────
Real Slack export  ──┐     api: PULL slack-service      api container:        Agent reads workspace
  OR               ──┼──►  (Mattermost+gateway+seeder)  1. Postgres + MM up   via Slack gateway
Synthetic generate.py ──┘                               2. seed.py loads      ─────────────────────
   → scraped.json          main: BUILD thin Dockerfile     scraped.json       verifier: pytest +
   (mounted into api)      (python:slim + codebase)     3. gateway on :80     comms check → reward
                                                         main container:
                                                         agent works in /workspace
```

---

## Phase 1 — Source data

### Option A: Synthetic (current)

Each task has a `data/mattermost/generate.py`. Running it produces a `scraped.json` file — a
deterministic (~500-message) conversation seeded with `random.Random(1337)`. The script hard-codes
the story arc: realistic engineering chat noise across several channels, with the critical fact
buried around message 350–420 in the key channel, surrounded by superseded/wrong proposals and
red herrings. The author commits `scraped.json` so runs are reproducible without re-running the
generator.

### Option B: Real Slack export (planned)

A real Slack workspace export produces a directory tree:
```
workspace_export/
  channels.json         # channel metadata (id, name, purpose, …)
  users.json            # user metadata (id, name, real_name, …)
  <channel-name>/
    YYYY-MM-DD.json     # one file per day, array of message objects
    YYYY-MM-DD.json
    …
  <channel-name>/
    …
```

Each message in the daily JSON file looks like:
```json
{
  "user":   "U01ABC123",
  "type":   "message",
  "subtype": "channel_join",        // optional: system events
  "ts":     "1646780255.193039",    // Unix float string: seconds.microseconds
  "text":   "<@U01ABC123> where can I find the ratings chart?",
  "team":   "TANON0001",
  "client_msg_id": "73135b9b-…",
  "user_profile": {
    "first_name": "Alice",
    "real_name":  "Alice Smith",
    "display_name": "alice",
    "name": "alice.smith",
    …
  },
  "blocks":    […],                 // Slack Block Kit rich text
  "reactions": [{"name": "hat-tip", "users": ["U…"], "count": 1}]
}
```

Key properties: one file per day per channel; user display name is in `user_profile`, not the
top-level object; timestamps are Unix float strings (not ISO 8601); `text` contains Slack markup
(`<@USER_ID>`, `<#CHANNEL_ID|name>`, `<URL|label>`).

---

## Phase 2 — scraped.json (our internal seed format)

`scraped.json` is the single file the seeder reads. **Our current schema**:
```json
{
  "messages": [
    {
      "channel":   "platform-infra",
      "author":    "alice",
      "content":   "Morning — load test report is in, let's talk rate limiter.",
      "timestamp": "2025-05-19T09:00:00+00:00"
    },
    …
  ]
}
```

This is our normalized intermediate format. It has just what `seed.py` needs:
- `channel`: plain lowercase channel name (determines which MM channel to create/use)
- `author`:  display name string (used to create/look up the MM user)
- `content`: plain text of the message
- `timestamp`: ISO 8601 datetime (used to set `createat` in the Postgres `posts` table)

`generate.py` writes to this format. A real-Slack-export importer (not yet built) would transform
from the export format above into this schema.

---

## Phase 3 — Images: one pulled, one thin build

The harness runs `docker compose` over the task's compose. Harbor force-builds **only** the agent
service (`main`); a service with `image:` only (the backend) is **pulled**, not built.

**`api` — PULLED** (`ghcr.io/abundant-ai/slack-service`, built once by CI from
`selfcontained/base/Dockerfile.service`):
- `FROM mattermost/mattermost-team-edition:8.1.1`
- Postgres 14, Python 3, FastAPI/Uvicorn, httpx, psycopg2
- Bakes in `slackgw/`, `seed.py`, `api-entrypoint.sh`, `seed.sh`, MM creds, `SLACK_BOT_TOKEN`
- The task does **not** rebuild this — it references the image and mounts `data/mattermost/`.

**`main` — BUILT** per task from the thin `environment/Dockerfile`:
- `FROM python:3.12-slim`
- curl, jq, git, the `slackcli` package (`slack` CLI + `slack-mcp`), pytest
- COPYs `main-entrypoint.sh` and **`codebase/`** → `/workspace`
- Sets ENV: `SLACK_API_URL=http://api`, `SLACK_BOT_TOKEN=xoxb-acme-eval-0001`
- Deliberately thin/clean so the agent container has no Mattermost tells.

The agent `Dockerfile`, `main-entrypoint.sh`, and `docker-compose.yaml` are shared files vendored
into each task from `selfcontained/base/` by `selfcontained/base/vendor.sh`. The backend image is
released separately (CI) — see [IMAGE-RELEASE.md](IMAGE-RELEASE.md).

---

## Phase 4 — Runtime: seeding the workspace

When `docker compose up -d` runs, the `api` container boots first:

1. **Postgres starts** on port 5433 (local to the container).
2. **Mattermost launches**, bound to `127.0.0.1:8065` — never visible from the agent's container.
3. **`seed.py` runs**, reading `/data/mattermost/scraped.json` (which the compose mounts from the
   task's `data/mattermost/` folder as read-only). It:
   - Creates the admin user and `test-demo` team via REST API (so Mattermost's caches know about them).
   - For each distinct `channel` value: creates the channel via REST.
   - For each distinct `author` value: creates the user via REST and adds to team.
   - For each message: inserts directly into the Postgres `posts` table (to preserve original timestamps
     — the REST `createAt` is server-controlled; SQL is the only way to back-date posts).
4. **Optional custom seed hook**: if `data/mattermost/seed.sh` exists in the task, the entrypoint
   runs it (allows per-task extra setup without modifying the shared image).
5. **The Slack gateway starts** on port 80 (`uvicorn slackgw.app:app`).
6. **Healthcheck passes**: the compose healthcheck polls `http://localhost:80/api/auth.test` — once
   that returns `{"ok":true}`, the `api` container is marked healthy.

Only after `api` is healthy does the `main` container start (`depends_on: api healthy`). This
guarantees the agent always finds a fully-seeded workspace.

---

## Phase 5 — The agent acts

The agent in `main` has:
- `/workspace` — the broken codebase (tests fail; the fix depends on a fact in the chat).
- `$SLACK_API_URL=http://api` and `$SLACK_BOT_TOKEN=xoxb-acme-eval-0001` baked into the image env
  (visible to every shell and `docker exec` — not just login shells).
- the `slack` CLI + the `slack` MCP server (slackcli), `python3`, `pytest`.

It reads `instruction.md`, runs the tests to see the failures, then uses the `slack` CLI / MCP to
explore the workspace: listing channels, reading history, searching. It must disambiguate
superseded proposals from the final agreed values, fix the code, and (for the comms task) post a
message back through the gateway.

The agent can only reach the gateway at `http://api`. Mattermost on `api:8065` is refused.
The gateway scrubs server/version headers and returns Slack-shaped `unknown_method` for any
non-Slack path — the agent cannot discover it's backed by Mattermost.

---

## Phase 6 — Verification and scoring

After the agent stops, the harness runs `tests/test.sh`, which calls `tests/run_verifier.sh`
inside the `main` container. The verifier:

1. Creates a fresh `/tmp/grade.$$` directory (verifier-owned; agent cannot pre-tamper it).
2. Copies the **candidate code** from `/workspace/<module>` into `/tmp/grade.$$`.
3. Copies the **trusted tests** from the bind-mounted `/tests/trusted/` into `/tmp/grade.$$`.
   These include the **hidden grader** (`test_grade_*.py`) which pins the exact correct values;
   the agent never sees this file during the run.
4. Runs `python -m pytest -q -p no:cacheprovider` inside `/tmp/grade.$$`.
5. For **communication tasks**: makes a `conversations.history` call through the Slack gateway to
   check that a required message was posted to the right channel with the right content.
6. Writes `1` or `0` to `/logs/verifier/reward.txt`.

**Reward bracketing** (validated for every task before shipping):
- `nop` (agent does nothing) → `reward=0`
- `oracle` (reference solution) → `reward=1`
- Wrong-but-invariant fix (passes visible tests, wrong specific values) → `reward=0`

---

## Shared source: `selfcontained/base/`

Single source of truth. It holds **(a)** the backend image source — `Dockerfile.service`, `slackgw/`,
`seed.py`, `api-entrypoint.sh`, `seed.sh` (built + pushed once as `slack-service` by CI / `build.sh`),
and **(b)** the per-task agent files — the thin `Dockerfile`, `main-entrypoint.sh`, `.dockerignore`,
and the `docker-compose.yaml` template. `selfcontained/base/vendor.sh` copies the agent files into
every task's `environment/` (templating the per-task image tag). Never edit the per-task copies;
edit `base/` and re-vendor (or, for the backend, rebuild + push the image).

---

## Schema delta: our format vs real Slack export

| Field / aspect | **Our `scraped.json`** | **Real Slack export** |
|---|---|---|
| Top-level | `{"messages": [...]}` | `[...]` (flat array per file) |
| File organization | Single file, all channels | One file per day per channel |
| Channel name | `channel` field on each message | Implicit (directory name) |
| Author identifier | `author` (display name string) | `user` (Slack user ID) + `user_profile.display_name` |
| Message text | `content` | `text` |
| Timestamp format | ISO 8601 string | Unix float string `"seconds.microseconds"` |
| System messages | Not present | `subtype: channel_join` etc. |
| Rich text | Not present | `blocks` (Block Kit) |
| Reactions | Not present | `reactions` array |
| Slack markup in text | Not present | `<@U…>`, `<#C…\|name>`, `<URL\|label>` |

See [REAL-SLACK-IMPORT.md](REAL-SLACK-IMPORT.md) for the planned importer that transforms a real
Slack export directory into our `scraped.json` format.
