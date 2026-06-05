# CLI, API & DB command reference

A practical cheat-sheet for interacting with an `abundant-slack-clone` workspace three ways:
the **`slack-cli`** tool, the raw **HTTP API**, and the **SQLite db** directly. The CLI and
API are the agent-facing surfaces; direct DB access is for authoring/debugging seeds.

> All three read/write the *same* state. The CLI is a thin HTTP client over the API, and the
> API serializes straight out of the SQLite db. There is **no auth** (open API by design).

## Setup

```bash
# dev install
uv venv && uv pip install -e ".[dev]"        # provides `slack-cli` + the package

# 1) seed a db   2) serve it   3) point the CLI at it
slack-cli seed generate --seed 42 --out slack.db
SLACK_DB=slack.db uvicorn slackclone.api.app:app --port 3000 &
export SLACK_API_URL=http://localhost:3000
slack-cli channels list --format markdown
```

In this repo use the venv binaries: `.venv/bin/slack-cli` and `.venv/bin/python` (the bare
`python` is the system one).

### Environment variables

| Var | Used by | Default | Meaning |
|---|---|---|---|
| `SLACK_API_URL` | `slack-cli` (client cmds) | `http://localhost:3000` | Where the CLI sends requests. |
| `SLACK_DB` | API server / `db.get_engine` | `slack.db` | SQLite file the server reads/writes. |
| `SLACK_USER` | API server | (first bot, else first user) | Default author for writes without `--user`. |
| `PORT` | service entrypoint | `3000` | Port the API listens on (Docker image). |
| `SLACK_SEED_DIR` | Docker entrypoint | `/data/slack` | Seed source: `slack.db` \| `workspace.json` \| `export/`. |

---

## `slack-cli` commands

Output is JSON by default; most read commands accept `--format markdown` for a readable
transcript. Every client command maps 1:1 to an API method (see the mapping table below).

### Reads

| Command | Does | Notes |
|---|---|---|
| `slack-cli channels list [--format markdown]` | List channels | → `conversations.list` |
| `slack-cli channels history <channel> [--limit N] [--oldest TS] [--latest TS] [--format markdown]` | Top-level messages, newest first | replies are excluded — fetch via `thread` |
| `slack-cli channels info <channel>` | Channel metadata | → `conversations.info` |
| `slack-cli thread <channel> <ts> [--format markdown]` | Full thread (parent + replies) | → `conversations.replies` |
| `slack-cli users list [--format markdown]` | List users | → `users.list` |
| `slack-cli users info <user>` | One user | takes a `U…` id (resolving `@name` is a known gap) |
| `slack-cli search <query> [--count N] [--format markdown]` | Substring message search | supports `in:#channel` and `from:@user` modifiers |

`<channel>` accepts a `C…` id **or** a name (`incidents` or `#incidents`). `<ts>` is a
message timestamp id like `1700000000.000001`.

```bash
slack-cli channels history incidents --format markdown
slack-cli thread incidents 1700000000.000001 --format markdown
slack-cli search "latency in:#incidents from:@carol" --format markdown
```

### Writes

| Command | Does | Notes |
|---|---|---|
| `slack-cli post <channel> <text> [--thread <ts>] [--user <U…>]` | Post a message / thread reply | → `chat.postMessage`; prints the new `ts` |
| `slack-cli react <channel> <ts> <emoji> [--user <U…>]` | Add an emoji reaction | → `reactions.add` (emoji short name, no colons) |
| `slack-cli pin <channel> <ts> [--user <U…>]` | Pin a message | → `pins.add` |

```bash
ts=$(slack-cli post incidents "ROOT CAUSE: connection pool exhaustion" | jq -r .ts)
slack-cli react incidents "$ts" eyes
slack-cli pin incidents "$ts"
```

### Seeding (build a db, no server needed)

| Command | Source |
|---|---|
| `slack-cli seed generate [--users N] [--channels N] [--days N] [--threads F] [--reactions F] [--seed N] --out slack.db [--emit workspace.json]` | Deterministic synthetic workspace |
| `slack-cli seed import-export <dir-or-.zip> --out slack.db [--emit workspace.json]` | A real Slack export |
| `slack-cli seed load <workspace.json> --out slack.db` | Hand-authored canonical seed JSON |

`--emit` also writes the portable **canonical seed JSON** (see
[seed/schema.py](../src/slackclone/seed/schema.py)) so a workspace can be inspected, diffed,
and committed into a task.

---

## HTTP API (curl)

Methods live at `/api/<method>`, accept GET or POST (query string, form, or JSON — like
Slack), and return the Slack envelope `{"ok": true, ...}` / `{"ok": false, "error": "..."}`.

