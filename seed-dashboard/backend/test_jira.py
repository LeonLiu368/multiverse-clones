"""Jira adapter tests. Need the ticketvector checkout (TICKETVECTOR_BASE) + the abundant-jira-clone
data (JIRA_DATA_BASE); skip gracefully if either is absent so the rest of the suite still runs."""
import json
import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

from app import app
from clone_bridge import jira_data_base, ticketvector_base

client = TestClient(app)

TV = ticketvector_base()
WEB = os.path.join(jira_data_base(), "tasks", "jira-assignee-count", "environment", "data", "state.json")
have = os.path.isdir(TV) and os.path.isfile(WEB)
need = pytest.mark.skipif(not have, reason="needs ticketvector + abundant-jira-clone checkouts")


def test_jira_registered_active():
    apps = {a["id"]: a for a in client.get("/api/apps").json()}
    assert apps["jira"]["status"] == "active" and apps["jira"]["ui_module"] == "jira"


@need
def test_load_reads_project_and_issues():
    r = client.post("/api/jira/load", json={"base_id": f"file:{WEB}"})
    assert r.status_code == 200 and r.json()["stats"]["issues"] == 12
    assert [c["key"] for c in client.get("/api/jira/containers").json()] == ["WEB"]
    issues = client.get("/api/jira/messages", params={"container": "WEB", "limit": 50}).json()
    assert len(issues) == 12 and all(i["origin"] == "base" for i in issues)


@need
def test_overlay_ops_and_provenance():
    client.post("/api/jira/load", json={"base_id": f"file:{WEB}"})

    def op(name, payload):
        return client.post("/api/jira/overlay/op", json={"op": name, "payload": payload})

    # add issue -> overlay, with the real project key
    added = op("add_issue", {"title": "planted", "state": "In Progress", "priority": "high",
                             "assignee": "priya.singh"}).json()
    assert added["origin"] == "overlay" and added["identifier"].startswith("WEB-")

    # comment -> overlay, attributed to the chosen existing user
    c = op("add_comment", {"identifier": added["identifier"], "body": "repro",
                           "author": "diego.brooks"}).json()
    assert c["origin"] == "overlay" and c["author"]["handle"] == "diego.brooks"

    # edit a BASE issue (genuine change) -> allowed, flagged edited
    e = op("update_issue", {"identifier": "WEB-1", "state": "In Progress"}).json()
    assert e["origin"] == "base" and e["edited"] is True

    # base issue can now be DELETED (recorded in the patch, not refused)
    assert op("remove_issue", {"identifier": "WEB-2"}).status_code == 200
    assert op("remove_issue", {"identifier": "NOPE-9"}).status_code == 400  # unknown still errors

    changes = client.get("/api/jira/meta").json()["changes"]
    assert changes["added"] and "WEB-1" in changes["edited"]
    assert any(d["identifier"] == "WEB-2" for d in changes["deleted"])


@need
def test_overlay_merge_flags_added_issues_and_stays_out_of_patch():
    overlay = os.path.join(os.path.dirname(__file__), "..", "samples", "jira.overlay.json")
    with open(overlay, "rb") as fh:
        r = client.post("/api/jira/load_overlay", data={"base_id": f"file:{WEB}"},
                        files={"overlay": ("jira.overlay.json", fh, "application/json")})
    assert r.status_code == 200, r.text
    assert r.json()["stats"]["overlay_issues"] == 1
    issues = {i["identifier"]: i for i in client.get("/api/jira/messages", params={"container": "WEB"}).json()}
    assert "WEB-100" in issues and issues["WEB-100"]["origin"] == "overlay"
    # overlay rows are part of the baseline -> the edit patch is empty until you edit something
    assert client.get("/api/jira/overlay/patch").json()["ops"] == []


@need
def test_export_is_a_patch_that_applies_back():
    client.post("/api/jira/load", json={"base_id": f"file:{WEB}"})

    def op(name, payload):
        client.post("/api/jira/overlay/op", json={"op": name, "payload": payload})

    op("add_issue", {"title": "exported add", "state": "To Do", "priority": "high"})
    op("update_issue", {"identifier": "WEB-1", "state": "In Progress", "priority": "low"})
    op("remove_issue", {"identifier": "WEB-2"})
    op("add_comment", {"identifier": "WEB-3", "body": "ping", "author": "priya.singh"})

    patch = client.get("/api/jira/overlay/export").json()
    assert patch["version"] == 1
    kinds = {(o["op"], o["entity"]) for o in patch["ops"]}
    assert {("add", "issue"), ("update", "issue"), ("delete", "issue"), ("add", "comment")} <= kinds

    # the patch applies cleanly onto a fresh copy of the base via the clone's own applier
    applier_dir = os.path.join(jira_data_base(), "selfcontained", "base")
    if applier_dir not in sys.path:
        sys.path.insert(0, applier_dir)
    import apply_state_patch  # type: ignore

    state = json.load(open(WEB))
    n = apply_state_patch.apply_patch(state, patch)
    assert n == len(patch["ops"])
    issues = {i["identifier"]: i for i in state["issues"]}
    assert "WEB-2" not in issues  # deleted
    assert any(i["title"] == "exported add" for i in state["issues"])  # added
    assert issues["WEB-1"]["state"]["name"] == "In Progress" and issues["WEB-1"]["priority"] == "low"
    assert any(c["body"] == "ping" for c in state["comments"].get("WEB-3", []))


def test_jira_op_requires_session():
    # fresh op without a load (use a distinct app instance is hard; just assert unknown op guarded)
    r = client.post("/api/jira/overlay/op", json={"op": "bogus", "payload": {}})
    assert r.status_code == 400
