# abundant-slack-clone

A **Slack-faithful service clone** for Harbor/Oddish simulation environments. An agent "drops in"
to a multi-service task and operates a realistic Slack workspace over a **CLI** (`slack-cli`) — the
service mirrors a subset of the real **Slack Web API**, is **filled with real or synthetic data**,
and is **verifiable** from tasks.

Built with **Python + FastAPI + SQLite**. Inspired by APEX-SWE's Mattermost integration but
Slack-faithful and richer (threads, reactions, users, pins, edits, writes). See
[docs/apex-mattermost-analysis.md](docs/apex-mattermost-analysis.md) and
[docs/slack-api-coverage.md](docs/slack-api-coverage.md).

## Architecture

```
producer ─▶ canonical seed ─▶ SQLite (slack.db) ─▶ FastAPI Slack API ◀─ slack-cli / slack-mcp / SDKs
  ├─ real:      Slack export importer
  ├─ synthetic: deterministic generator
  └─ authored:  hand-written workspace.json
```

The HTTP **Slack API** is the realism core; `slack-cli` and the `slack-mcp` MCP server are thin
clients of it, so they stay in parity automatically. No auth in v1 (open API on the internal
network); the only privileged surface is a token-gated `/_control/*` plane for operator reseeding.

The slack-clone runs as **its own container with its own baked-in workspace data**; tasks pick a
workspace by name (`SLACK_WORKSPACE`) and carry **no seed data themselves**. See
[docs/architecture.md](docs/architecture.md) for the full design, and
[docs/cli-and-db-commands.md](docs/cli-and-db-commands.md) for a command cheat-sheet.

## Quickstart

```bash
uv venv && uv pip install -e ".[dev]"

# 1) seed a workspace (pick one)
slack-cli seed generate --seed 42 --out slack.db                 # synthetic, deterministic
slack-cli seed import-export ./my-slack-export --out slack.db    # a real Slack export (dir or .zip)
slack-cli seed load workspace.json --out slack.db                # hand-authored canonical seed

# 2) serve it
SLACK_DB=slack.db uvicorn slackclone.api.app:app --port 3000

# 3) use it (another shell)
export SLACK_API_URL=http://localhost:3000
slack-cli channels list --format markdown
slack-cli channels history incidents --format markdown
slack-cli thread incidents <ts> --format markdown
slack-cli post incidents "ROOT CAUSE: connection pool exhaustion"
slack-cli search "latency" --format markdown
```

## Seeding (do it yourself — real & synthetic)

One **canonical seed** (`src/slackclone/seed/schema.py`) is the single seam; three producers target
it:

| Source | Command |
|---|---|
| Synthetic (deterministic) | `slack-cli seed generate --users 25 --channels 8 --days 30 --seed 42 --out slack.db [--emit workspace.json]` |
| Real Slack export | `slack-cli seed import-export ./export[.zip] --out slack.db [--emit workspace.json]` |
| Hand-authored | edit `workspace.json` → `slack-cli seed load workspace.json --out slack.db` |

`--emit` writes the portable canonical seed JSON. Commit canonical workspaces into the repo-level
[`workspaces/`](workspaces/) directory (NOT into a task) — they're baked into the slack image as a
named catalog and selected per task with `SLACK_WORKSPACE`.

## Use in a Harbor/Oddish task

Drop in the [`slack` service](harbor/slack-service/) (serves the API, seeds a baked-in workspace by
name via `SLACK_WORKSPACE`) and give your client container `slack-cli` (+ `slack-mcp`) and
`SLACK_API_URL`. Tasks carry **no seed data** — see [docs/architecture.md](docs/architecture.md).
An **Oddish-runnable** task suite lives in [oddish/](oddish/) — see
[oddish/tasks/slack-incident-triage/](oddish/tasks/slack-incident-triage/) (incident triage with a
split-harness verifier; `nop` → reward 0, `oracle` → reward 1). Run with
`oddish run oddish/tasks -a gemini-cli -m google/gemini-3.1-pro-preview --n-trials 1`.

## Develop / test

```bash
.venv/bin/python -m pytest -q                              # importer, generator, API, CLI, catalog, control, MCP
docker build -f docker/Dockerfile        -t abundant-slack-clone:latest .   # service image
docker build -f docker/client.Dockerfile -t abundant-slack-client:latest .  # agent image (slack-cli + slack-mcp)
```

## Roadmap
DMs/private write paths; reactions.remove /
pins.remove; a minimal web UI for human/VLM inspection.
