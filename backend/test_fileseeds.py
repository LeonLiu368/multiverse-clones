"""Read-only file-seed clones (gauge / sentry / github) — load a bundled sample + view()."""
import pytest
from fastapi.testclient import TestClient

import dockerutil
from app import app

client = TestClient(app)
FIGMA_PROD = "ghcr.io/abundant-ai/figma-service:prod-v1"
GAUGE_IMG = "ghcr.io/abundant-ai/gauge-gateway:apex-paperless"


def _load_sample(app_id: str):
    bases = client.get(f"/api/{app_id}/bases").json()
    # prefer the bundled file sample (figma also lists docker images, which come first)
    sample = next((b for b in bases if b["kind"] != "image"), None)
    assert sample, f"{app_id} has no bundled sample"
    r = client.post(f"/api/{app_id}/load", json={"base_id": sample["id"]})
    assert r.status_code == 200, r.text
    return client.get(f"/api/{app_id}/view").json()


def test_fileseed_clones_registered_active():
    apps = {a["id"]: a for a in client.get("/api/apps").json()}
    for cid in ("figma", "gauge", "sentry", "github", "logfire", "gworkspace", "notion", "aws"):
        assert apps[cid]["status"] == "active" and apps[cid]["ui_module"] == cid


def test_view_requires_session():
    assert client.get("/api/gauge/view").status_code == 400


def test_gauge_parses_logs_metrics_dashboards_datasources():
    v = _load_sample("gauge")
    assert v["stats"]["datasources"] == 2 and v["stats"]["dashboards"] == 1
    # Loki logs
    assert v["stats"]["log_streams"] >= 1 and v["stats"]["log_lines"] >= 1
    stream = next(iter(v["log_queries"]))
    assert "service" in stream and isinstance(v["log_queries"][stream], list)
    # Prometheus metrics — each query -> series with [ts, value] points
    assert v["stats"]["metric_queries"] >= 1
    expr = next(iter(v["metric_queries"]))
    series = v["metric_queries"][expr]
    assert series and "metric" in series[0] and len(series[0]["values"]) >= 1


def test_gauge_overlay_merges_streams_and_datasources():
    import os

    samples = os.path.join(os.path.dirname(__file__), "..", "samples")
    base = next(b for b in client.get("/api/gauge/bases").json() if b["kind"] != "image")["id"]
    with open(os.path.join(samples, "gauge.overlay.json"), "rb") as fh:
        r = client.post("/api/gauge/load_overlay", data={"base_id": base},
                        files={"overlay": ("gauge.overlay.json", fh, "application/json")})
    assert r.status_code == 200, r.text
    v = client.get("/api/gauge/view").json()
    assert v["stats"]["datasources"] == 3  # base 2 + overlay loki
    assert '{service="overlay-svc"}' in v["log_queries"]  # new stream from the overlay
    web = v["log_queries"]['{service="web"}']
    assert any(ln.get("origin") == "overlay" for ln in web)  # overlay line tagged + concatenated


def test_sentry_parses_issues_and_stacktrace():
    # the canonical multiverse sentry-clone corpus: top-level events joined to issues by issue_id
    v = _load_sample("sentry")
    assert v["org"] == "acme"
    assert v["stats"]["issues"] == 5 and v["stats"]["events"] == 5
    iss = v["issues"][0]
    assert iss["shortId"] and iss["title"] and isinstance(iss["tags"], dict)
    ev = iss["events"][0]
    assert ev["exception"]["type"] and ev["exception"]["value"]
    frame = ev["exception"]["stacktrace"][0]
    assert frame["filename"].endswith(".py") and frame["context"]


def test_figma_parses_workspace_and_node_tree():
    v = _load_sample("figma")
    assert v["stats"]["files"] == 1 and v["stats"]["nodes"] >= 8
    doc = v["files"][0]["document"]
    assert doc["type"] == "DOCUMENT"
    # the tree reaches a TEXT node with characters + an absoluteBoundingBox
    seen = []

    def walk(n):
        seen.append(n)
        for c in n.get("children", []):
            walk(c)

    walk(doc)
    text = next(n for n in seen if n["type"] == "TEXT")
    assert text.get("characters") and text.get("absoluteBoundingBox")
    assert any(n.get("cornerRadius") for n in seen)  # the CTA frame


