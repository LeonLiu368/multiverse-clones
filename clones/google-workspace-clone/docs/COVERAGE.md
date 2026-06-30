# Coverage matrix — abundant-gworkspace-clone

The agent-used surface of Google Workspace this clone emulates, mapped capability →
HTTP endpoint → `gws-cli` command → `gws-mcp` tool → envelope fidelity → assessment
grade → tested. One HTTP API is the source of truth; the CLI and MCP server are thin
clients of it, so every row is reachable from **both** (R3 parity) unless marked
operator-only.

Surfaces: **Drive v3**, **Docs v1** (derived text/search are client-side over
`documents.get`, since the real Docs API has no such endpoints), **Calendar v3**,
**Gmail v1**.

Legend — **Envelope**: ✅ matches Google's response shape (kind/ids/error body).
**Assess**: ✅ = assessment-grade (≥3 of: stateful round-trip · multi-step · realistic
errors · query grammar · side-effecting devops shape). **Tested**: pytest file(s) that
cover the row (happy + ≥1 error path).

| # | Capability | HTTP endpoint | CLI command | MCP tool | Envelope | Assess | Tested |
|---|---|---|---|---|---|---|---|
| 1 | Drive list (q-grammar) | `GET /drive/v3/files` | `gws-cli drive ls -q` | `gws_list_files` | ✅ `drive#fileList` | ✅ | `test_api.py` `test_cli.py` `test_mcp.py` `test_parity.py` |
| 2 | Drive get metadata | `GET /drive/v3/files/{id}` | `gws-cli drive get` | `gws_get_file` | ✅ `drive#file` | – | `test_api.py` `test_cli.py` `test_mcp.py` `test_parity.py` |
| 3 | Drive export / media (text) | `GET /drive/v3/files/{id}/export` (and `?alt=media`) | `gws-cli drive export` | `gws_get_file_text` | ✅ text/plain | – | `test_api.py` `test_cli.py` `test_mcp.py` |
| 4 | Docs get (structural body) | `GET /v1/documents/{id}` | `gws-cli docs get` | `gws_get_document` | ✅ document resource | ✅ | `test_api.py` `test_cli.py` `test_mcp.py` `test_parity.py` |
| 5 | Docs text (derived) | (client over `documents.get`) | `gws-cli docs text` | `gws_get_document_text` | ✅ plain text | – | `test_cli.py` `test_mcp.py` `test_parity.py` `test_query.py` |
| 6 | Docs search (derived) | (client over `documents.get`) | `gws-cli docs search` | `gws_search_document` | ✅ `[{style,text}]` | – | `test_cli.py` `test_mcp.py` |
| 7 | Calendar list (q + window) | `GET /calendar/v3/calendars/{cal}/events` | `gws-cli calendar events` | `gws_list_events` | ✅ `calendar#events` | ✅ | `test_api.py` `test_cli.py` `test_mcp.py` `test_parity.py` |
| 8 | Calendar get | `GET /calendar/v3/calendars/{cal}/events/{id}` | `gws-cli calendar get` | `gws_get_event` | ✅ `calendar#event` | – | `test_api.py` `test_cli.py` `test_mcp.py` |
| 9 | **Calendar create (WRITE → READ round-trip)** | `POST /calendar/v3/calendars/{cal}/events` | `gws-cli calendar create` | `gws_create_event` | ✅ `calendar#event` (server-minted id) | ✅ | `test_api.py` `test_cli.py` `test_mcp.py` `test_parity.py` `test_roundtrip.py` |
| 10 | Gmail search (operators) | `GET /gmail/v1/users/{u}/messages` | `gws-cli gmail search` | `gws_search_messages` | ✅ `{messages,resultSizeEstimate}` | ✅ | `test_api.py` `test_cli.py` `test_mcp.py` `test_parity.py` `test_query.py` |
| 11 | Gmail get message | `GET /gmail/v1/users/{u}/messages/{id}` | `gws-cli gmail get` | `gws_get_message` | ✅ message (`payload.headers`, base64url body) | – | `test_api.py` `test_cli.py` `test_mcp.py` |
| 12 | Gmail get thread | `GET /gmail/v1/users/{u}/threads/{id}` | `gws-cli gmail thread` | `gws_get_thread` | ✅ thread (chronological messages) | ✅ | `test_api.py` `test_cli.py` `test_mcp.py` |

**Operator-only (not agent-facing; gated by `$GWS_CONTROL_TOKEN`, 404 when unset):**
`POST /_control/seed`, `POST /_control/reset`, `GET /_control/status`. World-building
(seed/import/hydrate) is a gateway-only entrypoint the agent can never call (R2.g); the
agent image ships no `api/` or `seed/` source (R2.k).

## Assessment-grade capabilities (≥5, R5.1)

| # | Capability | Why assessment-grade |
|---|---|---|
| 9 | **Calendar create** | **Stateful write→read round-trip** (insert → list/get observes it), multi-step (create then read back), realistic 400 INVALID_ARGUMENT on missing fields, side-effecting devops shape. **Exercised end-to-end by the bundled `gws-create-event` task (R5.2).** |
| 1 | Drive list | Real `q` grammar (name/fullText/mimeType `contains`/`=`/`!=`, `'id' in parents`, `trashed`, `and`/`or`/`not`/parens), `fullText` searches Doc bodies, invalid term → 400, multi-step (list → filter → get). |
| 10 | Gmail search | Real operator grammar (`from:`/`to:`/`subject:`/`label:` + space-AND/`OR`/parens), multi-step (search → get → thread), realistic errors. |
| 7 | Calendar list | `q` free-text + `[timeMin,timeMax)` window query, multi-step (list → get), filtering grammar. |
| 4 | Docs get | Deep structural-element tree is the gradeable payload; multi-step (drive ls → docs get/text); 404 NOT_FOUND on missing id. |
| 12 | Gmail thread | Multi-step conversation reconstruction (search → thread), chronological ordering, 404 on missing thread. |

## Envelope fidelity (R4.3)

- IDs/prefixes: Drive/Docs ids are ~44-char URL-safe tokens; Calendar event ids are
  base32hex tokens (`events.insert` mints them server-side, like Google).
- List envelopes: `{"kind":"drive#fileList","incompleteSearch":false,"files":[…]}`,
  `{"kind":"calendar#events","items":[…]}`, `{"messages":[{id,threadId}],"resultSizeEstimate":N}`.
- Errors: `{"error":{"code","message","status"}}` with `401 UNAUTHENTICATED`,
  `404 NOT_FOUND`, `400 INVALID_ARGUMENT` — matched to the HTTP status, like Google.
