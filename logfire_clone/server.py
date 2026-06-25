"""Thin Logfire clone — serves Logfire's Query API (`POST /v2/query`: SQL over a `records`
table) backed by DuckDB, so an agent debugs the way an Abundant SWE actually does:
`SELECT … FROM records WHERE …`, with real traces/spans/exceptions/http columns — unlike
the gauge/Loki flattening. Read-token Bearer auth; offline; data sealed behind the API.

Faithful surface: same endpoint, same `{schema, data}` response, same required body
(`sql` + `min_timestamp`, optional `max_timestamp`/`limit`), same time-window scoping
(min/max bound which records the SQL sees). Backed by a baked records.json.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import duckdb

TOKEN = os.environ.get("LOGFIRE_TOKEN", "test-token-acme-eval")
RECORDS = os.environ.get("LOGFIRE_RECORDS", "/data/records.json")
PORT = int(os.environ.get("LOGFIRE_PORT", "80"))

_con = duckdb.connect(":memory:")
_con.execute(f"CREATE TABLE base_records AS SELECT * FROM read_json_auto('{RECORDS}', maximum_object_size=20000000)")
_N = _con.execute("SELECT count(*) FROM base_records").fetchone()[0]
print(f"[logfire-clone] loaded {_N} records from {RECORDS}", flush=True)


def _ts_literal(s: str) -> str:
    """Validate an ISO timestamp and return a DuckDB TIMESTAMP literal body (UTC, naive).
    Validation also makes it safe to inline (CREATE VIEW can't take bind params)."""
    dt = datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")


def _run(sql: str, mn: str, mx: str | None, limit: int):
    s = sql.lstrip()
    if not (s[:6].lower() == "select" or s[:4].lower() == "with"):
        raise ValueError("only SELECT/WITH queries are allowed")  # read-only, like Logfire
    lo, hi = _ts_literal(mn), _ts_literal(mx or "2100-01-01T00:00:00Z")
    # scope `records` to [min,max] like Logfire (start_timestamp is VARCHAR ISO -> cast), then run the agent's SQL
    _con.execute(
        "CREATE OR REPLACE TEMP VIEW records AS SELECT * FROM base_records WHERE "
        f"CAST(replace(start_timestamp,'Z','') AS TIMESTAMP) >= TIMESTAMP '{lo}' AND "
        f"CAST(replace(start_timestamp,'Z','') AS TIMESTAMP) <= TIMESTAMP '{hi}'"
    )
    cur = _con.execute(f"SELECT * FROM ({sql}) AS _q LIMIT {int(limit)}")
    cols = [d[0] for d in cur.description]
    types = [str(d[1]) for d in cur.description]
    data = [dict(zip(cols, row)) for row in cur.fetchall()]
    return {"schema": {"fields": [{"name": c, "data_type": t} for c, t in zip(cols, types)]}, "data": data}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code: int, obj):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "records": _N})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") not in ("/v2/query", "/v1/query"):
            self._send(404, {"error": "not found"})
            return
        scheme, _, token = self.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or token != TOKEN:
            self._send(401, {"detail": "Invalid read token"})
            return
        n = int(self.headers.get("Content-Length", "0") or "0")
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            self._send(400, {"error": "invalid json"})
            return
        sql, mn = body.get("sql"), body.get("min_timestamp")
        if not sql or not mn:
            self._send(400, {"error": "sql and min_timestamp are required"})
            return
        try:
            self._send(200, _run(sql, mn, body.get("max_timestamp"), body.get("limit") or 10000))
        except Exception as e:
            self._send(400, {"error": "invalid query", "details": str(e)[:300]})


def main():
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
