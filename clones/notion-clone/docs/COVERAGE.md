# Notion API coverage matrix

## Real service
- name: Notion API
- api_base: https://api.notion.com/v1
- reference: https://developers.notion.com/reference
- version: 2022-06-28 (Notion-Version)
- snapshot_date: 2026-06-30

Faithful to the agent-used surface of the [Notion API](https://developers.notion.com/reference).
Auth mirrors the integration token: requests carry `Authorization: Bearer <token>`
and `Notion-Version: 2022-06-28`; a non-empty token is accepted (presence == valid,
like a real integration secret). Every collection is the Notion list envelope
`{"object":"list","results":[…],"next_cursor":…,"has_more":…}`; every object carries
its `"object"` discriminator and a dashed-UUID `id`. Errors are the real shape
`{"object":"error","status":<code>,"code":"<code>","message":"…","request_id":…}`.

One capability = one HTTP endpoint = one `notion-cli` command = one `notion-mcp`
tool, all generated from this matrix over the shared `notionclone.client`
(`NotionClient`), so the CLI and MCP cannot drift (R3).

| Capability | HTTP endpoint | CLI command | MCP tool | Envelope | Assessment-grade | Tested |
|---|---|---|---|---|---|---|
| Retrieve page | `GET /v1/pages/{id}` | `pages get <id>` | `notion_retrieve_page` | `{"object":"page",…}` | – | ✅ happy+404 |
| Create page | `POST /v1/pages` | `pages create --parent --properties` | `notion_create_page` | `{"object":"page",…}` | **★** stateful, multi-step | ✅ happy+400+404 |
| Update page properties | `PATCH /v1/pages/{id}` | `pages update <id> --properties` | `notion_update_page` | `{"object":"page",…}` | **★** stateful round-trip | ✅ happy+404 |
| Archive page | `PATCH /v1/pages/{id}` (`archived`) | `pages archive <id> [--restore]` | `notion_update_page` (`archived`) | `{"object":"page","archived":true}` | **★** stateful round-trip | ✅ happy |
| Get block children | `GET /v1/blocks/{id}/children` | `blocks children <id>` | `notion_get_block_children` | list of `{"object":"block",…}` | – | ✅ happy+404 |
| Append block children | `PATCH /v1/blocks/{id}/children` | `blocks append <id> --children/--text` | `notion_append_block_children` | list of `{"object":"block",…}` | **★** stateful round-trip | ✅ happy+400 |
| Retrieve database | `GET /v1/databases/{id}` | `databases get <id>` | `notion_retrieve_database` | `{"object":"database",…schema}` | – | ✅ happy+404 |
| **Query database (filter+sorts)** | `POST /v1/databases/{id}/query` | `databases query <id> --filter --sorts` | `notion_query_database` | list of `{"object":"page",…}` | **★** query grammar, multi-step, real errors, pagination | ✅ happy×7+400+404 |
| Search by title | `POST /v1/search` | `search [query] --type --direction` | `notion_search` | list of page/db, `type:"page_or_database"` | **★** filter + sort + pagination | ✅ happy×2+400 |
| List comments | `GET /v1/comments?block_id=` | `comments list <page_id>` | `notion_list_comments` | list of `{"object":"comment",…}` | – | ✅ happy+400+404 |
| Create comment | `POST /v1/comments` | `comments add <page_id> -m` | `notion_create_comment` | `{"object":"comment",…}` | **★** stateful round-trip | ✅ happy+404+400 |
| List users | `GET /v1/users` | `users list` | `notion_list_users` | list of `{"object":"user",…}` | – | ✅ happy |
| Retrieve user | `GET /v1/users/{id}` | `users get <id>` | `notion_retrieve_user` | `{"object":"user",…}` | – | ✅ happy+404 |
| Retrieve self (bot) | `GET /v1/users/me` | `users me` | `notion_get_self` | `{"object":"user","type":"bot"}` | – | ✅ happy |
| Health | `GET /health` | – | – | `{"status":"healthy"}` | – | ✅ |
| **Control plane** (operator only) | `POST/GET /_control/{seed,reset,status}` | `notion-cli seed …` (offline) | — (never exposed) | token-gated, 404 when disabled | – (operator) | covered by control tests |

★ = labelled **assessment-grade** (see below). 14 agent capabilities, all in CLI⇄MCP parity.

## Assessment-grade capabilities (R5)

An endpoint is assessment-grade when it has ≥3 of: stateful round-trip · multi-step ·
realistic errors · query grammar · side-effecting devops shape. **7 are labelled**
(≥5 required):

1. **Query database** (`POST /v1/databases/{id}/query`) — the headline. A real
   filter grammar (single + compound `and`/`or`) over typed properties (title,
   rich_text, number, select, status, multi_select, checkbox, date, people) with
   operators per type (`equals`, `contains`, `greater_than_or_equal_to`, `before`,
   `is_empty`, …), real `sorts` (property + `timestamp`, ascending/descending), and
   opaque-cursor pagination. Wrong operator/type → `validation_error` (400, not 500).
   Stateful (a created page appears in a later query), multi-step (query → act),
   query grammar, realistic errors, pagination → **5/5**.
2. **Create page** — stateful + multi-step (resolve parent DB → build property
   values to the schema → create). Bad parent → `object_not_found`. **3/5**.
3. **Update page properties** — stateful round-trip; the patch is observable on a
   later retrieve **and** changes which rows the query returns. **3/5**.
4. **Archive page** — stateful round-trip (toggle `archived`, observable on read;
   archived rows drop out of queries/search). Devops shape (close-out). **3/5**.
5. **Append block children** — stateful round-trip; the appended blocks appear in a
   later `GET …/children`. **3/5**.
6. **Search** — title search with an `object` filter and a sort direction, paginated.
   Multi-step (search → open → act), filtering, pagination. **3/5**.
7. **Create comment** — stateful round-trip; the comment appears in a later
   `GET /v1/comments`. Devops shape (post a status/confirmation). **3/5**.

**Write→read round-trip exercised by a bundled task** (R5.2): `notion-db-triage`
makes the agent **query** the Tasks DB to find a page, **update** its Status + Done
properties, and **create** a confirmation comment — then the verifier reads all
three back through the API. (`nop=0`, `oracle=1`, validated locally and in the
two-container docker shape.)

## Intentionally out of scope

Database **create/update schema** (agents rarely author schemas), property-item
pagination for huge rollups, file uploads, link previews, OAuth flows, and webhooks.
The corpus is authored/generated; agents read it, query it, mutate page state, and
comment. This is the surface a coding/ops agent actually touches.
