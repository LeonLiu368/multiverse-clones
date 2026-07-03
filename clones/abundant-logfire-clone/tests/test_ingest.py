"""LIVE INGEST (env-gated): POST /v1/ingest (native records) + POST /v1/traces
(OTLP/HTTP JSON, the otel-collector `otlphttp` exporter payload with encoding: json).

Runs its own gateway instance (same in-process pattern as conftest) with a
full-22-column corpus and LOGFIRE_WRITE_TOKEN set, so struct->JSON `attributes`
normalization and every mapped column are exercised end-to-end: ingest -> /v2/query.
"""
import importlib
import json
import os
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request

import pytest

READ_TOKEN = "test-token-acme-eval"
WRITE_TOKEN = "test-write-token-acme-eval"
MIN_TS = "2026-06-24T00:00:00Z"

# Two full-schema seed records (all 22 corpus columns, attributes as an object so
# DuckDB infers STRUCT and the ingest-mode JSON normalization path is exercised).
SEED = [
    {"start_timestamp": "2026-06-24T22:34:00.751318Z", "end_timestamp": "2026-06-24T22:34:01.140896Z",
     "duration": 0.389578, "trace_id": "019efbc4d2af61ee60c2fc387882a9ef", "span_id": "05e52fccf06f5374",
     "parent_span_id": None, "kind": "span", "level": 13, "span_name": "GET /tasks/{task_id}",
     "message": "GET /tasks/d0ae3ede", "is_exception": True,
     "exception_type": "fastapi.exceptions.HTTPException", "exception_message": "404: Task d0ae3ede not found",
     "exception_stacktrace": "Traceback ...", "attributes": {"http.method": "GET"},
     "service_name": "oddish-backend", "deployment_environment": "production",
     "http_response_status_code": 404, "url_path": "/tasks/d0ae3ede", "url_query": "",
     "http_route": "/tasks/{task_id}", "http_method": "GET"},
    {"start_timestamp": "2026-06-24T22:35:00.000000Z", "end_timestamp": "2026-06-24T22:35:00.100000Z",
     "duration": 0.1, "trace_id": "019efbc4d2af61ee60c2fc387882a9f0", "span_id": "05e52fccf06f5375",
     "parent_span_id": None, "kind": "span", "level": 9, "span_name": "worker tick",
     "message": "worker tick", "is_exception": False, "exception_type": None, "exception_message": None,
     "exception_stacktrace": None, "attributes": {"tick": 1}, "service_name": "oddish-worker",
     "deployment_environment": "production", "http_response_status_code": None, "url_path": None,
     "url_query": None, "http_route": None, "http_method": None},
]


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def ingest_gw():
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(SEED, f)
    f.close()
    port = _free_port()
    os.environ["LOGFIRE_RECORDS"] = f.name
    os.environ["LOGFIRE_PORT"] = str(port)
    os.environ["LOGFIRE_TOKEN"] = READ_TOKEN
    os.environ["LOGFIRE_WRITE_TOKEN"] = WRITE_TOKEN
    import logfire_clone.server as server
    importlib.reload(server)
    t = threading.Thread(target=lambda: server.ThreadingHTTPServer(
        ("127.0.0.1", port), server.Handler).serve_forever(), daemon=True)
    t.start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(url + "/health", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    os.environ["LOGFIRE_URL"] = url
    yield {"url": url, "server": server}
    os.environ.pop("LOGFIRE_WRITE_TOKEN", None)


def _post(url, path, token, body):
    req = urllib.request.Request(
        url + path, data=json.dumps(body).encode(),
        headers=({"Authorization": f"Bearer {token}"} if token is not None else {}),
        method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _query(gw, sql):
    code, body = _post(gw["url"], "/v2/query", READ_TOKEN,
                       {"sql": sql, "min_timestamp": MIN_TS})
    assert code == 200, body
    return body["data"]


# ---- native ingest: write -> immediately visible on the read path ----
def test_native_ingest_roundtrip(ingest_gw):
    rec = {"start_timestamp": "2026-06-24T23:00:00Z", "span_name": "queue poll",
           "message": "queue poll", "service_name": "oddish-worker",
           "is_exception": True, "exception_type": "asyncpg.exceptions.DeadlockDetectedError",
           "exception_message": "deadlock detected", "attributes": {"queue": "default"}}
    code, body = _post(ingest_gw["url"], "/v1/ingest", WRITE_TOKEN, {"records": [rec]})
    assert code == 200 and body["inserted"] == 1
    rows = _query(ingest_gw, "SELECT * FROM records WHERE span_name = 'queue poll'")
    assert len(rows) == 1
    r = rows[0]
    assert r["exception_type"] == "asyncpg.exceptions.DeadlockDetectedError"
    assert r["service_name"] == "oddish-worker"
    assert json.loads(r["attributes"]) == {"queue": "default"}
    # missing optional fields land as NULL
    assert r["trace_id"] is None and r["http_response_status_code"] is None


def test_native_ingest_visible_in_health_count(ingest_gw):
    with urllib.request.urlopen(ingest_gw["url"] + "/health") as resp:
        before = json.load(resp)["records"]
    code, _ = _post(ingest_gw["url"], "/v1/ingest", WRITE_TOKEN, {"records": [
        {"start_timestamp": "2026-06-24T23:01:00Z", "span_name": "health bump"}]})
    assert code == 200
    with urllib.request.urlopen(ingest_gw["url"] + "/health") as resp:
        assert json.load(resp)["records"] == before + 1


# ---- OTLP/HTTP JSON: a realistic collector-shaped payload, 2 spans ----
def _otlp_payload():
    return {
        "resourceSpans": [{
            "resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": "oddish-backend"}},
                {"key": "deployment.environment.name", "value": {"stringValue": "production"}},
                {"key": "telemetry.sdk.language", "value": {"stringValue": "python"}},
            ]},
            "scopeSpans": [{
                "scope": {"name": "opentelemetry.instrumentation.fastapi", "version": "0.45b0"},
                "spans": [
                    {  # OK http server span
                        "traceId": "5b8efff798038103d269b633813fc60c",
                        "spanId": "eee19b7ec3c1b174",
                        "parentSpanId": "eee19b7ec3c1b173",
                        "name": "GET /dashboard",
                        "kind": 2,
                        "startTimeUnixNano": "1782340500000000000",
                        "endTimeUnixNano": "1782340500250000000",
                        "attributes": [
                            {"key": "http.request.method", "value": {"stringValue": "GET"}},
                            {"key": "http.response.status_code", "value": {"intValue": "200"}},
                            {"key": "url.path", "value": {"stringValue": "/dashboard"}},
                            {"key": "http.route", "value": {"stringValue": "/dashboard"}},
                            {"key": "client.address", "value": {"stringValue": "35.90.39.17"}},
                            {"key": "retry.count", "value": {"intValue": "0"}},
                        ],
                        "status": {},
                    },
                    {  # ERROR span with an exception event
                        "traceId": "5b8efff798038103d269b633813fc60c",
                        "spanId": "eee19b7ec3c1b175",
                        "name": "release queue slot",
                        "kind": 1,
                        "startTimeUnixNano": "1782340501000000000",
                        "endTimeUnixNano": "1782340501050000000",
                        "attributes": [
                            {"key": "db.system", "value": {"stringValue": "postgresql"}},
                        ],
                        "events": [{
                            "timeUnixNano": "1782340501040000000",
                            "name": "exception",
                            "attributes": [
                                {"key": "exception.type",
                                 "value": {"stringValue": "asyncpg.exceptions.UndefinedColumnError"}},
                                {"key": "exception.message",
                                 "value": {"stringValue": 'column "locked_at" of relation "queue_slots" does not exist'}},
                                {"key": "exception.stacktrace",
                                 "value": {"stringValue": "Traceback (most recent call last): ..."}},
                            ],
                        }],
                        "status": {"code": 2, "message": "UndefinedColumnError"},
                    },
                ],
            }],
        }]
    }