| Method | Key params | Returns |
|---|---|---|
| `GET /health` | — | `{"ok":true,"status":"healthy"}` |
| `auth.test` | — | workspace/user identity |
| `conversations.list` | `types`, `exclude_archived`, `cursor`, `limit` | `channels[]`, `response_metadata.next_cursor` |
| `conversations.history` | `channel`, `oldest`, `latest`, `inclusive`, `cursor`, `limit` | `messages[]` (top-level, newest first), `has_more` |
| `conversations.replies` | `channel`, `ts` | `messages[]` (parent + replies, chronological) |
| `conversations.info` | `channel` | `channel` |
| `conversations.members` | `channel` | `members[]` |
| `chat.postMessage` | `channel`, `text`, `thread_ts`, `user` | `channel`, `ts`, `message` |
| `chat.update` | `channel`, `ts`, `text`, `user` | updated `message` |
| `chat.delete` | `channel`, `ts` | `channel`, `ts` |
| `users.list` | `cursor`, `limit` | `members[]` |
| `users.info` | `user` | `user` |
| `search.messages` | `query`, `count`, `page` | `messages.matches[]` |
| `reactions.add` | `channel`, `timestamp`, `name`, `user` | `{"ok":true}` |
| `pins.add` | `channel`, `timestamp`, `user` | `{"ok":true}` |

```bash
API=http://localhost:3000
curl -s "$API/api/conversations.history" --data-urlencode 'channel=incidents' | jq .
curl -s "$API/api/search.messages" --data-urlencode 'query=root cause in:#incidents' | jq '.messages.matches'
curl -s "$API/api/chat.postMessage" --data-urlencode 'channel=incidents' --data-urlencode 'text=hello'
```

Full coverage notes: [docs/slack-api-coverage.md](slack-api-coverage.md).

---

## Inspecting the SQLite db directly

Useful when authoring or debugging a seed. The db is a plain SQLite file (default
`slack.db`, or `$SLACK_DB`).

### Schema (see [models.py](../src/slackclone/models.py))

| Table | Key columns |
|---|---|
| `workspace` | `id`, `name`, `domain` |
| `users` | `id` (`U…`), `name`, `real_name`, `is_bot`, `deleted`, `tz`, `profile` (JSON) |
| `channels` | `id` (`C…`), `name`, `is_private`/`is_im`/`is_mpim`/`is_archived`, `created`, `creator`, `topic`, `purpose` |
| `memberships` | `channel_id`, `user_id` (composite PK) |
| `messages` | `pk`, `channel_id`, `ts`, `user_id`, `text`, `thread_ts`, `subtype`, `edited_ts`, `deleted`, `blocks` (JSON); unique `(channel_id, ts)` |
| `reactions` | `channel_id`, `ts`, `name`, `user_id`; unique `(channel_id, ts, name, user_id)` |
| `pins` | `channel_id`, `ts`, `user_id`, `created`; unique `(channel_id, ts)` |

A **thread** is `messages` rows sharing a `thread_ts` equal to the parent's `ts`. A message is
**top-level** when `thread_ts IS NULL OR thread_ts == ts`. Reactions/pins are separate rows so
counts and user lists aggregate naturally.

### Example queries

```bash
sqlite3 slack.db '.tables'
sqlite3 slack.db 'SELECT id, name, is_archived FROM channels ORDER BY name;'

# transcript of #incidents, oldest first
sqlite3 slack.db "
  SELECT m.ts, u.name, m.text
  FROM messages m JOIN channels c ON m.channel_id = c.id
  LEFT JOIN users u ON m.user_id = u.id
  WHERE c.name = 'incidents' AND m.deleted = 0
  ORDER BY CAST(m.ts AS REAL);"

# the thread hanging off a parent ts
sqlite3 slack.db "SELECT ts, user_id, text FROM messages
  WHERE thread_ts = '1700000000.000001' ORDER BY CAST(ts AS REAL);"

# pinned messages and their text
sqlite3 slack.db "SELECT p.channel_id, p.ts, m.text
  FROM pins p JOIN messages m ON m.channel_id = p.channel_id AND m.ts = p.ts;"

# reaction tallies
sqlite3 slack.db "SELECT channel_id, ts, name, COUNT(*) AS n
  FROM reactions GROUP BY channel_id, ts, name;"
```

> Prefer the API/CLI for writes — direct `INSERT`s bypass `ts` allocation and serialization
> invariants. Treat the db as read-mostly when debugging; (re)build it with `slack-cli seed …`.

---

## CLI ↔ API mapping (quick reference)

```
channels list      → conversations.list
channels history   → conversations.history
channels info      → conversations.info
thread             → conversations.replies
users list         → users.list
users info         → users.info
search             → search.messages
post               → chat.postMessage
react              → reactions.add
pin                → pins.add
seed generate      → (local) seed.generator  + seed.load
seed import-export → (local) seed.export_importer + seed.load
seed load          → (local) seed.load
```

(`chat.update` / `chat.delete` and `conversations.members` exist on the API but have no CLI
wrapper yet.)
