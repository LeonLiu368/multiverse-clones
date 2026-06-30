"""HTTP API: every endpoint, happy + error paths, real envelopes."""
import json
import urllib.error
import urllib.request


def _post(url, token, body):
    req = urllib.request.Request(
        url + "/v2/query", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_health(gateway):
    with urllib.request.urlopen(gateway["url"] + "/health") as r:
        body = json.load(r)
    assert r.status == 200 and body["ok"] is True and body["records"] == 4


def test_query_happy_envelope(gateway):
    code, body = _post(gateway["url"], gateway["token"],
                       {"sql": "SELECT * FROM records", "min_timestamp": gateway["min"]})
    assert code == 200
    assert "schema" in body and "fields" in body["schema"] and "data" in body
    names = {f["name"] for f in body["schema"]["fields"]}
    assert {"exception_type", "service_name", "start_timestamp"} <= names


def test_query_group_by_filter(gateway):
    code, body = _post(gateway["url"], gateway["token"], {
        "sql": "SELECT exception_type, count(*) n FROM records WHERE exception_type IS NOT NULL GROUP BY 1 ORDER BY n DESC",
        "min_timestamp": gateway["min"]})
    assert code == 200
    rows = {r["exception_type"]: r["n"] for r in body["data"]}
    assert rows["asyncpg.exceptions.UndefinedColumnError"] == 2


def test_time_window_scoping(gateway):
    # exclude the 2026-06-25 frontend record with a max_timestamp before it
    code, body = _post(gateway["url"], gateway["token"], {
        "sql": "SELECT count(*) n FROM records", "min_timestamp": gateway["min"],
        "max_timestamp": "2026-06-24T23:00:00Z"})
    assert code == 200 and body["data"][0]["n"] == 3


def test_auth_401(gateway):
    code, body = _post(gateway["url"], "wrong-token",
                       {"sql": "SELECT 1", "min_timestamp": gateway["min"]})
    assert code == 401 and body == {"detail": "Invalid read token"}


def test_readonly_400(gateway):
    code, body = _post(gateway["url"], gateway["token"],
                       {"sql": "DROP TABLE records", "min_timestamp": gateway["min"]})
    assert code == 400 and "only SELECT/WITH" in body["details"]


def test_missing_fields_400(gateway):
    code, body = _post(gateway["url"], gateway["token"], {"sql": "SELECT 1"})
    assert code == 400 and body["error"] == "sql and min_timestamp are required"


def test_bad_column_400(gateway):
    code, body = _post(gateway["url"], gateway["token"],
                       {"sql": "SELECT nope FROM records", "min_timestamp": gateway["min"]})
    assert code == 400 and body["error"] == "invalid query"


def test_unknown_path_404(gateway):
    try:
        urllib.request.urlopen(gateway["url"] + "/nope")
        assert False
    except urllib.error.HTTPError as e:
        assert e.code == 404
