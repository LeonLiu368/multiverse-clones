# abundant-gworkspace-clone

A **Google Workspace-faithful service clone** (Drive v3 + Docs v1 + Calendar v3 +
Gmail v1) for Harbor/Oddish environments, built the same way as `abundant-figma-clone`:
one HTTP API is the source of truth; `gws-cli` and the `gws-mcp` MCP server are thin
clients; seeded data lives only behind the API (mounted per task, or baked into the
`:prod-v1` image). The agent reaches state only over HTTP — it carries no seed and no
server/seed source (the thin `gworkspace-agent` image strips `api/` and `seed/`).

A Google **Doc** is the Figma-twin: a deeply-nested structural-element tree
(`body.content` → paragraphs → textRuns) stored as a JSON column and served verbatim
by `GET /v1/documents/{id}` — gradeable on text/structure, never on pixels.

The full agent-used surface, with the CLI command + MCP tool + envelope + assessment
grade for each capability, is the machine-checkable matrix in
**[`docs/COVERAGE.md`](docs/COVERAGE.md)**.

## Surface

| Method | Endpoint | Notes |
|---|---|---|
| GET | `/drive/v3/files` (`?q=`, `?pageSize=`) | `{kind:"drive#fileList", files:[…]}`; real `q` grammar |
| GET | `/drive/v3/files/{fileId}` (`?alt=media`) | Drive file resource (or text content) |
| GET | `/drive/v3/files/{fileId}/export` | export a file's text |
| GET | `/v1/documents/{documentId}` | a Docs document (`body` = structural tree) |
| GET | `/calendar/v3/calendars/{calId}/events` (`?q=`, `?timeMin=`, `?timeMax=`) | `{kind:"calendar#events", items:[…]}` |
| GET | `/calendar/v3/calendars/{calId}/events/{eventId}` | a Calendar event |
| **POST** | **`/calendar/v3/calendars/{calId}/events`** | **`events.insert` — create an event (WRITE → READ round-trip)** |
| GET | `/gmail/v1/users/{userId}/messages` (`?q=`) | Gmail search (`from:`/`to:`/`subject:`/`label:` + free-text) |
| GET | `/gmail/v1/users/{userId}/messages/{id}` | a Gmail message (`payload.headers` + base64url body) |
| GET | `/gmail/v1/users/{userId}/threads/{id}` | a Gmail thread |
| GET | `/health` ; token-gated `/_control/*` | operator-only seed/reset/status |

`gws-cli docs text/search` and the matching MCP tools are **client-side derivations**
over `GET /v1/documents/{id}` (the real Docs API has no such endpoints).

## Tools (CLI + MCP in parity)

`gws-cli`: `drive ls|get|export` · `docs get|text|search` · `calendar events|get|create`
· `gmail search|get|thread` · `seed …` (offline). The `gws-mcp` server exposes the same
operations as 12 tools (`gws_list_files`, `gws_get_file`, `gws_get_document`,
`gws_get_file_text`, `gws_get_document_text`, `gws_search_document`, `gws_list_events`,
`gws_get_event`, **`gws_create_event`**, `gws_search_messages`, `gws_get_message`,
`gws_get_thread`). CLI ↔ MCP parity is pinned by `tests/test_parity.py`.

## Quickstart

```bash
python3.13 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest tests/ -q                                  # full surface suite
gws-cli seed load fixtures/acme.json --out gws.db
GWS_DB=gws.db uvicorn gwsclone.api.app:app --port 8080 &
export GWS_API_URL=http://localhost:8080 GWS_TOKEN=t
gws-cli drive ls --format markdown
gws-cli docs text <documentId>
gws-cli calendar create -s "Q3 Retro" --start 2026-10-06T14:00:00Z --end 2026-10-06T15:00:00Z
gws-cli calendar events -q "Q3 Retro"                       # read the write back
```

## Image trio (the gateway)

| Image | Data | Use |
|---|---|---|
| `gworkspace-service` (`:latest`/`:sha-…`) | none | base API |
| `gworkspace-service:empty` | none | per-task fixture **mounted** at run time |
| `gworkspace-service:prod-v1` | corpus DB **baked in** | prod tasks; boots healthy with **no mount** |
| `gworkspace-agent:latest` | none | thin agent — `gws-cli` + `gws-mcp` only, no `api/`/`seed/` source |

Built + published multi-arch (`linux/amd64,linux/arm64`) by
`.github/workflows/build-service-image.yml` (or locally via `docker/build-prod-v1.sh`).

## Bundled tasks (`oddish/tasks/`)

- `gws-launch-date` / `-prod-v1` — recover a launch date from a Google Doc (read).
- `gws-launch-multihop` — chain Gmail → Calendar to resolve a date (read, multi-hop).
- `gws-event-room` — Takeout-scale corpus (1735 events / 2000 messages) reconciliation.
- `gws-create-event` — **write → read round-trip**: read a Gmail thread, create the
  confirmed event via the calendar write tool; the verifier reads it back through the
  API (nop=0 / oracle=1).

## Real2sim
Capture real Google data and import it (ids/structure preserved):
```bash
gws-cli seed import-real --drive drive.json --doc doc.json --emit fixture.json --out gws.db
gws-cli seed import-takeout --root ./Takeout --out gws.db    # Gmail .mbox / Calendar .ics / Drive tree
```
