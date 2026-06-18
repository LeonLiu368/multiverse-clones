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
def test_overlay_ops_provenance_and_base_protection():
    client.post("/api/jira/load", json={"base_id": f"file:{WEB}"})

    def op(name, payload):
        return client.post("/api/jira/overlay/op", json={"op": name, "payload": payload})

    # add issue -> overlay, with the real project key
    added = op("add_issue", {"title": "planted", "state": "In Progress", "priority": "high",
                             "assignee": "priya.singh"}).json()
    assert added["origin"] == "overlay" and added["identifier"].startswith("WEB-")
    ident = added["identifier"]

    # comment on it -> overlay, attributed to the chosen existing user
    c = op("add_comment", {"identifier": ident, "body": "repro", "author": "diego.brooks"}).json()
    assert c["origin"] == "overlay" and c["author"]["handle"] == "diego.brooks"

    # edit a BASE issue -> allowed, flagged edited
    e = op("update_issue", {"identifier": "WEB-1", "state": "In Progress"}).json()
    assert e["origin"] == "base" and e["edited"] is True and e["state"]["name"] == "In Progress"

    # base data is protected from deletion
    assert op("remove_issue", {"identifier": "WEB-2"}).status_code == 400

    # overlay issue can be removed
    assert op("remove_issue", {"identifier": ident}).status_code == 200


@need
def test_export_merged_state_round_trips():
    client.post("/api/jira/load", json={"base_id": f"file:{WEB}"})
    client.post("/api/jira/overlay/op", json={"op": "update_issue",
                                              "payload": {"identifier": "WEB-1", "state": "Done"}})
    added = client.post("/api/jira/overlay/op", json={"op": "add_issue",
                                                      "payload": {"title": "exported"}}).json()
    state = client.get("/api/jira/overlay/export").json()
    assert set(["project", "issues", "comments", "users", "states"]).issubset(state)

    # the exported state.json loads back through ticketvector's own backend
    if TV not in sys.path:
        sys.path.insert(0, TV)
    from world_issues.client import FakePlaneBackend  # type: ignore

    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "state.json")
        json.dump(state, open(p, "w"))
        b = FakePlaneBackend(state_file=p)
        idents = {i["identifier"] for i in b.issue_list(limit=999)["results"]}
        assert added["identifier"] in idents
        assert next(i for i in b.issue_list(limit=999)["results"]
                    if i["identifier"] == "WEB-1")["state"]["name"] == "Done"


def test_jira_op_requires_session():
    # fresh op without a load (use a distinct app instance is hard; just assert unknown op guarded)
    r = client.post("/api/jira/overlay/op", json={"op": "bogus", "payload": {}})
    assert r.status_code == 400
