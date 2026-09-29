# Data pipeline: from Slack export to live agent workspace

End-to-end: how chat data gets from a source (a real Slack export, or a generated synthetic one
written in export shape) into a live, queryable Slack-compatible workspace the agent reads through
the gateway. Covers authoring, building, running, and testing.

## Big picture

```
Source data                  Image (single container)        Run                       Test
──────────────               ─────────────────────────       ─────────────────────     ──────────────────
Real Slack export  ──┐       slack-service (python:slim):     main container boots:     agent reads via
  OR               ──┼────►   gateway + SQLite store +        1. import_export.py        slack CLI + korotovsky
generate.py ──► slack-export ─┘ importer + slack CLI +           export -> /tmp/slack.db   MCP -> gateway
   (real export shape)        korotovsky slack-mcp + codebase  2. uvicorn gateway :80    verifier: pytest +
                                                               3. healthy -> agent runs   comms check -> reward
```

## Phase 1 — Source data
- **Synthetic (default):** each task's `data/generate.py` builds a deterministic (~500-message)
  story arc seeded with `random.Random(1337)` — realistic noise + the critical fact buried in the
  key channel, surrounded by superseded/wrong proposals and red herrings — and calls
  `slack_export_writer.write_export()` to emit a **real Slack export** under `data/slack-export/`.
  Committed for reproducibility.
- **Real export:** a genuine workspace export (`channels.json`, `users.json`, `<channel>/<date>.json`).
  `import_export.py` ingests it directly; `--channels`/`--start`/`--end` carve a slice from a big
  corpus. See [REAL-SLACK-IMPORT.md](REAL-SLACK-IMPORT.md).

## Phase 2 — The real-export format (the seed)
```
data/slack-export/
  channels.json          # [{id, name, created, creator, is_archived, is_general, members, topic, purpose}]
  users.json             # [{id, team_id, name, real_name, is_bot, profile:{display_name, email, …}}]
  <channel-name>/<YYYY-MM-DD>.json   # array of {user, ts, text, user_profile, thread_ts?, reactions?, …}
```
This is exactly what a real Slack export produces. `import_export.py` is robust to the anonymized
variant too (no top-level files → channels from dir names, users from message `user_profile`), and
normalizes any non-Slack-shaped id to deterministic `C…`/`U…`.

## Phase 3 — Image: one prebuilt, thin task layer
Single container (no `api` sidecar). Harbor force-builds `main` from the task `Dockerfile`:
- **base `slack-service`** (pulled, built once by CI): `python:3.12-slim` + FastAPI/uvicorn + the
  gateway (`slackgw/` over `store.py` SQLite), `import_export.py`, `slack_export_writer.py`, our
  `slack` CLI, and the korotovsky `slack-mcp` Go binary + wrapper. ~112 MB.
- **task layer**: ENV (`SLACK_API_URL`, `SLACK_BOT_TOKEN=xoxp-…`) + `main-entrypoint.sh` + the codebase.

Shared files live once in `selfcontained/base/`; `vendor.sh` pushes them into each task. The base
image is released by CI — see [IMAGE-RELEASE.md](IMAGE-RELEASE.md).

## Phase 4 — Runtime: seeding the workspace
`main-entrypoint.sh` → `slack-boot.sh`:
1. `import_export.py` loads the mounted seed into SQLite (`/data/slack-export` first, then a legacy
   `scraped.json`). Channels, users, and messages (threads, reactions, real ids) land in `/tmp/slack.db`.
2. `uvicorn slackgw.app:app` starts on `:80` in the background.
3. Waits for `/api/auth.test`, then keepalive. The compose healthcheck gates the agent on this —
   "healthy" means "seeded and serving." A few seconds total.

## Phase 5 — The agent acts
`/workspace` is the broken codebase. `$SLACK_API_URL=http://localhost`, `$SLACK_BOT_TOKEN=xoxp-…` are
baked env. The agent uses the **`slack` CLI** (`channels`, `history`, `search`, `post`, `whoami`) and
the **korotovsky MCP** (`conversations_history`, `conversations_replies`, `conversations_search_messages`,
`channels_list`, `conversations_add_message`) — both hitting the gateway. It disambiguates superseded
proposals from the agreed values, fixes the code, and (for the comms task) posts a notification.

## Phase 6 — Verification and scoring
`tests/test.sh` → `tests/run_verifier.sh` (in `main`):
1. Fresh `/tmp/grade.$$` (verifier-owned).
2. Copies candidate `/workspace/<module>` + trusted tests (incl. the hidden `test_grade_*.py`).
3. `python3 -m pytest -q -p no:cacheprovider` there.
4. Comms tasks: read the posted message back via `conversations.history` through the gateway.
5. Writes `1`/`0` to `/logs/verifier/reward.txt`.

**Reward bracket** (validated per task): `nop` → 0; `oracle` → 1; wrong-but-invariant → 0; comms
task: code-only fix → 0.

## Shared source: `selfcontained/base/`
Single source of truth: the backend image source (`Dockerfile.service`, `slackgw/`, `import_export.py`,
`slack_export_writer.py`, `mcp/`, entrypoints) **and** the per-task agent files (`Dockerfile`,
`main-entrypoint.sh`, `docker-compose.yaml`). Edit here, then `vendor.sh` (agent files) or rebuild +
push (the image). `data/` and `codebase/` are task-owned.
