"""Linear workspace export via the GraphQL API (read-only) -> abundant-jira-clone state.json.

Second source for spoink (after Slack). Mirrors slack_export.py: a read-only client,
a fetch, an access-envelope / sufficiency report, and the target format the clone's
gateway ingests -- here the ticketvector `state.json` that abundant-jira-clone's
`tools/jira_to_state.py` emits, served by `jira-gateway:empty` (mount your own state).

Unlike jira_to_state (which anonymizes a customer's Jira XML), this keeps REAL names --
it captures our own Linear workspace, same as spoink's Slack capture. Read-only; the key
comes only from env LINEAR_API_KEY, never logged or written.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

import httpx

LINEAR_URL = "https://api.linear.app/graphql"

# Linear priority int -> ticketvector priority (jira_to_state's vocabulary).
PRIORITY_BY_INT = {0: "none", 1: "urgent", 2: "high", 3: "medium", 4: "low"}
# Linear workflow-state type -> ticketvector state category.
CATEGORY_BY_TYPE = {
    "triage": "unstarted", "backlog": "unstarted", "unstarted": "unstarted",
    "started": "started", "completed": "completed",
    "canceled": "cancelled", "duplicate": "cancelled",
}


class LinearError(Exception):
    def __init__(self, errors: Any):
        super().__init__(json.dumps(errors)[:300])
        self.errors = errors


# --------------------------------------------------------------------------- client


class LinearClient:
    """Thin Linear GraphQL client: raw-key auth, Relay cursor pagination, 429 backoff."""

    def __init__(self, key: str, *, timeout: float = 60.0):
        self._http = httpx.Client(
            headers={"Authorization": key, "Content-Type": "application/json"}, timeout=timeout
        )
        self.rate_limit_stalls = 0

    def close(self) -> None:
        self._http.close()

    def gql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        for _ in range(8):
            r = self._http.post(LINEAR_URL, json={"query": query, "variables": variables or {}})
            if r.status_code == 429:
                self.rate_limit_stalls += 1
                time.sleep(int(r.headers.get("Retry-After", "2")))
                continue
            # Linear returns GraphQL validation errors as HTTP 400 with an {errors:[...]} body,
            # so read the body for errors BEFORE raising on status.
            try:
                j = r.json()
            except Exception:
                r.raise_for_status()
                raise
            if j.get("errors"):
                raise LinearError(j["errors"])
            r.raise_for_status()
            return j["data"]
        raise RuntimeError("Linear: rate-limited repeatedly")

    def paginate(self, query: str, conn: str, **variables: Any) -> Iterator[Dict[str, Any]]:
        """Walk a top-level Relay connection `conn` (query must take $after)."""
        after: Optional[str] = None
        while True:
            data = self.gql(query, {**variables, "after": after})
            c = data[conn]
            for node in c.get("nodes", []):
                yield node
            if not c["pageInfo"]["hasNextPage"]:
                break
            after = c["pageInfo"]["endCursor"]


# --------------------------------------------------------------------------- queries

_PAGE = "pageInfo { hasNextPage endCursor }"
Q_TEAMS = "query($after:String){ teams(first:100, after:$after){ %s nodes { id key name issueCount } } }" % _PAGE
Q_USERS = "query($after:String){ users(first:100, after:$after){ %s nodes { id name displayName email active } } }" % _PAGE
Q_STATES = "query($after:String){ workflowStates(first:100, after:$after){ %s nodes { id name type team { key } } } }" % _PAGE
Q_ISSUES = ("query($after:String,$team:ID!){ issues(first:100, after:$after, "
            "filter:{ team:{ id:{ eq:$team } } }){ %s nodes { id identifier title description "
            "priority createdAt updatedAt completedAt canceledAt state { id name type } "
            "assignee { id displayName email } labels { nodes { id name } } } } }" % _PAGE)
Q_COMMENTS = ("query($after:String){ comments(first:100, after:$after){ %s nodes { id body createdAt "
              "issue { identifier } user { id displayName email } } } }" % _PAGE)


# --------------------------------------------------------------------------- helpers


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def _iso(ts: Optional[str]) -> Optional[str]:
    """Linear ISO (e.g. 2026-06-25T18:30:00.000Z) -> 2026-06-25T18:30:00Z."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


class Users:
    """Linear user -> {id, handle, name} (real names; handle from email, deduped)."""

    def __init__(self) -> None:
        self.by_lid: Dict[str, Dict[str, str]] = {}
        self._handles: set = set()
        self.unknown = {"id": "user-unknown", "handle": "unknown", "name": "Unknown User"}

    def resolve(self, u: Optional[Dict[str, Any]]) -> Dict[str, str]:
        if not u or not u.get("id"):
            return self.unknown
        lid = u["id"]
        if lid in self.by_lid:
            return self.by_lid[lid]
        email = u.get("email") or ""
        base = (email.split("@")[0] if email else _slug(u.get("displayName") or u.get("name") or "user")) or "user"
        handle, n = base, 2
        while handle in self._handles:
            handle, n = f"{base}{n}", n + 1
        self._handles.add(handle)
        rec = {"id": f"user-{handle}", "handle": handle, "name": u.get("displayName") or u.get("name") or handle}
        self.by_lid[lid] = rec
        return rec


