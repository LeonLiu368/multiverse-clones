# notion-clone architecture

## Fidelity tier: T2 (handwritten + real query grammar)

Notion has **no faithful self-hostable OSS** engine (the open-source "Notion-likes"
— AppFlowy, AFFiNE, Outline — diverge sharply from Notion's REST API shape), so the
agent-used surface is **handwritten** over FastAPI + SQLite + SQLAlchemy. The clone
clears T2 (vs T1) because the database **query endpoint implements Notion's real
filter + sort grammar** (`store.query_database`): compound `and`/`or` filters over
typed properties with per-type operators, real `sorts`, and opaque-cursor
pagination — the assessment-grade surface (see `COVERAGE.md`).

## The single source of truth

`store.py` is the only place that reads/writes the DB and serializes Notion shapes.
The HTTP API (`api/app.py`), the seed loader (`seed/load.py`), and the query engine
all go through it, so reads, writes, search, query, and seeding emit the **same
envelopes**: objects carry `"object"`, collections are
`{"object":"list","results":…,"next_cursor":…,"has_more":…}`, ids are dashed UUIDs,
errors are `{"object":"error","status","code","message","request_id"}`.

## The parity seam: one shared client

`client.py` (`NotionClient`) is the single HTTP client. **Both** the CLI
(`cli/main.py`) and the MCP server (`mcp/server.py`) import it — one capability is
one `NotionClient` method, called identically from one CLI command and one MCP tool.
Neither surface contains business logic; they can't drift, and the parity tests
prove it by comparing their outputs over the real network.

## agent + gateway (the runtime model)

Two containers:

- **gateway** (`notion` service) — the HTTP API + CLI/MCP + seeder; the only place
  data lives. Shipped as the **image trio**: `notion-service` (base, no data) →
  `:prod-v1` (corpus DB baked in, served mount-free) + `:empty` (mount target).
- **agent** (`main`) — neutral `python:slim`, carries the codebase + `notion-cli` +
  `notion-mcp`, **no data, no api/, no seed/**. Reaches the gateway only over HTTP by
  name (`http://notion:3000`).

### Two seeding paths (both supported)

| Path | Image | Delivery |
|---|---|---|
| **Baked-DB (GHCR)** | `:prod-v1` | `COPY notion_corpus.db /srv/notion.db`; the entrypoint serves an existing `$NOTION_DB` as-is, **no mount, no seeding** |
| **Empty + mount** | `:empty` | base API, no data; per-task `fixture.json` mounted at `$NOTION_FIXTURE` into the gateway, **or** pushed via the token-gated `/_control/seed` |

Switching a task between them is the **image tag alone**.

## Operator / agent boundary

World-building is operator-only and unreachable by the agent:

- `notion-cli seed generate|load` build a DB file **offline** (no running server) —
  used to bake the corpus, not by the agent.
- `/_control/{seed,reset,status}` hydrate a **running** gateway, gated by
  `NOTION_CONTROL_TOKEN`. Unset → every route 404s (disabled). Wrong token → 404
  (not 401), so it isn't discoverable by probing. The agent container never gets the
  token.
- The agent image **deletes** `api/` and `seed/`, so the corpus generator/source
  isn't present to grep (R2.k leak rule). A build-time smoke test asserts their
  absence; an isolation test asserts no corpus DB on the agent's disk.

## Determinism

`ids.gen_uuid(rng)` draws from a seeded `random.Random`, and the generator stamps
every user/database/page/block/comment with a deterministic id and fixed timestamps.
Rebuilding the corpus from the same `--seed` yields a **byte-identical** DB (R1.6),
verified by hashing all table rows across two builds.
