"""Linear-faithful GraphQL surface over the ticketvector / abundant-jira-clone state.json.

The jira-gateway serves Plane-REST + a `linear` CLI skin; a real Linear GraphQL client or
`linear-mcp` (which POSTs to api.linear.app/graphql) can't talk to it. This serves the same
GraphQL shape over the SAME state.json the gateway bakes, so the agent's REAL Linear tooling
works: `{ issues(first, filter){ nodes{ identifier title state{name type} assignee{name} } } }`,
`{ teams{...} }`, `{ viewer{...} }`, per-issue comments, etc.

Read-only. `Authorization` header (raw key or Bearer) checked against LINEAR_TOKEN.
Backed by a baked state.json; data sealed behind the API.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from graphql import build_schema, graphql_sync
from graphql.utilities import value_from_ast_untyped

TOKEN = os.environ.get("LINEAR_TOKEN", "test-linear-key")
STATE = os.environ.get("LINEAR_STATE", "/var/lib/ticketvector/state.json")
PORT = int(os.environ.get("LINEAR_PORT", "80"))
EMAIL_DOMAIN = os.environ.get("LINEAR_EMAIL_DOMAIN", "abundant.ai")

PRIORITY_INT = {"none": 0, "urgent": 1, "high": 2, "medium": 3, "low": 4}
PRIORITY_LABEL = {0: "No priority", 1: "Urgent", 2: "High", 3: "Medium", 4: "Low"}
# ticketvector state category -> Linear workflow-state type
TYPE_FOR = {"unstarted": "unstarted", "started": "started", "completed": "completed",
            "cancelled": "canceled", "backlog": "backlog", "triage": "triage"}

SDL = """
scalar JSON
scalar DateTime
schema { query: Query }
type Query {
  viewer: User
  organization: Organization
  teams(first: Int, after: String): TeamConnection
  team(id: String): Team
  users(first: Int, after: String): UserConnection
  workflowStates(first: Int, after: String): WorkflowStateConnection
  issueLabels(first: Int, after: String): IssueLabelConnection
  issues(first: Int, after: String, filter: JSON, orderBy: String): IssueConnection
  issue(id: String!): Issue
  comments(first: Int, after: String): CommentConnection
}
type PageInfo { hasNextPage: Boolean! endCursor: String }
type Organization { id: ID! name: String urlKey: String userCount: Int }
type User { id: ID! name: String displayName: String email: String active: Boolean }
type Team { id: ID! key: String name: String issueCount: Int }
type WorkflowState { id: ID! name: String type: String }
type IssueLabel { id: ID! name: String }
type Issue {
  id: ID! identifier: String title: String description: String
  priority: Int priorityLabel: String createdAt: DateTime updatedAt: DateTime
  state: WorkflowState assignee: User team: Team
  labels(first: Int): IssueLabelConnection
  comments(first: Int): CommentConnection
}
type Comment { id: ID! body: String createdAt: DateTime user: User }
type TeamConnection { nodes: [Team!]! pageInfo: PageInfo! }
type UserConnection { nodes: [User!]! pageInfo: PageInfo! }
type WorkflowStateConnection { nodes: [WorkflowState!]! pageInfo: PageInfo! }
type IssueLabelConnection { nodes: [IssueLabel!]! pageInfo: PageInfo! }
type IssueConnection { nodes: [Issue!]! pageInfo: PageInfo! }
type CommentConnection { nodes: [Comment!]! pageInfo: PageInfo! }
"""


def _conn(items, first=None):
    n = len(items)
    sliced = items[: first] if first else items
    return {"nodes": sliced, "pageInfo": {"hasNextPage": bool(first and first < n),
                                          "endCursor": str(len(sliced)) if sliced else None}}


def _build(state):
    """Shape the ticketvector state.json into Linear-GraphQL objects (camelCase, connections)."""
    ws = state.get("workspace") or "workspace"
    proj = state.get("project") or {}
    team = {"id": proj.get("id", "team-1"), "key": proj.get("key", "TEAM"),
            "name": proj.get("name", proj.get("key", "Team")), "issueCount": len(state.get("issues", []))}

    def user(u):
        if not u:
            return None
        h = u.get("handle") or u.get("id", "user")
        return {"id": u["id"], "name": u.get("name") or h, "displayName": u.get("name") or h,
                "email": f"{h}@{EMAIL_DOMAIN}", "active": True}

    users = [user(u) for u in state.get("users", [])]
    by_uid = {u["id"]: u for u in users}
    type_by_state_id = {s["id"]: TYPE_FOR.get(s.get("category"), "unstarted") for s in state.get("states", [])}
    states = [{"id": s["id"], "name": s["name"], "type": TYPE_FOR.get(s.get("category"), "unstarted")}
              for s in state.get("states", [])]
    labels = [{"id": l["id"], "name": l["name"]} for l in state.get("labels", [])]
    comments_by_ident = state.get("comments", {}) or {}

    issues, by_id, by_ident = [], {}, {}
    for i in state.get("issues", []):
        st = i.get("state") or {}
        assignee = (i.get("assignees") or [None])[0]
        prio = PRIORITY_INT.get(i.get("priority"), 0)
        cmts = [{"id": c["id"], "body": c.get("body", ""), "createdAt": c.get("created_at"),
                 "user": by_uid.get((c.get("author") or {}).get("id")) or user(c.get("author"))}
                for c in comments_by_ident.get(i["identifier"], [])]
        obj = {
            "id": i["id"], "identifier": i["identifier"], "title": i.get("title"),
            "description": i.get("description"), "priority": prio, "priorityLabel": PRIORITY_LABEL[prio],
            "createdAt": i.get("created_at"), "updatedAt": i.get("updated_at"),
            "state": {"id": st.get("id"), "name": st.get("name"), "type": type_by_state_id.get(st.get("id"), "unstarted")},
            "assignee": user(assignee) if assignee else None,
            "team": team,
            "labels": _conn([{"id": l["id"], "name": l["name"]} for l in i.get("labels", [])]),
            "comments": _conn(cmts),
        }
        issues.append(obj)
        by_id[obj["id"]] = by_ident[obj["identifier"]] = obj
    org = {"id": f"org-{ws}", "name": (proj.get("name") or ws), "urlKey": ws, "userCount": len(users)}
    viewer = {"id": "user-agent", "name": "Agent", "displayName": "Agent",
              "email": f"agent@{EMAIL_DOMAIN}", "active": True}
    return {"org": org, "viewer": viewer, "teams": [team], "users": users, "states": states,
            "labels": labels, "issues": issues, "by_id": by_id, "by_ident": by_ident,
            "all_comments": [c for i in issues for c in i["comments"]["nodes"]]}


def make_schema(state):
    G = _build(state)
    schema = build_schema(SDL)
    for name in ("JSON", "DateTime"):
        t = schema.type_map[name]
        t.serialize = lambda v: v
        t.parse_value = lambda v: v
        t.parse_literal = lambda ast, _vars=None: value_from_ast_untyped(ast, _vars)

    def issues_resolver(_root, _info, first=None, after=None, filter=None, orderBy=None):
        items = G["issues"]
        if filter and isinstance(filter, dict):  # support a team filter (id/key eq); ignore the rest
            tf = (filter.get("team") or {})
            want = (tf.get("id") or {}).get("eq") or (tf.get("key") or {}).get("eq")
            if want:
                items = [i for i in items if i["team"]["id"] == want or i["team"]["key"] == want]
        return _conn(items, first)

    Q = schema.query_type.fields
    Q["viewer"].resolve = lambda *_: G["viewer"]
    Q["organization"].resolve = lambda *_: G["org"]
    Q["teams"].resolve = lambda r, i, first=None, after=None: _conn(G["teams"], first)
    Q["team"].resolve = lambda r, i, id=None: next((t for t in G["teams"] if t["id"] == id or t["key"] == id), None)
    Q["users"].resolve = lambda r, i, first=None, after=None: _conn(G["users"], first)
    Q["workflowStates"].resolve = lambda r, i, first=None, after=None: _conn(G["states"], first)
    Q["issueLabels"].resolve = lambda r, i, first=None, after=None: _conn(G["labels"], first)
    Q["issues"].resolve = issues_resolver
    Q["issue"].resolve = lambda r, i, id=None: G["by_id"].get(id) or G["by_ident"].get(id)
    Q["comments"].resolve = lambda r, i, first=None, after=None: _conn(G["all_comments"], first)
    return schema


_SCHEMA = make_schema(json.load(open(STATE)))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._send(200 if self.path == "/health" else 404, {"ok": True} if self.path == "/health" else {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/graphql":
            self._send(404, {"error": "not found"})
            return
        auth = self.headers.get("Authorization", "")
        token = auth.split(" ", 1)[1] if auth.lower().startswith("bearer ") else auth
        if token != TOKEN:
            self._send(400, {"errors": [{"message": "authentication failed"}]})
            return
        n = int(self.headers.get("Content-Length", "0") or "0")
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            self._send(400, {"errors": [{"message": "invalid json"}]})
            return
        res = graphql_sync(_SCHEMA, body.get("query", ""), variable_values=body.get("variables") or {})
        out = {}
        if res.data is not None:
            out["data"] = res.data
        if res.errors:
            out["errors"] = [{"message": str(e)} for e in res.errors]
        self._send(200, out)


def main():
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
