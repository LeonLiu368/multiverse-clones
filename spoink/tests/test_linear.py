"""Linear -> jira-clone state.json mapping, with a fake GraphQL client (no key needed)."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spoink.linear_export import fetch_workspace, to_state  # noqa: E402

ORG = {"name": "Test", "urlKey": "test"}
TEAMS = [{"id": "t1", "key": "TST", "name": "Test", "issueCount": 2}]
USERS = [
    {"id": "u1", "name": "Alice A", "displayName": "Alice", "email": "alice@x.test", "active": True},
    {"id": "u2", "name": "Bob B", "displayName": "Bob", "email": "bob@x.test", "active": True},
]
ISSUES = [
    {"id": "i1", "identifier": "TST-1", "title": "Login broken", "description": "d",
     "priority": 1, "createdAt": "2026-06-20T10:00:00.000Z", "updatedAt": "2026-06-21T10:00:00.000Z",
     "completedAt": None, "canceledAt": None, "state": {"id": "s1", "name": "In Progress", "type": "started"},
     "assignee": {"id": "u1", "displayName": "Alice", "email": "alice@x.test"},
     "labels": {"nodes": [{"id": "l1", "name": "bug"}]}},
    {"id": "i2", "identifier": "TST-2", "title": "Add export", "description": "",
     "priority": 3, "createdAt": "2026-06-22T10:00:00.000Z", "updatedAt": "2026-06-22T10:00:00.000Z",
     "completedAt": "2026-06-23T10:00:00.000Z", "canceledAt": None,
     "state": {"id": "s2", "name": "Done", "type": "completed"}, "assignee": None, "labels": {"nodes": []}},
]
COMMENTS = [
    {"id": "c1", "body": "looking into it", "createdAt": "2026-06-20T11:00:00.000Z",
     "issue": {"identifier": "TST-1"}, "user": {"id": "u2", "displayName": "Bob", "email": "bob@x.test"}},
    {"id": "c2", "body": "orphan", "createdAt": "2026-06-20T12:00:00.000Z",
     "issue": {"identifier": "TST-999"}, "user": {"id": "u1", "displayName": "Alice", "email": "alice@x.test"}},
]


class FakeLinear:
    def gql(self, q, variables=None):
        return {"organization": ORG}

    def paginate(self, q, conn, **v):
        return iter({"teams": TEAMS, "users": USERS, "issues": ISSUES, "comments": COMMENTS}[conn])


def test_to_state_maps_jira_clone_shape():
    state = to_state(fetch_workspace(FakeLinear(), None))

    assert state["project"] == {"id": "proj-tst", "key": "TST", "name": "Test", "archived": False}
    assert state["workspace"] == "test"
    assert len(state["issues"]) == 2

    by = {i["identifier"]: i for i in state["issues"]}
    # priority int -> ticketvector vocab; state.type -> category; real assignee kept
    assert by["TST-1"]["priority"] == "urgent"          # 1 -> urgent
    assert by["TST-2"]["priority"] == "medium"          # 3 -> medium
    assert by["TST-1"]["assignees"][0] == {"id": "user-alice", "handle": "alice", "name": "Alice"}
    assert by["TST-1"]["created_at"] == "2026-06-20T10:00:00Z"   # normalized iso
    assert by["TST-1"]["labels"] == [{"id": "label-bug", "name": "bug"}]

    cats = {s["name"]: s["category"] for s in state["states"]}
    assert cats["In Progress"] == "started" and cats["Done"] == "completed"

    # comments attach to kept issues only (orphan TST-999 dropped); count set on issue
    assert list(state["comments"]) == ["TST-1"]
    assert state["comments"]["TST-1"][0]["author"]["name"] == "Bob"
    assert by["TST-1"]["comments_count"] == 1 and by["TST-2"]["comments_count"] == 0

    handles = {u["handle"] for u in state["users"]}
    assert {"alice", "bob"} <= handles