# --------------------------------------------------------------------------- fetch


def fetch_workspace(client: LinearClient, team_key: Optional[str]) -> Dict[str, Any]:
    """Pull org + the chosen team's issues + comments + the people referenced.
    team_key None -> auto-pick the team with the most issues."""
    org = client.gql("{ organization { name urlKey } }")["organization"]
    teams = list(client.paginate(Q_TEAMS, "teams"))
    if not teams:
        raise LinearError("no teams visible")

    # choose team (issueCount comes straight off the teams list)
    counts = {t["key"]: (t.get("issueCount", 0), t) for t in teams}
    if team_key:
        if team_key.upper() not in {k.upper() for k in counts}:
            raise LinearError(f"team {team_key} not found; have {sorted(counts)}")
        team = next(t for k, (_, t) in counts.items() if k.upper() == team_key.upper())
    else:
        team = max(counts.values(), key=lambda x: x[0])[1]

    users_dir = Users()
    for u in client.paginate(Q_USERS, "users"):
        users_dir.resolve(u)  # pre-register everyone with a stable handle

    issues = list(client.paginate(Q_ISSUES, "issues", team=team["id"]))
    kept_idents = {i["identifier"] for i in issues}
    comments = [c for c in client.paginate(Q_COMMENTS, "comments")
                if (c.get("issue") or {}).get("identifier") in kept_idents]

    return {
        "org": org, "team": team, "issues": issues, "comments": comments,
        "users": users_dir, "team_counts": {k: v[0] for k, v in counts.items()},
    }


# --------------------------------------------------------------------- to state.json


def to_state(data: Dict[str, Any]) -> Dict[str, Any]:
    """Map the fetch into abundant-jira-clone's ticketvector state.json shape."""
    org, team, users = data["org"], data["team"], data["users"]
    issues_out: List[Dict[str, Any]] = []
    states: Dict[str, Dict[str, Any]] = {}
    labels: Dict[str, Dict[str, str]] = {}

    for it in data["issues"]:
        st = it.get("state") or {}
        sid = f"state-{_slug(st.get('name') or 'unknown')}"
        states.setdefault(sid, {"id": sid, "name": st.get("name") or "Unknown",
                                "category": CATEGORY_BY_TYPE.get(st.get("type"), "unstarted")})
        lbls = []
        for l in (it.get("labels") or {}).get("nodes", []):
            ld = {"id": f"label-{_slug(l['name'])}", "name": l["name"]}
            labels.setdefault(l["name"], ld)
            lbls.append(ld)
        assignee = users.resolve(it.get("assignee")) if it.get("assignee") else None
        issues_out.append({
            "id": f"issue-{_slug(it['identifier'])}",
            "identifier": it["identifier"],
            "title": it.get("title") or "",
            "description": it.get("description") or "",
            "state": {"id": sid, "name": st.get("name") or "Unknown"},
            "assignees": [dict(assignee)] if assignee else [],
            "labels": lbls,
            "priority": PRIORITY_BY_INT.get(it.get("priority"), "none"),
            "created_at": _iso(it.get("createdAt")),
            "updated_at": _iso(it.get("updatedAt")) or _iso(it.get("createdAt")),
            "comments_count": 0,
        })

    out_comments: Dict[str, List[Dict[str, Any]]] = {}
    for c in data["comments"]:
        ident = c["issue"]["identifier"]
        out_comments.setdefault(ident, []).append({
            "id": f"comment-{c['id']}",
            "author": dict(users.resolve(c.get("user"))),
            "body": c.get("body") or "",
            "created_at": _iso(c.get("createdAt")),
        })
    for ident, lst in out_comments.items():
        lst.sort(key=lambda x: x["created_at"] or "")
    for i in issues_out:
        i["comments_count"] = len(out_comments.get(i["identifier"], []))

    # users[]: everyone referenced (assignee/author), plus the full roster is fine.
    used = {u["id"] for i in issues_out for u in i["assignees"]} | \
           {c["author"]["id"] for lst in out_comments.values() for c in lst}
    users_list = sorted((u for u in users.by_lid.values() if u["id"] in used or True),
                        key=lambda u: u["handle"])
    if not any(u["id"] == "user-unknown" for u in users_list) and "user-unknown" in used:
        users_list.append(users.unknown)

    return {
        "workspace": org.get("urlKey") or "workspace",
        "base_url": f"https://linear.app/{org.get('urlKey') or 'workspace'}",
        "project": {
            "id": f"proj-{_slug(team['key'])}", "key": team["key"],
            "name": team.get("name") or team["key"], "archived": False,
        },
        "users": users_list,
        "states": sorted(states.values(), key=lambda s: (s["category"], s["name"])),
        "labels": sorted(labels.values(), key=lambda l: l["name"]),
        "modules": [], "cycles": [], "relations": {}, "links": {},
        "history": [], "attachments": {},
        "issues": issues_out,
        "comments": out_comments,
    }


