"""Thin Logfire clone — serves Logfire's Query API (`POST /v2/query`: SQL over a `records`
table) backed by DuckDB, so an agent debugs the way an Abundant SWE actually does:
`SELECT … FROM records WHERE …`, with real traces/spans/exceptions/http columns — unlike
the Grafana/Loki flattening. Read-token Bearer auth; offline; data sealed behind the API.

Faithful surface: same endpoint, same `{schema, data}` response, same required body
(`sql` + `min_timestamp`, optional `max_timestamp`/`limit`), same time-window scoping
(min/max bound which records the SQL sees). Backed by a baked records.json.

LIVE INGEST (env-gated on LOGFIRE_WRITE_TOKEN — real Logfire is an OTLP ingest backend):
`POST /v1/traces` accepts OTLP/HTTP JSON (the otel-collector `otlphttp` exporter with
`encoding: json`) and maps each span to one `records` row; `POST /v1/ingest` accepts
native records-schema rows. Both require `Authorization: Bearer $LOGFIRE_WRITE_TOKEN`
and INSERT into the live DuckDB table, so `/v2/query` sees rows immediately. When the
env var is unset the endpoints 404 and the clone is byte-identical to the read-only one.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import duckdb

TOKEN = os.environ.get("LOGFIRE_TOKEN", "test-token-acme-eval")
# LIVE INGEST is env-gated: when LOGFIRE_WRITE_TOKEN is unset the ingest endpoints
# (/v1/ingest, /v1/traces) return 404 and the clone behaves exactly as before.
WRITE_TOKEN = os.environ.get("LOGFIRE_WRITE_TOKEN")
RECORDS = os.environ.get("LOGFIRE_RECORDS", "/data/records.json")
PORT = int(os.environ.get("LOGFIRE_PORT", "80"))

def _records_path() -> str:
    """Resolve the records file, transparently gunzipping a `.gz` corpus to a temp file.
    The `:prod-v1` image bakes a gzipped corpus; `:empty` mounts a plain records.json."""
    import gzip
    import shutil
    import tempfile

    p = RECORDS
    if p.endswith(".gz") or (not os.path.exists(p) and os.path.exists(p + ".gz")):
        src = p if p.endswith(".gz") else p + ".gz"
        out = tempfile.NamedTemporaryFile(prefix="logfire_records_", suffix=".json", delete=False)
        with gzip.open(src, "rb") as f:
            shutil.copyfileobj(f, out)
        out.close()
        return out.name
    return p


_RECORDS_FILE = _records_path()
_con = duckdb.connect(":memory:")
# The server is a ThreadingHTTPServer (one thread per request) sharing this single
# module-global connection, so every _con access is serialized through _LOCK.
_LOCK = threading.Lock()
_con.execute(f"CREATE TABLE base_records AS SELECT * FROM read_json_auto('{_RECORDS_FILE}', maximum_object_size=20000000)")
_N = _con.execute("SELECT count(*) FROM base_records").fetchone()[0]
print(f"[logfire-clone] loaded {_N} records from {_RECORDS_FILE}", flush=True)

# ---------------------------------------------------------------------------
# LIVE INGEST (env-gated on LOGFIRE_WRITE_TOKEN)
# ---------------------------------------------------------------------------
# Canonical `records` schema — one row per span, the 22 columns of the corpus.
_CANON = [
    ("start_timestamp", "VARCHAR"), ("end_timestamp", "VARCHAR"), ("duration", "DOUBLE"),
    ("trace_id", "VARCHAR"), ("span_id", "VARCHAR"), ("parent_span_id", "VARCHAR"),
    ("kind", "VARCHAR"), ("level", "BIGINT"), ("span_name", "VARCHAR"), ("message", "VARCHAR"),
    ("is_exception", "BOOLEAN"), ("exception_type", "VARCHAR"), ("exception_message", "VARCHAR"),
    ("exception_stacktrace", "VARCHAR"), ("attributes", "JSON"), ("service_name", "VARCHAR"),
    ("deployment_environment", "VARCHAR"), ("http_response_status_code", "BIGINT"),
    ("url_path", "VARCHAR"), ("url_query", "VARCHAR"), ("http_route", "VARCHAR"),
    ("http_method", "VARCHAR"),
]
_CANON_NAMES = {c for c, _ in _CANON}
_PYTYPES = {  # loose python-type validation for native ingest
    "duration": (int, float), "level": int, "is_exception": bool,
    "http_response_status_code": int, "attributes": (dict, str),
}
_COLTYPES: dict = {}


def _prep_ingest():
    """Make the live table insert-ready: add any canonical column the loaded corpus
    lacks, and normalize `attributes` (inferred as STRUCT from a baked corpus) to JSON
    so arbitrary ingested attribute sets fit. Only runs when ingest is enabled."""
    global _COLTYPES
    with _LOCK:
        cols = {r[0]: r[1] for r in _con.execute("DESCRIBE base_records").fetchall()}
        for name, typ in _CANON:
            if name not in cols:
                _con.execute(f'ALTER TABLE base_records ADD COLUMN "{name}" {typ}')
                cols[name] = typ
        replacements = []
        for name, typ in _CANON:
            actual = cols[name].upper()
            if name == "attributes":
                if not (actual.startswith("JSON") or actual.startswith("VARCHAR")):
                    replacements.append('to_json(attributes) AS attributes')  # STRUCT -> JSON
                    cols[name] = "JSON"
            elif actual.startswith("JSON"):
                # read_json_auto infers all-NULL columns as JSON; pin the canonical type
                replacements.append(f'CAST("{name}" AS {typ}) AS "{name}"')
                cols[name] = typ
        if replacements:
            _con.execute("CREATE OR REPLACE TABLE base_records AS "
                         f"SELECT * REPLACE ({', '.join(replacements)}) FROM base_records")
        _COLTYPES = cols


if WRITE_TOKEN is not None:
    _prep_ingest()
    print(f"[logfire-clone] live ingest enabled (/v1/ingest, /v1/traces)", flush=True)


def _validate_records(recs):
    """Native-ingest validation: rows must be objects in the records schema; unknown
    fields and grossly wrong types are rejected with per-record details."""
    if not isinstance(recs, list) or not recs or not all(isinstance(r, dict) for r in recs):
        return ["'records' must be a non-empty list of objects"]
    errors = []
    for i, r in enumerate(recs):
        unknown = sorted(set(r) - _CANON_NAMES)
        if unknown:
            errors.append(f"record {i}: unknown fields {unknown}")
        for k, v in r.items():
            if v is None or k in unknown:
                continue
            if k in _PYTYPES:
                if isinstance(v, bool) and _PYTYPES[k] is not bool:
                    errors.append(f"record {i}: field '{k}' has wrong type bool")
                elif not isinstance(v, _PYTYPES[k]):
                    errors.append(f"record {i}: field '{k}' has wrong type {type(v).__name__}")
            elif k in _CANON_NAMES and not isinstance(v, str):
                errors.append(f"record {i}: field '{k}' must be a string")
        for k in ("start_timestamp", "end_timestamp"):
            v = r.get(k)
            if isinstance(v, str):
                try:
                    _ts_literal(v)
                except Exception:
                    errors.append(f"record {i}: field '{k}' is not an ISO-8601 timestamp")
    return errors


def _coerce(name, v):
    if v is None:
        return None
    t = _COLTYPES.get(name, "VARCHAR").upper()
    if "TIMESTAMP" in t and isinstance(v, str):
        return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    if name == "attributes" and isinstance(v, (dict, list)):
        return json.dumps(v)
    return v


def _insert_rows(rows):
    """INSERT validated canonical rows into the live table (missing fields -> NULL).
    Whole batch or nothing; guarded by _LOCK against concurrent reads/ingests."""
    global _N
    cols = [c for c, _ in _CANON]
    params = [[_coerce(c, r.get(c)) for c in cols] for r in rows]
    q = f"INSERT INTO base_records ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})"
    with _LOCK:
        _con.execute("BEGIN TRANSACTION")
        try:
            _con.executemany(q, params)
            _con.execute("COMMIT")
        except Exception:
            _con.execute("ROLLBACK")
            raise
        _N = _con.execute("SELECT count(*) FROM base_records").fetchone()[0]


# ---- OTLP/HTTP JSON (POST /v1/traces — what the collector's otlphttp exporter emits
# with encoding: json). Each span maps to one `records` row. ----
_KIND = {0: "internal", 1: "internal", 2: "server", 3: "client", 4: "producer", 5: "consumer"}
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _otlp_kind(v):
    if isinstance(v, str) and v.startswith("SPAN_KIND_"):
        return v[len("SPAN_KIND_"):].lower().replace("unspecified", "internal")
    return _KIND.get(int(v or 0), "internal")


def _unwrap_value(v):
    """OTLP JSON AnyValue -> python (intValue arrives as a string per proto3 JSON)."""
    if not isinstance(v, dict):
        raise ValueError("attribute value must be an OTLP AnyValue object")
    if "stringValue" in v:
        return v["stringValue"]
    if "intValue" in v:
        return int(v["intValue"])
    if "doubleValue" in v:
        return float(v["doubleValue"])
    if "boolValue" in v:
        return bool(v["boolValue"])
    if "arrayValue" in v:
        return [_unwrap_value(x) for x in v["arrayValue"].get("values", [])]
    if "kvlistValue" in v:
        return _unwrap_kvs(v["kvlistValue"].get("values", []))
    if "bytesValue" in v:
        return v["bytesValue"]
    return None


def _unwrap_kvs(kvs):
    if not isinstance(kvs, list):
        raise ValueError("attributes must be a list of {key, value}")
    return {kv["key"]: _unwrap_value(kv.get("value", {})) for kv in kvs}


def _iso(ns: int) -> str:
    return (_EPOCH + timedelta(microseconds=ns // 1000)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _span_to_row(sp, service_name, deployment_environment):
    if not isinstance(sp, dict):
        raise ValueError("span must be an object")
    for req in ("traceId", "spanId", "name", "startTimeUnixNano", "endTimeUnixNano"):
        if not sp.get(req):
            raise ValueError(f"span missing required field '{req}'")
    start_ns, end_ns = int(sp["startTimeUnixNano"]), int(sp["endTimeUnixNano"])
    attrs = _unwrap_kvs(sp.get("attributes", []))

    # status/events -> exception columns
    status = sp.get("status") or {}
    code = status.get("code", 0)
    is_error = code == 2 or code == "STATUS_CODE_ERROR"
    exc_type = exc_msg = exc_stack = None
    for ev in sp.get("events", []) or []:
        if isinstance(ev, dict) and ev.get("name") == "exception":
            eattrs = _unwrap_kvs(ev.get("attributes", []))
            exc_type = eattrs.get("exception.type")
            exc_msg = eattrs.get("exception.message")
            exc_stack = eattrs.get("exception.stacktrace")
            is_error = True
            break
    if is_error and exc_msg is None:
        exc_msg = status.get("message") or None

    # http/url semconv attributes -> dedicated columns (new + legacy names)
    def _take(*names):
        out = None
        for n in names:
            v = attrs.pop(n, None)
            if out is None:
                out = v
        return out

    http_status = _take("http.response.status_code", "http.status_code")
    url_path, url_query = _take("url.path"), _take("url.query")
    target = _take("http.target")
    if url_path is None and isinstance(target, str):
        url_path, _, q = target.partition("?")
        url_query = url_query if url_query is not None else (q or None)
    http_route = _take("http.route")
    http_method = _take("http.request.method", "http.method")

    name = sp["name"]
    message = f"{http_method} {url_path}" if http_method and url_path else name
    return {
        "start_timestamp": _iso(start_ns), "end_timestamp": _iso(end_ns),
        "duration": (end_ns - start_ns) / 1e9,
        "trace_id": sp["traceId"], "span_id": sp["spanId"],
        "parent_span_id": sp.get("parentSpanId") or None,
        "kind": _otlp_kind(sp.get("kind", 0)), "level": 17 if is_error else 9,
        "span_name": name, "message": message,
        "is_exception": is_error, "exception_type": exc_type,
        "exception_message": exc_msg, "exception_stacktrace": exc_stack,
        "attributes": json.dumps(attrs), "service_name": service_name,
        "deployment_environment": deployment_environment,
        "http_response_status_code": int(http_status) if http_status is not None else None,
        "url_path": url_path, "url_query": url_query,
        "http_route": http_route, "http_method": http_method,
    }


def _otlp_to_rows(payload):
    """resourceSpans[].scopeSpans[].spans[] -> canonical rows. Malformed structure
    rejects the whole batch (no partial success)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("resourceSpans"), list):
        raise ValueError("payload must contain a 'resourceSpans' list")
    rows = []
    for rs in payload["resourceSpans"]:
        if not isinstance(rs, dict):
            raise ValueError("resourceSpans entries must be objects")
        res_attrs = _unwrap_kvs((rs.get("resource") or {}).get("attributes", []))
        service = res_attrs.get("service.name") or "unknown_service"
        env = res_attrs.get("deployment.environment.name") or res_attrs.get("deployment.environment")
        for ss in rs.get("scopeSpans", []) or []:
            if not isinstance(ss, dict):
                raise ValueError("scopeSpans entries must be objects")
            for sp in ss.get("spans", []) or []:
                rows.append(_span_to_row(sp, service, env))
    if not rows:
        raise ValueError("no spans in payload")
    return rows


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
    # start_timestamp may be inferred as VARCHAR or TIMESTAMP depending on the duckdb version;
    # CAST->VARCHAR->strip Z->TIMESTAMP handles both uniformly.
    col = "CAST(replace(CAST(start_timestamp AS VARCHAR),'Z','') AS TIMESTAMP)"
    with _LOCK:  # serialize with ingest INSERTs (shared module-global connection)
        _con.execute(
            "CREATE OR REPLACE TEMP VIEW records AS SELECT * FROM base_records WHERE "
            f"{col} >= TIMESTAMP '{lo}' AND {col} <= TIMESTAMP '{hi}'"
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

    def _read_body_json(self):
        n = int(self.headers.get("Content-Length", "0") or "0")
        return json.loads(self.rfile.read(n) or b"{}")

    def _do_ingest(self, path: str):
        """POST /v1/ingest (native records) and POST /v1/traces (OTLP/HTTP JSON).
        Env-gated: 404 unless LOGFIRE_WRITE_TOKEN is set; then Bearer write-token auth."""
        if WRITE_TOKEN is None:
            self._send(404, {"error": "not found"})
            return
        scheme, _, token = self.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or token != WRITE_TOKEN:
            self._send(401, {"detail": "Invalid write token"})
            return
        try:
            body = self._read_body_json()
        except Exception:
            self._send(400, {"error": "invalid json"})
            return
        if path == "/v1/ingest":
            if not isinstance(body, dict) or "records" not in body:
                self._send(400, {"error": "body must be {\"records\": [...]}"})
                return
            rows = body["records"]
            errors = _validate_records(rows)
            if errors:
                self._send(400, {"error": "invalid records", "details": errors[:20]})
                return
        else:  # /v1/traces — OTLP/HTTP JSON; malformed structure rejects the whole batch
            try:
                rows = _otlp_to_rows(body)
            except (ValueError, KeyError, TypeError, OverflowError) as e:
                self._send(400, {"error": "invalid otlp payload", "details": str(e)[:300]})
                return
        try:
            _insert_rows(rows)
        except Exception as e:
            self._send(400, {"error": "invalid records", "details": str(e)[:300]})
            return
        self._send(200, {"inserted": len(rows), "records": _N})

    def do_POST(self):
        path = self.path.rstrip("/")
        if path in ("/v1/ingest", "/v1/traces"):
            self._do_ingest(path)
            return
        if path not in ("/v2/query", "/v1/query"):
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
