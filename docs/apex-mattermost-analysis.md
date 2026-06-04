# How APEX-SWE integrates Mattermost (and why we built a Slack clone)

Analysis of `Mercor-Intelligence/apex-swe` `observability/tasks/shared/`, the basis for this
project's design.

## Service stack
A `mattermost` container built from `dockerfiles/Dockerfile.mattermost-lightweight` =
`mattermost/mattermost-team-edition:8.1.1` + an **embedded PostgreSQL** (tmpfs, port 5433). The
entrypoint `docker-entrypoint-mattermost-lightweight.sh` boots PG → writes `config.json`
(SiteURL `:8065`, dev features + user-access-tokens on, files/links off) → launches
`./bin/mattermost` → polls `/api/v4/system/ping` → seeds. The agent reaches it from a separate
**client** container.

## Data injection & structure
Seed file mounted at `/data/mattermost/scraped.json`, authoring format:
```json
{ "messages": [ {"channel": "...", "author": "alice", "content": "...", "timestamp": 1748000000000} ] }
```
(`author` may be a string or `{global_name|username}`; `timestamp` Unix-ms or ISO.) The entrypoint
creates an admin, team `test-demo`, a `general` channel, then bulk-inserts messages (direct
`psycopg2` and/or `POST /api/v4/posts`), auto-creating one user per author, filtering by git-commit
time to avoid future-data leakage, sampling large sets. **Not modeled:** threads, reactions, DMs,
files, edits, pins, real user profiles — it is effectively a flat message log.

## Agent interface (MCP)
A TypeScript MCP server (`mcp-servers/mattermost/`) exposes **3 read-only** tools backed by
Mattermost REST:

| MCP tool | inputs | backing REST |
|---|---|---|
| `mattermost_channels` | `limit?` | `GET /channels` |
| `mattermost_fetch` | `channels?`, `limit?` | `GET /channels/{id}/posts` |
| `mattermost_search` | `query`, `channels?`, `before/after/on?`, `limit?` | `POST /teams/{teamId}/posts/search` |

Auth via env `MATTERMOST_ENDPOINT/_TOKEN/_TEAM`; launched over stdio by the `bin/mcp-mattermost`
wrapper, which sources `/config/mcp-config.txt` and auto-provisions a token if missing. The README
notes search is unreliable ("prefer fetch").

## Task creation
A task's `environment/docker-compose.yaml` declares the `mattermost` service (mounting
`data/mattermost/`); the client builds the MCP server and is wired via `/config/mcp-config.txt`;
`setup-observability-mcp.sh` provisions and loads data; `instruction.md` tells the agent to "use
the configured MCP tools."

## Why a Slack-faithful clone instead of reusing Mattermost
- **Richer, real model.** APEX's Mattermost integration models a flat log; we model **threads,
  reactions, users, pins, edits** and support **write** ops (post/update/delete/react/pin).
- **Real-world data.** Slack has a well-documented **export format** (`channels.json`,
  `users.json`, per-channel `YYYY-MM-DD.json`); our importer ingests it directly, plus a
  deterministic synthetic generator and hand-authoring — all through one canonical seed.
- **Agent fidelity.** Slack's API (`conversations.*`, `chat.*`, `ts`/`thread_ts`, cursor
  pagination) is the industry standard; an agent's Slack knowledge and real Slack SDKs transfer to
  the clone unchanged. Mattermost's `posts`/`root_id`/UUID model does not.
- **Control.** A single-container FastAPI + SQLite service is deterministic, fast to cold-start,
  and trivial to pre-seed and ship inside a task — better suited to reproducible sims than a full
  Mattermost + Postgres stack.

## What we carried over
The drop-in pattern (a service container + a client with tools + a mounted seed + a healthcheck),
and the split-harness verifier that reads state back rather than trusting the agent.