def test_otlp_traces_mapping(ingest_gw):
    code, body = _post(ingest_gw["url"], "/v1/traces", WRITE_TOKEN, _otlp_payload())
    assert code == 200 and body["inserted"] == 2

    ok = _query(ingest_gw, "SELECT * FROM records WHERE span_id = 'eee19b7ec3c1b174'")[0]
    assert ok["trace_id"] == "5b8efff798038103d269b633813fc60c"
    assert ok["parent_span_id"] == "eee19b7ec3c1b173"
    assert ok["kind"] == "server"
    assert ok["span_name"] == "GET /dashboard" and ok["message"] == "GET /dashboard"
    assert str(ok["start_timestamp"]).startswith("2026-06-24") \
        and str(ok["end_timestamp"]).startswith("2026-06-24")
    assert abs(float(ok["duration"]) - 0.25) < 1e-9
    assert ok["http_response_status_code"] == 200 and ok["url_path"] == "/dashboard"
    assert ok["http_method"] == "GET" and ok["http_route"] == "/dashboard"
    assert ok["service_name"] == "oddish-backend"
    assert ok["deployment_environment"] == "production"
    assert ok["is_exception"] is False and ok["exception_type"] is None
    # consumed semconv attrs moved to columns; the rest live in the attributes JSON
    attrs = json.loads(ok["attributes"])
    assert attrs == {"client.address": "35.90.39.17", "retry.count": 0}

    err = _query(ingest_gw, "SELECT * FROM records WHERE span_id = 'eee19b7ec3c1b175'")[0]
    assert err["is_exception"] is True
    assert err["exception_type"] == "asyncpg.exceptions.UndefinedColumnError"
    assert 'column "locked_at"' in err["exception_message"]
    assert err["kind"] == "internal" and err["parent_span_id"] is None
    assert abs(float(err["duration"]) - 0.05) < 1e-9
    assert json.loads(err["attributes"]) == {"db.system": "postgresql"}


