"""gh-compatible `--json` export.

Real gh's `--json` takes a comma-separated field list, returns a JSON array (or
object) containing ONLY those fields, in gh's schema (camelCase keys, sorted,
compact; `state` upper-cased; `author`/`labels`/… as nested objects). With no
value it errors and lists the available fields.

We map the common, agent-used fields from the Forgejo response to gh's schema.
GitHub-only fields with no Forgejo equivalent (reactionGroups, statusCheckRollup,
projectCards, viewer*, the opaque GraphQL `id`, …) are accepted but return a
typed empty value, so a script asking for them still gets valid JSON.
"""

from __future__ import annotations

import json as _json
import sys


def _user(u):
    u = u or {}
    return {"id": str(u.get("id", "")), "is_bot": bool(u.get("is_bot", False)),
            "login": u.get("login", ""), "name": u.get("full_name", "") or ""}


def _label(lb):
    return {"id": str(lb.get("id", "")), "name": lb.get("name", ""),
            "description": lb.get("description", "") or "",
            "color": (lb.get("color", "") or "").lstrip("#")}


def _milestone(m):
    if not m:
        return None
    return {"number": m.get("id", 0), "title": m.get("title", ""),
            "description": m.get("description", "") or "",
            "dueOn": m.get("due_on")}


def _clean_url(u):
    return (u or "").replace("/pulls/", "/pull/")


# Each resource maps gh field name -> (fn(obj) -> value). Fields not listed but
# valid in gh return an empty default (see _EMPTY).
ISSUE = {
    "number": lambda o: o.get("number"),
    "title": lambda o: o.get("title", ""),
    "state": lambda o: str(o.get("state", "")).upper(),
    "stateReason": lambda o: o.get("state_reason"),
    "body": lambda o: o.get("body", "") or "",
    "url": lambda o: _clean_url(o.get("html_url", "")),
    "id": lambda o: str(o.get("id", "")),
    "author": lambda o: _user(o.get("user")),
    "labels": lambda o: [_label(x) for x in o.get("labels") or []],
    "assignees": lambda o: [_user(x) for x in o.get("assignees") or []],
    "milestone": lambda o: _milestone(o.get("milestone")),
    "comments": lambda o: o.get("comments", 0),
    "createdAt": lambda o: o.get("created_at"),
    "updatedAt": lambda o: o.get("updated_at"),
    "closedAt": lambda o: o.get("closed_at"),
    "closed": lambda o: str(o.get("state", "")) == "closed",
    "isPinned": lambda o: bool(o.get("is_pinned", False)),
}

PR = dict(ISSUE, **{
    "headRefName": lambda o: (o.get("head") or {}).get("ref", ""),
    "baseRefName": lambda o: (o.get("base") or {}).get("ref", ""),
    "headRefOid": lambda o: (o.get("head") or {}).get("sha", ""),
    "baseRefOid": lambda o: (o.get("base") or {}).get("sha", ""),
    "isDraft": lambda o: bool(o.get("draft", False)),
    "merged": lambda o: bool(o.get("merged", False)),
    "mergedAt": lambda o: o.get("merged_at"),
    "mergeable": lambda o: o.get("mergeable"),
    "additions": lambda o: o.get("additions", 0),
    "deletions": lambda o: o.get("deletions", 0),
    "changedFiles": lambda o: o.get("changed_files", 0),
    "state": lambda o: "MERGED" if o.get("merged") else str(o.get("state", "")).upper(),
})

REPO = {
    "name": lambda o: o.get("name", ""),
    "nameWithOwner": lambda o: o.get("full_name", ""),
    "description": lambda o: o.get("description", "") or "",
    "url": lambda o: o.get("html_url", ""),
    "isPrivate": lambda o: bool(o.get("private", False)),
    "isFork": lambda o: bool(o.get("fork", False)),
    "isArchived": lambda o: bool(o.get("archived", False)),
    "isEmpty": lambda o: bool(o.get("empty", False)),
    "defaultBranchRef": lambda o: {"name": o.get("default_branch", "")},
    "stargazerCount": lambda o: o.get("stars_count", 0),
    "forkCount": lambda o: o.get("forks_count", 0),
    "createdAt": lambda o: o.get("created_at"),
    "updatedAt": lambda o: o.get("updated_at"),
    "pushedAt": lambda o: o.get("updated_at"),
    "sshUrl": lambda o: o.get("ssh_url", ""),
    "owner": lambda o: {"id": str((o.get("owner") or {}).get("id", "")),
                        "login": (o.get("owner") or {}).get("login", "")},
    "visibility": lambda o: "PRIVATE" if o.get("private") else "PUBLIC",
}

RELEASE = {
    "name": lambda o: o.get("name", "") or o.get("tag_name", ""),
    "tagName": lambda o: o.get("tag_name", ""),
    "isDraft": lambda o: bool(o.get("draft", False)),
    "isPrerelease": lambda o: bool(o.get("prerelease", False)),
    "isLatest": lambda o: not (o.get("draft") or o.get("prerelease")),
    "createdAt": lambda o: o.get("created_at"),
    "publishedAt": lambda o: o.get("published_at"),
    "url": lambda o: o.get("html_url", ""),
    "body": lambda o: o.get("body", "") or "",
}

LABEL = {
    "id": lambda o: str(o.get("id", "")),
    "name": lambda o: o.get("name", ""),
    "color": lambda o: (o.get("color", "") or "").lstrip("#"),
    "description": lambda o: o.get("description", "") or "",
}

def _run_step_json(s):
    return {"conclusion": s.get("conclusion", "") or "", "name": s.get("name", ""),
            "number": s.get("number", 0), "status": s.get("status", "")}


