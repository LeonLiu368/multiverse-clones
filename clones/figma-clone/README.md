# abundant-figma-clone

A **Figma-faithful service clone** for Harbor/Oddish simulation environments. An agent "drops
in" to a task and operates a realistic Figma file over a **CLI** (`figma-cli`) and an **MCP
server** (`figma-mcp`) — the service mirrors a subset of the real **Figma REST API**, is
**filled with seeded design data** the agent can only reach through the tools, and is
**verifiable** from tasks.

Built with **Python + FastAPI + SQLite**. Inspired by the [abundant-slack-clone] and
[ticketvector] service clones, but Figma-faithful: the **document node tree** (with `fills`,
`characters`, `style`, `cornerRadius`, `layoutMode`/`itemSpacing`/`padding*`,
`absoluteBoundingBox`) is the rich, read-mostly payload an agent must mine to recover a
design spec.

## Architecture

```
producer ─▶ canonical seed ─▶ SQLite (figma.db) ─▶ FastAPI Figma REST API ◀─ figma-cli / figma-mcp
  ├─ synthetic: deterministic generator (design system)
  ├─ import:    real `GET /v1/files/:key` JSON dump
  └─ authored:  hand-written fixture.json   (planted spec + decoys)
```

The HTTP **Figma REST API** is the realism core; `figma-cli` and the `figma-mcp` MCP server
are thin clients of it, so they stay in parity automatically. Auth mirrors Figma's
`X-Figma-Token` personal-access-token header. The only privileged surface is a token-gated
`/_control/*` plane for operator reseeding (gated by `FIGMA_CONTROL_TOKEN`; returns 404 when
unset). The node tree is the source of truth — `GET /v1/images` returns URLs to pre-baked
placeholder PNGs; pixels are not graded.

### One image, per-task data

The clone ships as **one pullable `figma-service` image** containing the API + `figma-cli` +
`figma-mcp` but **no task data**. A task provides its design data **per task**, either by
mounting a `fixture.json` into the *service* container only (the agent's container never
mounts it) or by pushing it through the token-gated `/_control/seed`. Either way the seeded
spec lives only behind the API — if an agent can `cat` the answer, the task is broken.

## Quickstart

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# 1) seed a file (pick one)
figma-cli seed generate --seed 42 --out figma.db                 # synthetic, deterministic
figma-cli seed import-file ./file-dump.json --out figma.db       # a real GET /v1/files/:key dump
figma-cli seed load fixture.json --out figma.db                  # hand-authored canonical seed

# 2) serve it
FIGMA_DB=figma.db uvicorn figmaclone.api.app:app --port 3000

# 3) use it (another shell)
export FIGMA_API_URL=http://localhost:3000
figma-cli files get <KEY> --format markdown
figma-cli tree <KEY>
figma-cli node <KEY> 1:7
figma-cli text <KEY>
figma-cli styles list <KEY> --format markdown
figma-cli comments list <KEY> --format markdown
figma-cli comments add <KEY> --node 1:7 -m "implemented per spec"
```

## API coverage

| Method | Endpoint |
|---|---|
| GET | `/v1/files/{key}` (`?ids=`, `?depth=`) |
| GET | `/v1/files/{key}/nodes?ids=1:2,1:3` |
| GET/POST/DELETE | `/v1/files/{key}/comments[/{id}]` |
| GET | `/v1/files/{key}/components` · `/component_sets` · `/styles` |
| GET | `/v1/files/{key}/versions` |
| GET | `/v1/images/{key}?ids=…&format=png&scale=2` |
| GET | `/v1/teams/{team_id}/projects` · `/v1/projects/{project_id}/files` |
| GET | `/health` · `/v1/me` · token-gated `/_control/*` |

The `figma-cli` `tree` / `node` / `text` / `search` commands (and the matching MCP tools)
are **client-side derivations** over `GET /v1/files/{key}` — the real Figma API has no such
endpoints, so the API stays faithful and the convenience lives in the thin client.

## Use in a Harbor/Oddish task

An Oddish-runnable task suite lives in [`oddish/`](oddish/) — see
[`oddish/tasks/figma-spec-recovery/`](oddish/tasks/figma-spec-recovery/): an observability
task where the exact component spec is buried in the file's node tree and a comment thread
with superseded proposals, and the agent must recover it to make a pytest suite pass
(`nop` → reward 0, `oracle` → reward 1). The task **pulls** the `figma-service` image and
mounts its own `fixture.json` into the service container.

To author new tasks, use the **`figma-observability-task-builder`** skill.

[abundant-slack-clone]: ../abundant-slack-clone
[ticketvector]: https://github.com/abundant-ai/ticketvector