# --------------------------------------------------------------------------- probe


def run_probe(client: LinearClient) -> List[Dict[str, Any]]:
    checks = [
        ("viewer", "{ viewer { id name } }"),
        ("organization", "{ organization { name } }"),
        ("teams", "{ teams(first:1){ nodes { key } } }"),
        ("users", "{ users(first:1){ nodes { name } } }"),
        ("issues", "{ issues(first:1){ nodes { identifier } } }"),
        ("comments", "{ comments(first:1){ nodes { id } } }"),
        ("issueHistory", "{ issues(first:1){ nodes { history(first:1){ nodes { createdAt } } } } }"),
    ]
    out = []
    for name, q in checks:
        try:
            client.gql(q)
            out.append({"method": name, "ok": True, "error": None})
        except Exception as e:
            out.append({"method": name, "ok": False, "error": str(e)[:120]})
    return out


def build_report(probe, state, data) -> Dict[str, Any]:
    by = {p["method"]: p["ok"] for p in probe}
    gaps = []
    if by.get("comments") is False:
        gaps.append("comments denied -> no issue discussion in the corpus.")
    if by.get("issueHistory") is False:
        gaps.append("issueHistory denied -> mutable-state slice_as_of(T) replay not possible.")
    sufficient = bool(by.get("viewer") and by.get("issues") and not [g for g in gaps if "comments" in g])
    return {
        "org": data["org"], "team": data["team"]["key"], "team_counts": data["team_counts"],
        "counts": {"issues": len(state["issues"]), "comments": sum(len(v) for v in state["comments"].values()),
                   "users": len(state["users"]), "states": len(state["states"]), "labels": len(state["labels"])},
        "access_matrix": probe, "gaps": gaps, "sufficient_for_task_gen": sufficient,
        "verdict": ("SUFFICIENT for task-gen with this Linear key." if sufficient
                    else "INSUFFICIENT -- see gaps."),
    }


def render_report_md(rep: Dict[str, Any]) -> str:
    L = ["# Linear export -- sufficiency report", "",
         f"**Org:** {rep['org'].get('name')} (`{rep['org'].get('urlKey')}`)  ",
         f"**Team:** {rep['team']}  (all teams: {rep['team_counts']})  ",
         f"**Counts:** {rep['counts']['issues']} issues, {rep['counts']['comments']} comments, "
         f"{rep['counts']['users']} users, {rep['counts']['states']} states, {rep['counts']['labels']} labels  ",
         "", "## Access matrix", "", "| field | ok | error |", "|---|---|---|"]
    for p in rep["access_matrix"]:
        L.append(f"| `{p['method']}` | {'yes' if p['ok'] else 'no'} | {p.get('error') or ''} |")
    L += ["", "## Gaps"] + ([f"- {g}" for g in rep["gaps"]] or ["- none"])
    L += ["", "## Verdict", "", f"**{rep['verdict']}**", ""]
    return "\n".join(L)


# --------------------------------------------------------------------------- CLI


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="spoink.linear_export", description="Read-only Linear export -> jira-clone state.json.")
    ap.add_argument("--team", default=None, help="team key (e.g. ABT); default = team with most issues")
    ap.add_argument("--out", default="state.json", help="state.json to write")
    ap.add_argument("--report", default=None, help="write sufficiency report (.md; .json alongside)")
    ap.add_argument("--token-env", default="LINEAR_API_KEY", help="env var holding the Linear key")
    args = ap.parse_args(argv)

    key = os.environ.get(args.token_env)
    if not key:
        print(f"error: set {args.token_env} to a Linear API key (not passed on the CLI)", file=sys.stderr)
        return 2

    client = LinearClient(key)
    try:
        data = fetch_workspace(client, args.team)
        probe = run_probe(client)
        state = to_state(data)
        rep = build_report(probe, state, data)
    finally:
        client.close()

    Path = __import__("pathlib").Path
    Path(args.out).write_text(json.dumps(state, indent=2, ensure_ascii=False))
    print(json.dumps({"out": args.out, "team": rep["team"], **rep["counts"],
                      "sufficient": rep["sufficient_for_task_gen"]}))
    if args.report:
        md = args.report if args.report.endswith(".md") else args.report + ".md"
        Path(md).write_text(render_report_md(rep))
        Path(md[:-3] + ".json").write_text(json.dumps(rep, indent=2))
        print(f"report: {md}", file=sys.stderr)
    return 0 if rep["sufficient_for_task_gen"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
