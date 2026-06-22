"""Read-only file-seed clones (gauge / sentry / github) — load a bundled sample + view()."""
from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def _load_sample(app_id: str):
    bases = client.get(f"/api/{app_id}/bases").json()
    assert bases, f"{app_id} has no bundled sample"
    r = client.post(f"/api/{app_id}/load", json={"base_id": bases[0]["id"]})
    assert r.status_code == 200, r.text
    return client.get(f"/api/{app_id}/view").json()


def test_all_three_registered_active():
    apps = {a["id"]: a for a in client.get("/api/apps").json()}
    for cid in ("gauge", "sentry", "github"):
        assert apps[cid]["status"] == "active" and apps[cid]["ui_module"] == cid


def test_view_requires_session():
    assert client.get("/api/gauge/view").status_code == 400


def test_gauge_parses_logs_dashboards_datasources():
    v = _load_sample("gauge")
    assert v["stats"]["datasources"] == 2 and v["stats"]["dashboards"] == 1
    assert v["stats"]["log_lines"] == 3
    stream = next(iter(v["log_queries"]))
    assert "service" in stream  # a LogQL selector
    assert any("read timeout" in ln["line"] for ln in v["log_queries"][stream])


def test_sentry_parses_issues_and_stacktrace():
    v = _load_sample("sentry")
    assert v["stats"]["issues"] == 2 and v["stats"]["events"] == 2
    iss = v["issues"][0]
    assert iss["events"][0]["exception"]["stacktrace"][0]["filename"].endswith(".py")


def test_github_parses_seed_script():
    v = _load_sample("github")
    assert v["stats"] == {"repos": 1, "issues": 2, "prs": 1, "reviews": 2, "comments": 0}
    assert v["prs"][0]["head"] == "fix/read-timeout" and v["prs"][0]["base"] == "main"
    states = {r["state"] for r in v["reviews"]}
    assert states == {"changes_requested", "approved"}
    assert "gh repo create" in v["raw"]
