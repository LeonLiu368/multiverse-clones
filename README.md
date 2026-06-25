# abundant-gworkspace-clone

A **Google Workspace-faithful service clone** (Drive v3 + Docs v1, this slice) for
Harbor/Oddish environments, built the same way as `abundant-figma-clone`: one HTTP
API is the source of truth; `gws-cli` and the `gws-mcp` MCP server are thin clients;
seeded data lives only behind the API and is mounted per task.

A Google **Doc** is the Figma-twin: a deeply-nested structural-element tree
(`body.content` → paragraphs → textRuns) stored as a JSON column and served verbatim
by `GET /v1/documents/{id}` — gradeable on text/structure, never on pixels.

## Surface (this slice)

| Method | Endpoint |
|---|---|
| GET | `/drive/v3/files` (`?q=`, `?pageSize=`) → `{kind:"drive#fileList", files:[…]}` |
| GET | `/drive/v3/files/{fileId}` → a Drive file resource |
| GET | `/v1/documents/{documentId}` → a Docs document (`body` = structural tree) |
| GET | `/health` ; token-gated `/_control/*` |

`gws-cli docs text/search` and the matching MCP tools are **client-side derivations**
over `GET /v1/documents/{id}` (the real Docs API has no such endpoints).

## Quickstart

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
gws-cli seed load fixture.json --out gws.db          # or: gws-cli seed import-real --drive d.json --doc doc.json --emit fixture.json
GWS_DB=gws.db uvicorn gwsclone.api.app:app --port 8080
export GWS_API_URL=http://localhost:8080
gws-cli drive ls --format markdown
gws-cli docs text <documentId>
```

## Real2sim
Capture real Google data and import it (ids/structure preserved):
```bash
# GET https://www.googleapis.com/drive/v3/files?fields=files(id,name,mimeType,parents,modifiedTime,owners)  > drive.json
# GET https://docs.googleapis.com/v1/documents/<id>                                                          > doc.json
gws-cli seed import-real --drive drive.json --doc doc.json --emit fixture.json --out gws.db
```

## Tooling reuse
The Google **discovery→OpenAPI** specs are faithful for the list/read surface (use
them to schema-validate responses), and a mature Workspace **MCP server** can be
repointed at this backend by overriding its discovery `rootUrl` (one `build()`
swap) — see the spike notes. The rich Docs/Sheets bodies must be seeded from real
captures (a generic mock can't synthesize them).
