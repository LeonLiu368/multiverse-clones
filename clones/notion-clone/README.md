# notion-clone

A **Notion-faithful service clone** for Harbor/Oddish agent-eval environments —
built to **Clone Standard v1**. It serves the agent-used subset of the
[Notion API](https://developers.notion.com/reference) (pages, blocks, databases
with a real **filter + sort query grammar**, search, comments, users) over one HTTP
API, with a **CLI** (`notion-cli`) and an **MCP server** (`notion-mcp`) in parity as
thin clients, packaged as a two-container **agent + gateway** Harbor task with
**GHCR image-DB seeding** (`:prod-v1` bakes the corpus and serves it mount-free).

Fidelity tier: **T2** (handwritten + a real query engine). Notion has no faithful
self-hostable OSS, so the surface is handwritten — see `docs/architecture.md`.

## Layout

```
src/notionclone/
  models.py        SQLAlchemy ORM (users, databases, pages, blocks, comments)
  db.py            engine/session helpers (SQLite from $NOTION_DB)
  ids.py           UUIDv4 ids (dashed, deterministic under a seeded RNG)
  store.py         THE SEAM: data access + Notion-shaped serialization + the QUERY ENGINE
  client.py        the shared HTTP client (NotionClient) — CLI and MCP both import it
  api/app.py       FastAPI; /v1/... routes; real envelopes + error objects
  api/control.py   token-gated /_control/{seed,reset,status}  (operator only)
  cli/main.py      notion-cli  (typer, over NotionClient) + offline `seed` verbs
  mcp/server.py    notion-mcp  (FastMCP stdio, over NotionClient)
  seed/            schema.py (canonical seed) · generator.py (deterministic corpus) · load.py
docker/            Dockerfile (base) · Dockerfile.empty · Dockerfile.prod-v1 · Dockerfile.agent · entrypoint.sh
docs/              COVERAGE.md (the matrix) · architecture.md · PROD-OVERLAY.md
oddish/tasks/notion-db-triage/   a bundled Harbor task (write->read round-trip)
tests/             pytest: every endpoint/CLI/MCP + parity + isolation
clone-spec.yaml    the creator->auditor manifest
notion_corpus.db   the baked corpus (deterministic; :prod-v1 COPYs it)
```

## Quickstart (local, no docker)

```bash
python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]"
# build a corpus and serve it
.venv/bin/notion-cli seed generate --out notion.db
NOTION_DB=notion.db .venv/bin/uvicorn notionclone.api.app:app --port 3000 &
export NOTION_API_URL=http://localhost:3000 NOTION_TOKEN=t
# query the Tasks database with a real filter + sort
DBID=$(notion-cli search Tasks --type database | jq -r .results[0].id)
notion-cli databases query "$DBID" \
  --filter '{"and":[{"property":"Done","checkbox":{"equals":false}},
                    {"property":"Priority","select":{"equals":"Urgent"}}]}' \
  --sorts  '[{"property":"Estimate","direction":"descending"}]'
# the same capability via MCP:  tool notion_query_database
```

## Tests

```bash
.venv/bin/pytest          # 73 pass, 1 skip (isolation asserts only in the agent container)
```

The suite boots a real uvicorn server in a background thread and routes both the CLI
and the MCP server at it over HTTP — so the parity tests compare the two real
surfaces, not an in-process shim.

## Docker — the image trio + agent

```bash
docker build -f docker/Dockerfile        -t notion-service:base .
docker build -f docker/Dockerfile.empty   --build-arg BASE=notion-service:base -t notion-service:empty .
docker build -f docker/Dockerfile.prod-v1 --build-arg BASE=notion-service:base -t notion-service:prod-v1 .
docker build -f docker/Dockerfile.agent   -t notion-agent .
# :prod-v1 serves the baked corpus with NO mount:
docker run -d -p 3000:3000 notion-service:prod-v1
curl -s localhost:3000/v1/users -H 'Authorization: Bearer t' -H 'Notion-Version: 2022-06-28'
```

## The bundled task

`oddish/tasks/notion-db-triage` — the agent must query the **Tasks** database, find
the "Rotate prod database creds" page, mark it **Done**, and post a confirmation
comment; the verifier reads the state back through the API. Validated locally and in
the full two-container docker shape: **nop = 0.0, oracle = 1.0**. Run
`bash oddish/tasks/notion-db-triage/validate_local.sh` (uses the project venv).

## Operator vs agent boundary

World-building (`notion-cli seed …`, `/_control/seed`) is **operator-only**, never an
agent capability. The agent image strips `api/` and `seed/` and carries no corpus on
disk; it reaches state only through the tools over HTTP. See `docs/architecture.md`.
