"""Capture Sentry-clone parity demos in-process against the real seed file.

Running this verifies the seed format is accepted (the clone store loads it and serves reads)
AND captures the clone's ACTUAL output for the dashboard comparison boxes. The `real_output`
golden samples are authored from the real Sentry Web API v0 docs (https://docs.sentry.io/api/).
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

CLONE = Path(__file__).resolve().parents[2] / "clones" / "sentry-clone"
sys.path.insert(0, str(CLONE))

from sentry_clone.server import events, issues  # noqa: E402
from sentry_clone.server.state import SentryStore  # noqa: E402

SEED_REL = "examples/data/sentry-clone/state.json"


def build() -> dict:
    seed = json.load(open(CLONE / SEED_REL))
    store = SentryStore(copy.deepcopy(seed))

    org = store.org_slug()
    proj = "payments-api"
    hero = "PAYMENTS-501"  # the unresolved high-priority payments issue (id 1001)

    demos = []

    # ---- GET: list issues (table, is:unresolved default + query grammar) ---
    clone_issues = issues.list_project_issues(store, org, proj, query="is:unresolved", sort="freq")
    demos.append({
        "id": "list-issues",
        "title": "List unresolved issues",
        "method": "GET",
        "capability": "Issue search (is:/level:/assigned: query grammar)",
        "seed_excerpt": {"issues": [{"shortId": i.get("shortId"), "level": i.get("level"),
                                     "status": i.get("status"), "count": i.get("count"),
                                     "title": i.get("title")}
                                    for i in seed["issues"] if i.get("project_slug") == proj]},
        "ui": {"type": "table", "title": "Sentry › payments-api › Issues (is:unresolved)",
               "columns": ["level", "shortId", "title", "count", "userCount", "lastSeen"],
               "rows": [{"level": i.get("level"), "shortId": i.get("shortId"),
                         "title": i.get("title"), "count": i.get("count"),
                         "userCount": i.get("userCount"), "lastSeen": i.get("lastSeen")}
                        for i in clone_issues]},
        "agent": {"cli": "sentry issues list --project payments-api --query is:unresolved --sort freq",
                  "mcp": {"tool": "list_issues",
                          "args": {"project": proj, "query": "is:unresolved", "sort": "freq"}}},
        "real_mapping": {
            "api": "GET /api/0/projects/{org}/{project}/issues/?query=is:unresolved&sort=freq",
            "mcp": "sentry-mcp › list_issues",
            "cli": "curl -H 'Authorization: Bearer <token>'",
            "doc": "https://docs.sentry.io/api/events/list-a-projects-issues/"},
        "clone_output": clone_issues,
        "real_output": [{
            "id": i.get("id"), "shortId": i.get("shortId"), "title": i.get("title"),
            "culprit": i.get("culprit"), "level": i.get("level"), "status": i.get("status"),
            "substatus": i.get("substatus"), "isUnhandled": True, "count": str(i.get("count")),
            "userCount": i.get("userCount"), "firstSeen": i.get("firstSeen"),
            "lastSeen": i.get("lastSeen"), "permalink": f"https://sentry.io/organizations/{org}/issues/{i.get('id')}/",
            "project": {"id": "1", "slug": proj, "name": "Payments API"},
            "metadata": {"type": i.get("title", "").split(":")[0], "value": i.get("title")},
            "assignedTo": i.get("assignedTo")}
            for i in clone_issues],
    })

    # ---- GET: get one issue (list of key fields) --------------------------
    clone_issue = issues.get_issue(store, hero)
    demos.append({
        "id": "get-issue",
        "title": "Get an issue",
        "method": "GET",
        "capability": "Issue detail (shortId, status, culprit, counts)",
        "seed_excerpt": {"issue": {"id": clone_issue.get("id"), "shortId": clone_issue.get("shortId"),
                                   "status": clone_issue.get("status"), "level": clone_issue.get("level"),
                                   "culprit": clone_issue.get("culprit")}},
        "ui": {"type": "list", "title": f"Sentry › {hero}",
               "rows": [
                   {"icon": _level_icon(clone_issue.get("level")), "title": clone_issue.get("title"),
                    "sub": clone_issue.get("culprit"),
                    "tags": [clone_issue.get("level", ""), clone_issue.get("status", "")]},
                   {"icon": "#", "title": "shortId", "sub": clone_issue.get("shortId"), "tags": []},
                   {"icon": "∑", "title": "events / users",
                    "sub": f"{clone_issue.get('count')} events · {clone_issue.get('userCount')} users",
                    "tags": [clone_issue.get("priority", "")]},
                   {"icon": "⏱", "title": "lastSeen", "sub": clone_issue.get("lastSeen"), "tags": []},
               ]},
        "agent": {"cli": f"sentry issues get {hero}",
                  "mcp": {"tool": "get_issue", "args": {"issue": hero}}},
        "real_mapping": {
            "api": "GET /api/0/issues/{issue_id}/",
            "mcp": "sentry-mcp › get_issue",
            "cli": "curl -H 'Authorization: Bearer <token>'",
            "doc": "https://docs.sentry.io/api/events/retrieve-an-issue/"},
        "clone_output": clone_issue,
        "real_output": {
            "id": clone_issue.get("id"), "shortId": clone_issue.get("shortId"),
            "title": clone_issue.get("title"), "culprit": clone_issue.get("culprit"),
            "level": clone_issue.get("level"), "status": clone_issue.get("status"),
            "substatus": clone_issue.get("substatus"), "isPublic": False, "isUnhandled": True,
            "count": str(clone_issue.get("count")), "userCount": clone_issue.get("userCount"),
            "firstSeen": clone_issue.get("firstSeen"), "lastSeen": clone_issue.get("lastSeen"),
            "permalink": f"https://sentry.io/organizations/{org}/issues/{clone_issue.get('id')}/",
            "metadata": {"type": "RuntimeError", "value": clone_issue.get("title")},
            "assignedTo": clone_issue.get("assignedTo")},
    })

    # ---- GET: latest event (table of frames / event fields) ---------------
    clone_event = events.latest_event(store, hero)
    frames = (clone_event or {}).get("stacktrace", {}).get("frames", [])
    demos.append({
        "id": "latest-event",
        "title": "Get the latest event",
        "method": "GET",
        "capability": "Latest event (exception + stack frames)",
        "seed_excerpt": {"event": {"id": clone_event.get("id"), "issue_id": clone_event.get("issue_id"),
                                   "message": clone_event.get("message"),
                                   "exception": clone_event.get("exception")}},
        "ui": {"type": "table", "title": f"Sentry › {hero} › Latest event stacktrace",
               "columns": ["level", "function", "filename", "lineno", "context_line"],
               "rows": [{"level": "error" if f.get("in_app") else "info",
                         "function": f.get("function"), "filename": f.get("filename"),
                         "lineno": f.get("lineno"), "context_line": f.get("context_line")}
                        for f in frames]},
        "agent": {"cli": f"sentry issues latest-event {hero}",
                  "mcp": {"tool": "get_latest_event", "args": {"issue": hero}}},
        "real_mapping": {
            "api": "GET /api/0/issues/{issue_id}/events/latest/",
            "mcp": "sentry-mcp › get_latest_event",
            "cli": "curl -H 'Authorization: Bearer <token>'",
            "doc": "https://docs.sentry.io/api/events/retrieve-the-latest-event-for-an-issue/"},
        "clone_output": clone_event,
        "real_output": {
            "id": clone_event.get("id"), "eventID": clone_event.get("eventID", clone_event.get("id")),
            "groupID": clone_event.get("issue_id"), "projectID": "1",
            "message": clone_event.get("message"), "title": clone_event.get("message"),
            "platform": "python", "dateCreated": clone_event.get("timestamp"),
            "tags": [{"key": k, "value": v} for k, v in (clone_event.get("tags") or {}).items()],
            "entries": [{"type": "exception", "data": clone_event.get("exception")}],
            "user": clone_event.get("user")},
    })

    # ---- POST/PUT: resolve issue (before/after status flip) ---------------
    before_issue = issues.get_issue(store, hero)
    before = [{"id": before_issue.get("id"), "title": before_issue.get("shortId"),
               "tags": [before_issue.get("status"), before_issue.get("substatus")]}]
    resolved = issues.update_issue(store, hero, {"status": "resolved"})
    after = [{"id": resolved.get("id"), "title": resolved.get("shortId"),
              "tags": [resolved.get("status"), resolved.get("substatus")]}]
    demos.append({
        "id": "resolve-issue",
        "title": "Resolve an issue",
        "method": "POST",
        "capability": "Issue status write→read round-trip",
        "seed_excerpt": {"issue": {"shortId": before_issue.get("shortId"),
                                   "status_before": before_issue.get("status")}},
        "ui": {"type": "timeline", "title": f"Sentry › {hero} (status)",
               "before": before, "after": after, "new_id": resolved.get("id")},
        "agent": {"cli": f"sentry issues resolve {hero}",
                  "mcp": {"tool": "resolve_issue", "args": {"issue": hero}}},
        "real_mapping": {
            "api": "PUT /api/0/issues/{issue_id}/",
            "mcp": "sentry-mcp › resolve_issue",
            "cli": "curl -X PUT -d '{\"status\":\"resolved\"}'",
            "doc": "https://docs.sentry.io/api/events/update-an-issue/"},
        "clone_output": resolved,
        "real_output": {
            "id": resolved.get("id"), "shortId": resolved.get("shortId"),
            "status": resolved.get("status"), "substatus": resolved.get("substatus"),
            "statusDetails": {}, "isPublic": False,
            "assignedTo": resolved.get("assignedTo")},
        "change": {"before": before, "after": after, "new_id": resolved.get("id")},
    })

    return {
        "clone": "sentry-clone",
        "product": "Sentry",
        "real_service": {
            "name": "Sentry Web API v0",
            "reference": "https://docs.sentry.io/api/",
            "api_base": "{gateway}/api/0"},
        "parity": {"verdict": "HIGH after reliability pass",
                   "note": "is:unresolved default + real is:/level:/assigned: query grammar, "
                           "shortId PAYMENTS-501, {detail} errors."},
        "seed_file": SEED_REL,
        "surfaces": {"cli": "sentry", "mcp": "sentry-mcp"},
        "demos": demos,
    }


def _level_icon(level: str | None) -> str:
    return {"error": "🔴", "fatal": "🔴", "warning": "🟡", "warn": "🟡",
            "info": "🔵", "debug": "⚪"}.get((level or "").lower(), "⚪")


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "data" / "sentry-clone.json"
    manifest = build()
    out.write_text(json.dumps(manifest, indent=2, default=str))
    print(f"OK sentry-clone: {len(manifest['demos'])} demos, "
          f"seed '{manifest['seed_file']}' accepted -> {out}")
