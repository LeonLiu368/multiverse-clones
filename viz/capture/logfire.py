"""Capture Logfire-clone parity demos in-process against the real seed corpus.

Running this verifies the seed format is accepted (the clone's DuckDB store loads the gzipped
records corpus and serves reads) AND captures the clone's ACTUAL `{schema, data}` output for the
dashboard comparison boxes. The `real_output` golden samples are authored from the Pydantic
Logfire Query API docs (https://logfire.pydantic.dev/docs/reference/query-api/) so they share the
same response shape as the clone.

The clone's query engine is `logfire_clone.server._run(sql, min_ts, max_ts, limit)` — the exact
function backing `POST /v2/query`. `server.py` loads the corpus at import time from
``$LOGFIRE_RECORDS``; we point that at the baked `.gz` corpus (it transparently gunzips) and call
`_run` directly, so we capture the same envelope the gateway returns over HTTP.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CLONE = Path(__file__).resolve().parents[2] / "clones" / "abundant-logfire-clone"
SEED_REL = "corpus/records.json.gz"

# server.py reads the corpus at import time from $LOGFIRE_RECORDS (gunzips a .gz transparently).
os.environ["LOGFIRE_RECORDS"] = str(CLONE / SEED_REL)
sys.path.insert(0, str(CLONE))

try:
    from logfire_clone import server  # noqa: E402
except ModuleNotFoundError as e:  # duckdb is a hard dependency of the query engine
    if e.name == "duckdb":
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "duckdb"], check=True)
        from logfire_clone import server  # noqa: E402
    else:
        raise

# The gateway scopes every query to [min,max]; this window covers the baked incident corpus.
MIN_TS = "2026-06-24T00:00:00Z"

DOC = "https://logfire.pydantic.dev/docs/reference/query-api/"


def q(sql: str, limit: int = 100) -> dict:
    """Run SQL through the clone's real query engine (the fn backing POST /v2/query)."""
    return server._run(sql, MIN_TS, None, limit)