def _run_job_json(j):
    return {"completedAt": j.get("completed_at") or None,
            "conclusion": j.get("conclusion", "") or "",
            "databaseId": j.get("id"), "name": j.get("name", ""),
            "startedAt": j.get("started_at") or None, "status": j.get("status", ""),
            "steps": [_run_step_json(s) for s in j.get("steps", [])],
            "url": j.get("url", "") or ""}


# gh's `gh run view --json` fields. Source keys cover BOTH the seeded Actions
# overlay (run_number/head_sha/run_started_at/url/jobs) and the live-forge run
# shape (html_url/head_branch), so the same map serves either path.
RUN = {
    "attempt": lambda o: o.get("attempt", 1),
    "conclusion": lambda o: o.get("conclusion", "") or "",
    "createdAt": lambda o: o.get("created_at"),
    "databaseId": lambda o: o.get("id"),
    "displayTitle": lambda o: o.get("display_title", o.get("name", "")),
    "event": lambda o: o.get("event", ""),
    "headBranch": lambda o: o.get("head_branch", ""),
    "headSha": lambda o: o.get("head_sha", o.get("sha", "")),
    "jobs": lambda o: [_run_job_json(j) for j in o.get("jobs", [])],
    "name": lambda o: o.get("name", ""),
    "number": lambda o: o.get("run_number", o.get("id")),
    "startedAt": lambda o: o.get("run_started_at", o.get("started_at", o.get("created_at"))),
    "status": lambda o: o.get("status", ""),
    "updatedAt": lambda o: o.get("updated_at", o.get("created_at")),
    "url": lambda o: o.get("html_url", "") or o.get("url", ""),
    "workflowDatabaseId": lambda o: o.get("workflow_id", o.get("workflow_database_id", "")),
    "workflowName": lambda o: o.get("name", ""),
}

WORKFLOW = {
    "id": lambda o: o.get("id", o.get("path", "")),
    "name": lambda o: o.get("name", o.get("path", "")),
    "path": lambda o: o.get("path", ""),
    "state": lambda o: o.get("state", "active"),
}

# gh's `gh pr checks --json` fields. `bucket` categorizes `state` into
# pass|fail|pending|skipping|cancel (computed in the Actions overlay).
CHECK = {
    "bucket": lambda o: o.get("bucket", ""),
    "completedAt": lambda o: o.get("completed_at") or None,
    "description": lambda o: o.get("description", "") or "",
    "event": lambda o: o.get("event", ""),
    "link": lambda o: o.get("link", o.get("url", "")),
    "name": lambda o: o.get("name", ""),
    "startedAt": lambda o: o.get("started_at") or None,
    "state": lambda o: o.get("state", ""),
    "workflow": lambda o: o.get("workflow", ""),
}


class JSONFieldError(Exception):
    """Raised when --json is given no/invalid fields; carries gh's message."""


def _jq_results(data, expr: str):
    """Run a jq expression over `data`, returning the result list. Prefer the
    embedded `jq` lib (self-contained, like gh's gojq); fall back to the `jq`
    binary if the lib isn't available."""
    try:
        import jq as _jqlib
        return _jqlib.compile(expr).input(data).all()
    except ImportError:
        import subprocess
        p = subprocess.run(["jq", "-c", expr], input=_json.dumps(data),
                           capture_output=True, text=True)
        if p.returncode != 0:
            print(p.stderr.strip() or "jq error", file=sys.stderr)
            raise SystemExit(1)
        return [_json.loads(ln) for ln in p.stdout.splitlines() if ln.strip()]


def print_jq(data, expr: str) -> None:
    """Apply a jq expression and print like gh's --jq: one result per line,
    strings raw (unquoted), objects/arrays as compact JSON."""
    try:
        results = _jq_results(data, expr)
    except SystemExit:
        raise
    except Exception as e:  # compile/runtime error
        print(f"failed to parse jq expression: {e}", file=sys.stderr)
        raise SystemExit(1)
    for r in results:
        if isinstance(r, str):
            print(r)
        elif r is None:
            print("null")
        elif isinstance(r, bool):
            print("true" if r else "false")
        elif isinstance(r, (int, float)):
            print(_json.dumps(r))
        else:
            print(_json.dumps(r, separators=(",", ":"), default=str))


def _fields_msg(mapping: dict, given: str | None) -> str:
    avail = "\n".join(f"  {k}" for k in sorted(mapping))
    if not given:
        return f"Specify one or more comma-separated fields for `--json`:\n{avail}"
    return f"Unknown JSON field. Available fields:\n{avail}"


def export(data, mapping: dict, fields: str, jq: str | None = None) -> None:
    """Print `data` (list or dict) as gh-schema JSON limited to `fields`.

    `fields` is the raw --json value (comma-separated). Empty/invalid -> gh-style
    error to stderr + exit 1. If `jq` is given, the filtered output is passed
    through the jq expression (gh's `--json … --jq …`).
    """
    requested = [f.strip() for f in (fields or "").split(",") if f.strip()]
    if not requested:
        print(_fields_msg(mapping, None), file=sys.stderr)
        raise SystemExit(1)
    unknown = [f for f in requested if f not in mapping]
    if unknown:
        print(_fields_msg(mapping, fields), file=sys.stderr)
        raise SystemExit(1)

    # gh sorts the TOP-LEVEL requested fields alphabetically, but keeps nested
    # objects (author/labels/…) in Go struct order — so we build the top level in
    # sorted order and DON'T re-sort (the mappers emit nested keys in gh's order).
    def one(obj):
        return {f: mapping[f](obj) for f in sorted(requested)}

    out = [one(o) for o in data] if isinstance(data, list) else one(data)
    if jq:
        return print_jq(out, jq)
    print(_json.dumps(out, separators=(",", ":"), default=str))