def test_otlp_rows_queryable_with_seed_corpus(ingest_gw):
    # ingested + baked rows aggregate together through the same records view
    rows = _query(ingest_gw, "SELECT service_name, count(*) n FROM records "
                             "WHERE service_name = 'oddish-backend' GROUP BY 1")
    assert rows and rows[0]["n"] >= 2  # 1 seeded + >=1 ingested


# ---- auth / env gating ----
def test_ingest_wrong_token_401(ingest_gw):
    for path in ("/v1/ingest", "/v1/traces"):
        code, body = _post(ingest_gw["url"], path, "wrong-token", {"records": []})
        assert code == 401 and body == {"detail": "Invalid write token"}


def test_ingest_missing_token_401(ingest_gw):
    code, body = _post(ingest_gw["url"], "/v1/ingest", None, {"records": []})
    assert code == 401 and body == {"detail": "Invalid write token"}


def test_read_token_not_valid_for_ingest(ingest_gw):
    code, body = _post(ingest_gw["url"], "/v1/ingest", READ_TOKEN, {"records": []})
    assert code == 401 and body == {"detail": "Invalid write token"}


def test_ingest_404_when_env_unset(ingest_gw):
    server = ingest_gw["server"]
    saved = server.WRITE_TOKEN
    server.WRITE_TOKEN = None  # feature off -> endpoints don't exist
    try:
        for path in ("/v1/ingest", "/v1/traces"):
            code, body = _post(ingest_gw["url"], path, WRITE_TOKEN, {"records": []})
            assert code == 404 and body == {"error": "not found"}
    finally:
        server.WRITE_TOKEN = saved


# ---- bad payloads -> 400, batch rejected atomically ----
def test_native_ingest_unknown_field_400(ingest_gw):
    code, body = _post(ingest_gw["url"], "/v1/ingest", WRITE_TOKEN, {"records": [
        {"start_timestamp": "2026-06-24T23:02:00Z", "span_nam": "typo", "bogus": 1}]})
    assert code == 400 and body["error"] == "invalid records"
    assert any("unknown fields" in d and "bogus" in d for d in body["details"])


def test_native_ingest_wrong_type_400(ingest_gw):
    code, body = _post(ingest_gw["url"], "/v1/ingest", WRITE_TOKEN, {"records": [
        {"start_timestamp": "2026-06-24T23:02:00Z", "http_response_status_code": "five hundred"}]})
    assert code == 400 and body["error"] == "invalid records"


def test_native_ingest_not_a_list_400(ingest_gw):
    code, body = _post(ingest_gw["url"], "/v1/ingest", WRITE_TOKEN, {"records": {"nope": 1}})
    assert code == 400


def test_otlp_malformed_400_and_atomic(ingest_gw):
    with urllib.request.urlopen(ingest_gw["url"] + "/health") as resp:
        before = json.load(resp)["records"]
    payload = _otlp_payload()
    del payload["resourceSpans"][0]["scopeSpans"][0]["spans"][1]["spanId"]  # 2nd span invalid
    code, body = _post(ingest_gw["url"], "/v1/traces", WRITE_TOKEN, payload)
    assert code == 400 and body["error"] == "invalid otlp payload" and "spanId" in body["details"]
    with urllib.request.urlopen(ingest_gw["url"] + "/health") as resp:
        assert json.load(resp)["records"] == before  # whole batch rejected, no partial rows


def test_otlp_not_otlp_400(ingest_gw):
    code, body = _post(ingest_gw["url"], "/v1/traces", WRITE_TOKEN, {"records": []})
    assert code == 400 and body["error"] == "invalid otlp payload"


# ---- reads during ingest don't error (shared connection is lock-guarded) ----
def test_concurrent_reads_during_ingest(ingest_gw):
    errors = []

    def reader():
        for _ in range(20):
            try:
                _query(ingest_gw, "SELECT count(*) n FROM records")
            except Exception as e:  # pragma: no cover
                errors.append(e)

    def writer(i):
        for j in range(10):
            code, _ = _post(ingest_gw["url"], "/v1/ingest", WRITE_TOKEN, {"records": [
                {"start_timestamp": "2026-06-24T23:30:00Z", "span_name": f"burst {i}-{j}"}]})
            if code != 200:  # pragma: no cover
                errors.append(RuntimeError(f"ingest {code}"))

    threads = [threading.Thread(target=reader) for _ in range(3)] + \
              [threading.Thread(target=writer, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    rows = _query(ingest_gw, "SELECT count(*) n FROM records WHERE span_name LIKE 'burst %'")
    assert rows[0]["n"] == 20
