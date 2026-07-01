# Logfire Query API — coverage matrix

## Real service
- name: Pydantic Logfire Query API
- api_base: https://logfire-api.pydantic.dev
- reference: https://logfire.pydantic.dev/docs/
- version: v2/query
- snapshot_date: 2026-06-30

Faithful to the real [Pydantic Logfire Query API](https://logfire.pydantic.dev/docs/reference/query-api/)
and the [Logfire MCP server](https://github.com/pydantic/logfire-mcp). The agent operates
the clone through the **`logfire` CLI** and the **`logfire-mcp` server**, both **thin
clients of one HTTP API** (`cli.query` → `POST /v2/query`). Auth mirrors Logfire's read
token (`Authorization: Bearer <token>`). The `records` table is one row per span, with the
real trace/span/exception/http columns.

Tier: **T2** — a real DuckDB SQL query grammar (`SELECT … WHERE … GROUP BY …`, time-window
scoping) over the `records` table.

| Capability | Endpoint | CLI | MCP tool | Envelope | Assessment-grade | Tested |
|---|---|---|---|---|---|---|
| Arbitrary SQL over `records` | `POST /v2/query` | `logfire query <sql> [--since --until --limit]` | `arbitrary_query(query\|sql, age?, min_timestamp?, max_timestamp?, limit?)` | `{schema:{fields:[{name,data_type}]}, data:[…]}` | **yes** — stateful-read, multi-step, query grammar, realistic errors (1,3,4,5) | `test_api`, `test_cli_mcp` |
| Recent exceptions | `POST /v2/query` (canned SQL) | `logfire exceptions [--since --limit]` | `find_exceptions_in_file(filepath?, …)` (real upstream name; `find_exceptions` kept as alias) | `[{start_timestamp, exception_type, exception_message, service_name, url_path, http_response_status_code}]` | **yes** — multi-step, query grammar, devops-investigation shape (2,4,5) | `test_api`, `test_cli_mcp` |
| Records schema | `POST /v2/query` (`limit 0`) | `logfire schema` | `get_logfire_records_schema()` (alias `schema_reference` for logfire-mcp `main`) | `{fields:[{name,data_type}]}` | **yes** — devops-investigation entry point; chains into query construction (multi-step + grammar precursor, 2,4) | `test_cli_mcp` (parity) |
| Health | `GET /health` | — | — | `{ok, records}` | — (operator) | `test_api` |
| Auth / read-only / validation | `POST /v2/query` (error paths) | (surfaced verbatim, exit 1) | (raises) | `401 {detail}`, `400 {error[,details]}`, `404 {error}` | **yes** — realistic product error envelopes, not 500s (3) | `test_api`, `test_cli_mcp` |

## Assessment-grade tally (R5)

An endpoint is assessment-grade with ≥3 of: (1) stateful, (2) multi-step,
(3) realistic errors, (4) query grammar, (5) side-effecting devops shape.

- **`arbitrary_query` / `logfire query`** — (1) stateful read of the corpus, (3) real
  DuckDB Binder errors + auth/read-only envelopes, (4) full SQL grammar (`WHERE`,
  `GROUP BY`, `ORDER BY`, aggregates), (5) "query logs to find a cause" devops shape. **4 criteria.**
- **`find_exceptions` / `logfire exceptions`** — (2) realistic use chains list→filter→drill,
  (3) real errors, (4) query grammar underneath, (5) the canonical incident-investigation
  move. **4 criteria.**
- **Error surface (`/v2/query` auth/read-only/validation)** — (3) the real Logfire error
  envelopes (`401 {"detail":"Invalid read token"}`, `400 {"error":"invalid query","details":…}`),
  plus (4) it's the boundary the query grammar is validated against. **≥3 when paired with the query path.**

Meets the **small-clone ≥3 assessment-grade** bar with the SQL query grammar as the
discriminating surface.

## R5.2 round-trip note

This is a **read-only** telemetry API (SELECT/WITH only, like real Logfire), so the
canonical "write→read round-trip" is **N/A**. The bundled task
(`oddish/tasks/logfire-incident-rca`) exercises the equivalent **read-investigation chain**
end-to-end: the agent must construct SQL over `records` to find the failing exception's
type, service, table, missing column, and occurrence count, then apply a code fix graded
against the exact recovered values (nop=0, oracle=1).

## Intentionally out of scope

- Write/ingest endpoints — the clone is a read-only Query API by design.
- The Logfire dashboards/alerts UI — not an agent-used surface.
