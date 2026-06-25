# abundant-logfire-clone

A thin, **faithful Logfire clone** for agent-eval: serves Logfire's Query API
(`POST /v2/query` — SQL over a `records` table) backed by DuckDB, so an agent debugs the
way an Abundant SWE actually does — `SELECT … FROM records WHERE …`, with real
**traces/spans** (`trace_id/span_id/parent_span_id/duration`), **exceptions**
(`exception_type/message/stacktrace`), and **http** columns — unlike mapping telemetry into
gauge/Loki log lines (which loses all of that).

- Same endpoint + `{schema,data}` response + required body (`sql` + `min_timestamp`,
  optional `max_timestamp`/`limit`) + time-window scoping as the real Logfire Query API.
- Read-only (SELECT/WITH only), Bearer read token, offline, data sealed behind the API.
- `build.sh <records.json> <tag>` bakes a per-incident records corpus into a gateway image.

Capture the records with `spoink` (rich columns incl. trace/span/exception).
