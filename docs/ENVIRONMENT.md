# How the environment works (start to end)

This explains exactly what happens from the moment Oddish picks up a task to the moment a
reward is written — where the data comes from, how the two containers talk, and how the
verifier decides 0 or 1. Plain English, no prior Harbor knowledge assumed.

## The two containers

Every task is a `docker compose` project with two services:

- **`mattermost`** — the real Mattermost server (`mattermost/mattermost-team-edition:8.1.1`)
  with an **embedded Postgres** inside the same container. This is the "world" the agent
  operates on.
- **`client`** — a small Debian image where the **agent** runs. It carries the agent's
  Slack-branded tool — the `slack` CLI and `slack` MCP server (thin wrappers over `mmctl` /
  `mmctl-mcp`) — plus the verifier scripts.

They share one Docker network and find each other **by service name**: the client (via the
`slack` facade) talks to the server at `http://mattermost:8065`. We deliberately declare **no `networks:`** block in the
compose file, because the Harbor/Oddish runtime injects its own networking onto the client; an
explicit network would conflict with it. Both services pin `platform: linux/amd64` (Mattermost
and `mmctl` ship only for amd64).

## Step by step

### 1. Build & upload (self-contained)
Oddish uploads **only the task directory**. Everything needed to build both images lives inside
`tasks/<name>/environment/`:
- the `client` image's `Dockerfile` copies `mmctl` out of the Mattermost image and **compiles
  `mmctl-mcp` from a pinned commit** in a Go builder stage;
- the `mattermost` image's `Dockerfile` adds Postgres + a Python seeder to the product image.

Nothing references files outside the task folder, so the build is portable (this is what makes
it work on Modal).

### 2. The service boots and seeds itself
The `mattermost` container's entrypoint (`environment/mattermost/entrypoint.sh`):
1. starts the embedded Postgres (on port 5433, in tmpfs),
2. writes a `config.json` and launches the Mattermost server on `:8065`,
3. waits until `/api/v4/system/ping` responds,
4. runs the **seeder** (`environment/mattermost/seed.py`).

**Where the data comes from.** The seeder reads `environment/data/mattermost/scraped.json` — a
hand-authored file describing the workspace as a flat list of messages:

```json
{ "messages": [ { "channel": "incidents", "author": "carol", "content": "...", "timestamp": "2023-11-16T16:57:45+00:00" }, ... ] }
```

From that it creates: an **admin** (`admin@demo.local` / `AdminUser123!`), a **team**
(`test-demo`), the **channels** named in the file, the **users** named as authors, and the
**message history**.

Two important implementation choices (learned the hard way):
- **Channels and users are created over the REST API, not raw SQL.** Raw-SQL rows exist in the
  database but the running server caches around them, so things like `channel list`, user
  *deactivation*, and role changes silently don't work. Creating them through the API makes them
  fully "app-managed" so every later operation behaves correctly.
- **Posts are inserted via SQL**, purely so we can preserve the original historical timestamps
  (the REST "create post" endpoint always stamps "now").

### 3. The fault is injected (the "issue")
After a healthy workspace exists, the entrypoint runs the task's
`environment/data/mattermost/fault.sh` **if present**. The fault script logs in as admin and
breaks exactly one thing over the REST API — deactivate a user, archive a channel, flip a
config flag. This keeps the service image **identical across all tasks**; only the mounted
`data/` (the seed + the fault) differs. That's the whole trick that lets one service power many
different "issue, go fix it" scenarios.

### 4. The client wires up the agent's tools
The `client` container only starts once the server's healthcheck passes (`depends_on:
service_healthy`). Its entrypoint then authenticates the workspace connection with the admin
credentials and waits until the workspace is actually seeded, so by the time the agent arrives,
both the `slack` CLI and the `slack` MCP server "just work" with no setup.

### 5. The agent acts
The agent reads `instruction.md` (which states only the symptom and that it has the `slack`
tool), then explores and remediates using the `slack` CLI and/or the `slack` MCP tools. See
[TOOLS.md](TOOLS.md) for the surface.

### 6. The verifier scores
Harbor runs `tests/test.sh` (a thin wrapper) → `tests/run_verifier.sh` **inside the client
container**. The verifier does **not** trust logs or the agent's narration — it logs in as
admin and **queries the live REST API** for the resulting state, then writes `0` or `1` to
`/logs/verifier/reward.txt`. Examples:
- responder-lockout → `GET /users/username/carol` and check `delete_at == 0` (active),
- archived-channel → look up `#deploys` and check it resolves with `delete_at == 0`,
- file-sharing-broken → `GET /config` and check `FileSettings.EnableFileAttachments == true`.

### 7. The reward is bracketed
Every task ships a reference `solution/solve.sh` (the **oracle**). Harbor runs each task with
two reference agents: **`nop`** (does nothing) must score **0**, and **`oracle`** must score
**1**. This proves the verifier actually distinguishes "fixed" from "not fixed". All three
tasks here pass that bracket.

## Why these choices make it a good benchmark
- **Data lives in the server, never on the agent's disk** → the agent must use the tools, and
  the verifier's read-back genuinely reflects what the agent did.
- **Deterministic seed + a single injected fault** → identical starting state every run.
- **The reward is keyed on the fixed state**, and the broken state is set at seed time, so a
  no-op can never accidentally pass.
- **API read-back, not log-scraping** → clean, reproducible 0/1.
- **`nop`=0 / `oracle`=1 bracket on every task** → catches a broken task immediately.
- **Self-contained, no explicit networks, amd64 pinned** → runs the same locally and on Modal.