@pytest.mark.skipif(not dockerutil.image_exists(GAUGE_IMG),
                    reason="needs local gauge-gateway:apex-paperless image")
def test_gauge_loads_baked_state_from_image():
    r = client.post("/api/gauge/load", json={"base_id": GAUGE_IMG})
    assert r.status_code == 200, r.text
    assert r.json()["stats"]["log_lines"] > 1  # the corpus stores {"entries":[...]}, must normalize
    v = client.get("/api/gauge/view").json()
    stream = next(iter(v["log_queries"]))
    assert isinstance(v["log_queries"][stream], list)  # normalized to a flat line list


@pytest.mark.skipif(not dockerutil.image_exists(FIGMA_PROD),
                    reason="needs local figma-service:prod-v1 image")
def test_figma_loads_baked_corpus_from_image():
    r = client.post("/api/figma/load", json={"base_id": FIGMA_PROD})
    assert r.status_code == 200, r.text
    assert r.json()["stats"]["nodes"] > 1000  # the real imported corpus
    f = client.get("/api/figma/view").json()["files"][0]
    assert f["thumbnailUrl"].startswith("http")  # a real rendered thumbnail image
    assert f["document"]["type"] == "DOCUMENT"


def test_github_parses_seed_script():
    v = _load_sample("github")
    assert v["stats"] == {"repos": 1, "issues": 2, "prs": 1, "reviews": 2, "comments": 0}
    assert v["prs"][0]["head"] == "fix/read-timeout" and v["prs"][0]["base"] == "main"
    states = {r["state"] for r in v["reviews"]}
    assert states == {"changes_requested", "approved"}
    assert "gh repo create" in v["raw"]


def test_logfire_parses_traces_spans_exceptions():
    v = _load_sample("logfire")
    assert v["stats"]["records"] == 11 and v["stats"]["traces"] == 4
    co = next(t for t in v["traces"] if t["root_name"] == "POST /checkout")
    assert co["span_count"] == 6 and co["error_count"] >= 1
    assert max(s["depth"] for s in co["spans"]) >= 2
    exc = next(s for s in co["spans"] if s["is_exception"])
    assert exc["exception_type"] == "PaymentDeclinedError" and "Traceback" in exc["exception_stacktrace"]
    root = co["spans"][0]
    assert root["http_method"] == "POST" and root["http_status_code"] == 500


def test_gworkspace_parses_drive_docs_calendar_gmail():
    v = _load_sample("gworkspace")
    assert v["stats"] == {"files": 5, "folders": 1, "documents": 2, "events": 1, "messages": 1}
    launch = next(n for n in v["tree"] if n["isFolder"])
    assert launch["name"] == "Launch" and {c["name"] for c in launch["children"]} >= {"Q3 Launch Plan"}
    doc = next(d for d in v["documents"] if d["documentId"] == "DOC_Q3PLAN_0001")
    assert [h["text"] for h in doc["headings"]] == ["Q3 Launch Plan", "Goals", "Status"]
    assert v["events"][0]["summary"] == "Q3 Launch Sync"
    assert v["messages"][0]["from"] == "omar@acme.example"


def test_notion_parses_databases_pages_blocks():
    v = _load_sample("notion")
    assert v["stats"]["databases"] == 1 and v["stats"]["pages"] == 3
    db = v["databases"][0]
    assert db["title"] == "Engineering Tasks" and "Status" in db["property_order"]
    page = next(p for p in v["pages"] if p["title"] == "Fix login redirect loop")
    assert page["properties"]["Status"]["display"] == "In Progress"
    assert page["properties"]["Status"]["options"][0]["color"] == "blue"
    assert {"heading_2", "to_do", "bulleted_list_item"} <= {b["type"] for b in page["blocks"]}
    todo = next(b for b in page["blocks"] if b["type"] == "to_do")
    assert isinstance(todo["checked"], bool) and todo["rich"][0]["text"]
    assert page["comments"] and page["comments"][0]["rich"][0]["text"]


def test_aws_parses_services():
    v = _load_sample("aws")
    assert v["meta"]["region"] == "us-east-1"
    labels = {n["label"] for n in v["nav"]}
    assert {"S3", "SQS", "DynamoDB", "Lambda", "IAM"} <= labels
    assert v["services"]["s3"][0]["name"] and "objects" in v["services"]["s3"][0]
    assert v["services"]["lambda"][0]["function_name"]
    assert v["services"]["iam"]["users"]
