"""Capture abundant-jira-clone parity demos in-process against the real seed file.

NO DOCKER / NO ticketvector engine here: the ``/rpc`` gateway (CLI, JQL engine, JSON-RPC
transport, seed generator) lives in the external ``ghcr.io/abundant-ai/ticketvector-service``
image, which we cannot boot in this environment. So we do the honest next-best thing:

  * We read the clone's REAL seed (``tasks/*/environment/data/state.json``) — that IS the
    ticketvector-native issue shape the gateway serves (flat issue payload, ``state:{id,name}``,
    ``assignees[]``, ``priority`` string, ``PROJ-###`` keys).
  * We stand up a tiny in-process ``/rpc`` backend that reproduces the gateway's envelopes
    from that seed (``get_issue`` → flat issue, ``issue_list`` → ``{results,next_cursor}``,
    ``update_issue`` → ``(before,after)``, error → ``{ok:false,error_type,error}``), and
    monkeypatch it onto the clone's OWN ``TicketVectorClient._rpc`` transport.
  * We then call the clone's ACTUAL MCP tool functions (``mcp/server.py`` +
    ``mcp/client.py`` + ``mcp/jql.py``) — so ``clone_output`` is produced by the clone's real
    marshalling code (``parse_jql``, ``_minimal_issue``, ``_mutation_receipt``), not authored.

The ``real_output`` golden samples are authored from the real Jira Cloud REST API v3 docs
(``{id,key,fields:{...}}``, ``{issues,nextPageToken,isLast}``, ``{errorMessages,errors}``).
Because the clone presents ticketvector-native shapes rather than Jira REST shapes, the
comparison HONESTLY shows a LOW shape-parity — that is correct and intended for this clone.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

CLONE = Path(__file__).resolve().parents[2] / "clones" / "abundant-jira-clone"
sys.path.insert(0, str(CLONE))

# The clone's OWN code (mcp/ package). No world_issues dependency; these are self-contained.
from mcp import client as mcp_client  # noqa: E402
from mcp import server as mcp_server  # noqa: E402

# The transition-roundtrip seed is the served ticketvector-native issue corpus (WEB project).
SEED_REL = "tasks/jira-transition-roundtrip/environment/data/state.json"


# --------------------------------------------------------------------------- #
# In-process /rpc backend: reproduces the ticketvector gateway envelopes from
# the seed state.json. This stands in for the external image we cannot boot;
# the shapes are exactly what the clone's seed serves.
# --------------------------------------------------------------------------- #
class RecordedRpcBackend:
    """A minimal, faithful stand-in for the ticketvector ``/rpc`` gateway, seeded from
    ``state.json``. Serves the same envelopes ``mcp/client.TicketVectorClient`` expects."""

    def __init__(self, state: dict) -> None:
        self.state = copy.deepcopy(state)
        self.comments: dict[str, list] = {
            k: list(v) for k, v in (self.state.get("comments") or {}).items()
        }

    def _issues(self) -> list[dict]:
        return self.state["issues"]

    def _find(self, identifier: str) -> dict | None:
        return next((i for i in self._issues() if i["identifier"] == identifier), None)

    def _state_by_name(self, name: str) -> dict | None:
        return next((s for s in self.state.get("states", []) if s["name"].lower() == name.lower()), None)

    def _page(self, items: list, limit: int, cursor: str | None) -> dict:
        # ticketvector-native pagination envelope: {results, next_cursor}
        start = int(cursor) if cursor else 0
        window = items[start : start + limit]
        nxt = start + limit
        next_cursor = str(nxt) if nxt < len(items) else None
        return {"results": window, "next_cursor": next_cursor}

    def _apply_filters(self, items: list, filters: dict | None) -> list:
        if not filters:
            return items
        out = items
        if "assignee" in filters and filters["assignee"] != "me":
            want = filters["assignee"]
            out = [i for i in out if any(a.get("handle") == want for a in i.get("assignees", []))]
        if "state" in filters:
            out = [i for i in out if (i.get("state") or {}).get("name", "").lower() == filters["state"].lower()]
        if "state_ne" in filters:
            out = [i for i in out if (i.get("state") or {}).get("name", "").lower() != filters["state_ne"].lower()]
        if "priority" in filters:
            wanted = filters["priority"]
            wanted = wanted if isinstance(wanted, list) else [wanted]
            wanted = [w.lower() for w in wanted]
            out = [i for i in out if (i.get("priority") or "").lower() in wanted]
        if "label" in filters:
            out = [i for i in out if filters["label"] in [l.get("name") for l in i.get("labels", [])]]
        if "project" in filters:
            key = filters["project"]
            out = [i for i in out if i["identifier"].split("-")[0].upper() == key.upper()]
        return out

    def _text_search(self, items: list, query: str) -> list:
        q = query.lower()
        return [i for i in items if q in (i.get("title", "") + " " + i.get("description", "")).lower()]

    # ---- dispatch (method names mirror RemoteTicketBackend) ----
    def rpc(self, method: str, *args, **kwargs):
        if method == "current_user":
            return {"id": "user-agent", "handle": "agent", "name": "Agent"}
        if method == "project_list":
            p = self.state["project"]
            return [{"id": p["id"], "key": p["key"], "name": p["name"], "archived": p.get("archived", False)}]
        if method == "list_states":
            return list(self.state.get("states", []))
        if method == "list_labels":
            return list(self.state.get("labels", []))
        if method == "issue_list":
            query = kwargs.get("query")
            filters = kwargs.get("filters")
            limit = kwargs.get("limit", 50)
            cursor = kwargs.get("cursor")
            items = list(self._issues())
            if query is not None:
                items = self._text_search(items, query)
            else:
                items = self._apply_filters(items, filters)
            return self._page(items, limit, cursor)
        if method == "issue_mine":
            actor = args[0] if args else "agent"
            limit = kwargs.get("limit", 50)
            cursor = kwargs.get("cursor")
            items = [i for i in self._issues() if any(a.get("handle") == actor for a in i.get("assignees", []))]
            return self._page(items, limit, cursor)
        if method == "get_issue":
            issue = self._find(args[0])
            if issue is None:
                raise mcp_client.RpcError(f"issue not found: {args[0]}", error_type="NotFoundError")
            return copy.deepcopy(issue)
        if method == "list_comments":
            return list(self.comments.get(args[0], []))
        if method == "list_links":
            return list((self.state.get("links") or {}).get(args[0], []))
        if method == "history_list":
            return [h for h in self.state.get("history", []) if h.get("identifier") == args[0]]
        if method == "update_issue":
            identifier = args[0]
            issue = self._find(identifier)
            if issue is None:
                raise mcp_client.RpcError(f"issue not found: {identifier}", error_type="NotFoundError")
            before = copy.deepcopy(issue)
            if "state" in kwargs:
                st = self._state_by_name(kwargs["state"])
                if st is None:
                    raise mcp_client.RpcError(f"state not found: {kwargs['state']}", error_type="NotFoundError")
                issue["state"] = {"id": st["id"], "name": st["name"]}
            after = copy.deepcopy(issue)
            return [before, after]
        if method == "add_comment":
            identifier = args[0]
            body = args[1]
            issue = self._find(identifier)
            if issue is None:
                raise mcp_client.RpcError(f"issue not found: {identifier}", error_type="NotFoundError")
            comment = {
                "id": f"comment-{identifier.lower()}-{len(self.comments.get(identifier, [])) + 1}",
                "issue": identifier,
                "body": body,
                "author": {"id": "user-agent", "handle": "agent", "name": "Agent"},
                "created_at": "2026-07-01T00:00:00Z",
            }
            self.comments.setdefault(identifier, []).append(comment)
            issue["comments_count"] = len(self.comments[identifier])
            return copy.deepcopy(comment)
        raise mcp_client.RpcError(f"unsupported command: {method}", error_type="UnsupportedCommandError")


def build() -> dict:
    seed = json.load(open(CLONE / SEED_REL))
    backend = RecordedRpcBackend(seed)

    # Point the clone's REAL client transport at the in-process backend, so every MCP tool
    # (get_issue / search_issues / issue_list / update_issue) runs the clone's actual code.
    def _rpc(self, method, *args, **kwargs):  # noqa: ANN001
        return backend.rpc(method, *args, **kwargs)

    mcp_client.TicketVectorClient._rpc = _rpc  # type: ignore[assignment]

    project = seed["project"]
    demos = []

    # ---- GET: get one issue (list view: identifier/title/state/assignees/priority) ----
    clone_issue = mcp_server.get_issue("WEB-1")
    demos.append({
        "id": "get-issue",
        "title": "Get one issue",
        "method": "GET",
        "capability": "Get issue (state, assignees, priority)",
        "seed_excerpt": {"issues": [{
            "identifier": "WEB-1", "title": clone_issue["title"],
            "state": clone_issue["state"], "priority": clone_issue["priority"]}]},
        "ui": {"type": "list", "title": f"Jira › {project['key']} › {clone_issue['identifier']}",
               "rows": [{
                   "icon": _prio_icon(clone_issue.get("priority")),
                   "title": f"{clone_issue['identifier']}  {clone_issue['title']}",
                   "sub": (clone_issue.get("state") or {}).get("name"),
                   "tags": [a.get("handle") for a in clone_issue.get("assignees", [])]
                           + [clone_issue.get("priority", "")]}]},
        "agent": {"cli": "jira issue view WEB-1",
                  "mcp": {"tool": "get_issue", "args": {"identifier": "WEB-1"}}},
        "real_mapping": {
            "api": "GET /rest/api/3/issue/{issueIdOrKey}",
            "mcp": "jira-mcp › get_issue",
            "cli": "curl -u email:token '.../rest/api/3/issue/WEB-1'",
            "doc": "https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-get"},
        "clone_output": clone_issue,
        "real_output": {
            "id": "10001", "key": clone_issue["identifier"],
            "self": "https://your-domain.atlassian.net/rest/api/3/issue/10001",
            "fields": {
                "summary": clone_issue["title"],
                "status": {"name": (clone_issue.get("state") or {}).get("name"),
                           "statusCategory": {"key": "done", "name": "Done"}},
                "assignee": {"accountId": "5b10a2844c20165700ede21g",
                             "displayName": (clone_issue.get("assignees") or [{}])[0].get("name"),
                             "emailAddress": "priya.singh@example.com"},
                "priority": {"id": "2", "name": "High"},
                "labels": [],
                "created": clone_issue.get("created_at"),
                "updated": clone_issue.get("updated_at")}},
    })

    # ---- GET: JQL search (table view — the strongest fidelity point) ----
    jql = "status = \"In Progress\" ORDER BY updated desc"
    clone_jql = mcp_server.search_issues(jql=jql, limit=50)
    demos.append({
        "id": "search-jql",
        "title": "Search issues with JQL",
        "method": "GET",
        "capability": "JQL query (real grammar) → issue table",
        "seed_excerpt": {"jql": jql,
                         "parsed_filters": _parse_jql_excerpt(jql)},
        "ui": {"type": "table", "title": f"Jira › {project['key']} › JQL: {jql}",
               "columns": ["key", "title", "status", "priority"],
               "rows": [{"key": i["identifier"], "title": i["title"],
                         "status": (i.get("state") or {}).get("name"),
                         "priority": i.get("priority")} for i in clone_jql["results"]]},
        "agent": {"cli": f'jira jql "{jql}"',
                  "mcp": {"tool": "search_issues", "args": {"jql": jql}}},
        "real_mapping": {
            "api": "POST /rest/api/3/search/jql",
            "mcp": "jira-mcp › search_issues",
            "cli": "curl -u email:token -X POST '.../rest/api/3/search/jql' -d '{\"jql\":\"...\"}'",
            "doc": "https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/#api-rest-api-3-search-jql-post"},
        "clone_output": clone_jql,
        "real_output": {
            "issues": [{
                "id": "10002", "key": i["identifier"],
                "fields": {
                    "summary": i["title"],
                    "status": {"name": (i.get("state") or {}).get("name")},
                    "priority": {"name": i.get("priority", "").capitalize()}}}
                for i in clone_jql["results"]],
            "nextPageToken": None,
            "isLast": True},
    })

    # ---- GET: list projects (list view) ----
    clone_projects = mcp_server.list_projects()
    demos.append({
        "id": "list-projects",
        "title": "List projects",
        "method": "GET",
        "capability": "Project list",
        "seed_excerpt": {"project": {"key": project["key"], "name": project["name"]}},
        "ui": {"type": "list", "title": "Jira › Projects",
               "rows": [{"icon": "▣", "title": p["name"], "sub": p["key"], "tags": []}
                        for p in clone_projects]},
        "agent": {"cli": "jira project list",
                  "mcp": {"tool": "list_projects", "args": {}}},
        "real_mapping": {
            "api": "GET /rest/api/3/project/search",
            "mcp": "jira-mcp › list_projects",
            "cli": "curl -u email:token '.../rest/api/3/project/search'",
            "doc": "https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-projects/#api-rest-api-3-project-search-get"},
        "clone_output": clone_projects,
        "real_output": {
            "self": "https://your-domain.atlassian.net/rest/api/3/project/search?startAt=0",
            "maxResults": 50, "startAt": 0, "total": len(clone_projects), "isLast": True,
            "values": [{
                "id": "10000", "key": p["key"], "name": p["name"],
                "projectTypeKey": "software", "simplified": False, "style": "next-gen"}
                for p in clone_projects]},
    })

    # ---- POST: transition issue (timeline / before→after state change) ----
    target_state = "Done"
    clone_receipt = mcp_server.transition_issue("WEB-2", target_state)
    before_min = clone_receipt["before"]
    after_min = clone_receipt["after"]
    demos.append({
        "id": "transition-issue",
        "title": "Transition an issue to a new state",
        "method": "POST",
        "capability": "Stateful transition (write→read round-trip)",
        "seed_excerpt": {"issue": "WEB-2",
                         "state_before": before_min["state"], "target": target_state},
        "ui": {"type": "timeline", "title": f"Jira › WEB-2 (workflow transition)",
               "before": [{"id": before_min["identifier"],
                           "text": f"{before_min['identifier']} → {before_min['state']['name']}",
                           "tags": [before_min.get("priority", "")]}],
               "after": [{"id": after_min["identifier"],
                          "text": f"{after_min['identifier']} → {after_min['state']['name']}",
                          "tags": [after_min.get("priority", "")]}],
               "new_id": after_min["identifier"]},
        "agent": {"cli": f'jira issue transition WEB-2 "{target_state}"',
                  "mcp": {"tool": "transition_issue",
                          "args": {"identifier": "WEB-2", "state": target_state}}},
        "real_mapping": {
            "api": "POST /rest/api/3/issue/{issueIdOrKey}/transitions",
            "mcp": "jira-mcp › transition_issue",
            "cli": "curl -u email:token -X POST '.../issue/WEB-2/transitions' -d '{\"transition\":{\"id\":\"31\"}}'",
            "doc": "https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-transitions-post"},
        "clone_output": clone_receipt,
        # Real Jira transition returns 204 No Content (empty body); the state change is
        # observed on a subsequent GET /issue. Golden reflects that read-back shape.
        "real_output": {
            "id": "10002", "key": after_min["identifier"],
            "fields": {"summary": after_min["title"],
                       "status": {"name": target_state,
                                  "statusCategory": {"key": "done", "name": "Done"}}}},
        "change": {
            "before": [{"id": before_min["identifier"],
                        "title": before_min["title"], "tags": [before_min["state"]["name"]]}],
            "after": [{"id": after_min["identifier"],
                       "title": after_min["title"], "tags": [after_min["state"]["name"]]}],
            "new_id": after_min["identifier"]},
    })

    return {
        "clone": "abundant-jira-clone",
        "product": "Jira",
        "real_service": {
            "name": "Jira Cloud REST API v3 (semantic model; clone serves ticketvector-native shapes)",
            "reference": "https://developer.atlassian.com/cloud/jira/platform/rest/v3/",
            "api_base": "https://<your-domain>.atlassian.net/rest/api/3"},
        "parity": {
            "verdict": "LOW (ticketvector-native shapes, not Jira REST) — faithful issue-tracking semantics + JQL grammar",
            "note": "What IS faithful: real JQL grammar, PROJ-### issue keys (WEB-1), and stateful write→read transitions/comments; the ENVELOPE differs (ticketvector {results,next_cursor} / {ok:false,error_type} / flat issue vs Jira {issues,nextPageToken} / {errorMessages} / fields+ADF)."},
        "seed_file": SEED_REL,
        "surfaces": {"cli": "jira / linear", "mcp": "jira-mcp"},
        "capture_note": "No Docker/ticketvector here — clone_output is the clone's served ticketvector-native shape (from mcp client marshalling / seed state.json). REAL column is real Jira REST v3, so the comparison honestly shows the envelope gap.",
        "demos": demos,
    }


def _prio_icon(priority: str | None) -> str:
    return {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "none": "⚪"}.get(
        (priority or "").lower(), "⚪")


def _parse_jql_excerpt(jql: str) -> dict:
    """Show the clone's OWN parse_jql output for this JQL (the fidelity point)."""
    from mcp.jql import parse_jql
    return parse_jql(jql)


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "data" / "abundant-jira-clone.json"
    manifest = build()
    out.write_text(json.dumps(manifest, indent=2, default=str))
    populated = sum(1 for d in manifest["demos"] if d.get("clone_output"))
    print(f"OK abundant-jira-clone: {len(manifest['demos'])} demos "
          f"({populated} with populated clone_output), seed '{manifest['seed_file']}' accepted -> {out}")