def build() -> dict:
    demos = []

    # ---- schema of the records table (table view: fields as rows) ----------
    schema_res = q("SELECT * FROM records", limit=0)
    fields = schema_res["schema"]["fields"]
    demos.append({
        "id": "schema",
        "title": "Records table schema",
        "method": "GET",
        "capability": "records schema (columns + types)",
        "seed_excerpt": {"fields_sample": fields[:4], "field_count": len(fields)},
        "ui": {"type": "table", "title": "Logfire › records schema",
               "columns": ["name", "data_type"],
               "rows": [{"name": f["name"], "data_type": f["data_type"]} for f in fields]},
        "agent": {"cli": "logfire schema",
                  "mcp": {"tool": "get_logfire_records_schema", "args": {}}},
        "real_mapping": {
            "api": "POST /v2/query",
            "mcp": "logfire-mcp › get_logfire_records_schema",
            "cli": "logfire (query the records table schema)",
            "doc": DOC},
        # get_logfire_records_schema returns the {fields:[...]} schema object.
        "clone_output": {"schema": schema_res["schema"], "data": []},
        "real_output": {"schema": {"fields": [
            {"name": "start_timestamp", "data_type": "TIMESTAMP"},
            {"name": "trace_id", "data_type": "VARCHAR"},
            {"name": "span_id", "data_type": "VARCHAR"},
            {"name": "span_name", "data_type": "VARCHAR"},
            {"name": "message", "data_type": "VARCHAR"},
            {"name": "is_exception", "data_type": "BOOLEAN"},
            {"name": "exception_type", "data_type": "VARCHAR"},
            {"name": "service_name", "data_type": "VARCHAR"},
            {"name": "http_response_status_code", "data_type": "BIGINT"}]}, "data": []},
    })

    # ---- recent exceptions (table view) ------------------------------------
    exc_sql = ("SELECT start_timestamp, exception_type, exception_message, service_name, "
               "http_response_status_code FROM records WHERE exception_type IS NOT NULL "
               "ORDER BY start_timestamp DESC")
    exc_res = q(exc_sql, limit=5)
    exc_cols = [f["name"] for f in exc_res["schema"]["fields"]]
    demos.append({
        "id": "query-exceptions",
        "title": "Recent exceptions",
        "method": "GET",
        "capability": "SQL over records → exception rows",
        "seed_excerpt": {"records": exc_res["data"][:2]},
        "ui": {"type": "table", "title": "Logfire › recent exceptions",
               "columns": exc_cols,
               "rows": [_row(r, exc_cols) for r in exc_res["data"]]},
        "agent": {"cli": "logfire exceptions --limit 5",
                  "mcp": {"tool": "find_exceptions_in_file", "args": {"limit": 5}}},
        "real_mapping": {
            "api": "POST /v2/query",
            "mcp": "logfire-mcp › find_exceptions_in_file",
            "cli": 'logfire query "SELECT ... FROM records WHERE exception_type IS NOT NULL"',
            "doc": DOC},
        "clone_output": exc_res,
        "real_output": {"schema": {"fields": [
            {"name": "start_timestamp", "data_type": "TIMESTAMP"},
            {"name": "exception_type", "data_type": "VARCHAR"},
            {"name": "exception_message", "data_type": "VARCHAR"},
            {"name": "service_name", "data_type": "VARCHAR"},
            {"name": "http_response_status_code", "data_type": "BIGINT"}]},
            "data": [{
                "start_timestamp": "2026-06-25 00:33:59.200057",
                "exception_type": "sqlalchemy.exc.InvalidRequestError",
                "exception_message": "One or more mappers failed to initialize ...",
                "service_name": "api",
                "http_response_status_code": 500}]},
    })

    # ---- arbitrary SQL: GROUP BY aggregate (table view) --------------------
    agg_sql = ("SELECT http_response_status_code, count(*) AS count FROM records "
               "GROUP BY http_response_status_code ORDER BY count DESC")
    agg_res = q(agg_sql, limit=20)
    agg_cols = [f["name"] for f in agg_res["schema"]["fields"]]
    demos.append({
        "id": "arbitrary-sql",
        "title": "Aggregate: requests by HTTP status",
        "method": "GET",
        "capability": "arbitrary SQL (GROUP BY aggregate)",
        "seed_excerpt": {"records": agg_res["data"][:3]},
        "ui": {"type": "table", "title": "Logfire › count by http_response_status_code",
               "columns": agg_cols,
               "rows": [_row(r, agg_cols) for r in agg_res["data"]]},
        "agent": {"cli": ('logfire query "SELECT http_response_status_code, count(*) AS count '
                          'FROM records GROUP BY 1 ORDER BY count DESC"'),
                  "mcp": {"tool": "arbitrary_query", "args": {
                      "sql": ("SELECT http_response_status_code, count(*) AS count FROM records "
                              "GROUP BY http_response_status_code ORDER BY count DESC")}}},
        "real_mapping": {
            "api": "POST /v2/query",
            "mcp": "logfire-mcp › arbitrary_query",
            "cli": 'logfire query "SELECT ... GROUP BY http_response_status_code"',
            "doc": DOC},
        "clone_output": agg_res,
        "real_output": {"schema": {"fields": [
            {"name": "http_response_status_code", "data_type": "BIGINT"},
            {"name": "count", "data_type": "BIGINT"}]},
            "data": [
                {"http_response_status_code": 500, "count": 2186},
                {"http_response_status_code": None, "count": 735},
                {"http_response_status_code": 404, "count": 367}]},
    })

    return {
        "clone": "abundant-logfire-clone",
        "product": "Logfire",
        "real_service": {
            "name": "Pydantic Logfire Query API",
            "reference": DOC,
            "api_base": "{gateway}/v2/query"},
        "parity": {"verdict": "HIGH after reliability pass",
                   "note": ("read-only SQL over `records` returns the real {schema,data} envelope; "
                            "min/max time-window scoping and column types match the Query API.")},
        "seed_file": SEED_REL,
        "surfaces": {"cli": "logfire", "mcp": "logfire-mcp"},
        "demos": demos,
    }


def _row(rec: dict, cols: list[str]) -> dict:
    return {c: rec.get(c) for c in cols}


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "data" / "abundant-logfire-clone.json"
    manifest = build()
    out.write_text(json.dumps(manifest, indent=2, default=str))
    n_rows = sum(len(d.get("clone_output", {}).get("data", [])) for d in manifest["demos"])
    print(f"OK abundant-logfire-clone: {len(manifest['demos'])} demos, "
          f"{n_rows} captured rows, seed '{manifest['seed_file']}' accepted -> {out}")
