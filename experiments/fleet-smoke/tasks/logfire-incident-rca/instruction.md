# Fix the worker incident

The **oddish-worker** service is throwing a database error in production and failing to
lease queue slots. The schema for the worker's `queue_slots` table lives in the repo:

- `/workspace/queue/models.py` — `SLOT_COLUMNS` + the table DDL (source of truth for the
  table's columns).
- `/workspace/queue/worker.py` — `lease_slot(...)` stamps a lock-timestamp column when it
  grabs a slot; it raises if that column isn't in the schema (mirrors the prod failure).
- `/workspace/incident_rca.py` — `root_cause()` returns the diagnosis. The fields are
  blank; you must fill them in **from the telemetry**, not by guessing.

Run the visible checks with:

```bash
cd /workspace && python3 -m pytest tests/ -q
```

They confirm the *shape* of the fix and the RCA, but not the actual values — those live
in the **production telemetry**, not the repo.

## The telemetry

The incident's traces, spans, and exceptions are in **Logfire**. You have the Logfire
tools pointed at the gateway:

- the **`logfire`** CLI (e.g. `logfire schema`, `logfire exceptions --limit 50`,
  `logfire query "SELECT … FROM records WHERE … GROUP BY …"`), and
- the **`logfire`** MCP server (`arbitrary_query`, `find_exceptions`,
  `get_logfire_records_schema`).

The `records` table is one row per span, with `exception_type`, `exception_message`,
`service_name`, `url_path`, `http_response_status_code`, `start_timestamp`, etc. Query it
to find the worker's failing exception: which **service** emits it, which database
**table** and **column** the error names, the exact **exception type**, and **how many**
records carry it in the incident window. The incident window starts `2026-06-24`.

## What to do

1. Read the telemetry and recover the root cause. Fill in `root_cause()` in
   `/workspace/incident_rca.py` with the exact values (keep the keys and types).
2. Apply the schema fix in `/workspace/queue/models.py`: add the missing column the
   worker writes (both to `SLOT_COLUMNS` and the DDL types) so `lease_slot` stops raising.

When the RCA matches the telemetry and the schema fix is applied, you're done.
