"""Linear clone seed viewer.

The multiverse `abundant-jira-clone/linear/server.py` serves a Linear-faithful GraphQL surface
(`{issues,teams,viewer,workflowStates,...}`) over the SAME ticketvector `state.json` the
jira-gateway bakes — same data, a different (Linear-shaped) API surface. This adapter mirrors that
server's `_build(state)` mapping exactly (priority int scale, workflow-state `type` buckets, one
team per project) so the seed viewer's Linear tile renders the identical shape a real
`linear-mcp`/GraphQL client would see. Read-only.

Accepts the same inputs as the Jira tile: a local `state.json`, or a `jira-gateway` image's baked
`/var/lib/ticketvector/state.json` (the Linear GraphQL service is typically built ad hoc per-task
via `linear/build.sh <state.json> <tag>` rather than published as a standing image, so we read the
same corpus jira-gateway ships)."""
from __future__ import annotations

import json
from typing import Any

from adapters.fileseed import FileSeedAdapter

# ticketvector state category -> Linear workflowState.type (exact PRIORITY/TYPE maps from
# abundant-jira-clone/linear/server.py, so the viewer matches the real GraphQL shape byte-for-byte).
_PRIORITY_INT = {"none": 0, "urgent": 1, "high": 2, "medium": 3, "low": 4}
_PRIORITY_LABEL = {0: "No priority", 1: "Urgent", 2: "High", 3: "Medium", 4: "Low"}
_TYPE_FOR = {"unstarted": "unstarted", "started": "started", "completed": "completed",
             "cancelled": "canceled", "backlog": "backlog", "triage": "triage"}
# the six real Linear status-group buckets, in Linear's own default board order
_TYPE_ORDER = ["triage", "backlog", "unstarted", "started", "completed", "canceled"]

IMAGE_STATE_PATH = "/var/lib/ticketvector/state.json"


class LinearAdapter(FileSeedAdapter):
    id = "linear"
    display_name = "Linear"
    status = "active"
    ui_module = "linear"
    sample_files = ("linear.state.json",)
    image_substrings = ("linear-gateway", "linear-service", "jira-gateway")
    image_state_paths = (IMAGE_STATE_PATH,)

    def _user(self, u: dict | None) -> dict | None:
        if not u:
            return None
        handle = u.get("handle") or u.get("id", "user")
        name = u.get("name") or handle
        return {"id": u.get("id"), "name": name, "displayName": name,
                "email": f"{handle}@abundant.ai", "avatarLetter": name[0].upper() if name else "?"}

    def _parse(self, raw: str, path: str) -> dict[str, Any]:
        d = json.loads(raw)
        proj = d.get("project") or {}
        team = {"id": proj.get("id", "team-1"), "key": proj.get("key", "TEAM"),
                "name": proj.get("name", proj.get("key", "Team")), "issueCount": len(d.get("issues") or [])}

        users = [self._user(u) for u in (d.get("users") or [])]
        by_uid = {u["id"]: u for u in users if u}

        type_by_state_id = {s["id"]: _TYPE_FOR.get(s.get("category"), "unstarted")
                             for s in (d.get("states") or [])}
        states = [{"id": s["id"], "name": s["name"],
                   "type": _TYPE_FOR.get(s.get("category"), "unstarted")}
                  for s in (d.get("states") or [])]
        # one representative state per type-bucket (for the board column header + color dot)
        state_by_type: dict[str, dict] = {}
        for s in states:
            state_by_type.setdefault(s["type"], s)

        comments_by_ident = d.get("comments") or {}
        issues = []
        for i in d.get("issues") or []:
            st = i.get("state") or {}
            assignee = (i.get("assignees") or [None])[0]
            prio = _PRIORITY_INT.get(i.get("priority"), 0)
            cmts = [
                {"id": c.get("id"), "body": c.get("body", ""), "createdAt": c.get("created_at"),
                 "author": by_uid.get((c.get("author") or {}).get("id")) or self._user(c.get("author"))}
                for c in comments_by_ident.get(i.get("identifier"), [])
            ]
            issues.append({
                "id": i.get("id"), "identifier": i.get("identifier"), "title": i.get("title"),
                "description": i.get("description"),
                "priority": prio, "priorityLabel": _PRIORITY_LABEL[prio],
                "createdAt": i.get("created_at"), "updatedAt": i.get("updated_at"),
                "state": {"id": st.get("id"), "name": st.get("name"),
                          "type": type_by_state_id.get(st.get("id"), "unstarted")},
                "assignee": self._user(assignee) if assignee else None,
                "team": team,
                "labels": [{"id": l.get("id"), "name": l.get("name")} for l in (i.get("labels") or [])],
                "comments": cmts,
            })

        # group into the real Linear status buckets, ordered + counted like the app's default view
        groups = []
        for t in _TYPE_ORDER:
            members = [iss for iss in issues if iss["state"]["type"] == t]
            if not members and t not in state_by_type:
                continue
            groups.append({
                "type": t,
                "name": (state_by_type.get(t) or {}).get("name") or t.capitalize(),
                "issues": sorted(members, key=lambda x: -x["priority"] if x["priority"] else 99),
            })

        org = {"name": proj.get("name") or d.get("workspace") or "Workspace",
               "urlKey": d.get("workspace") or "workspace"}
        return {
            "org": org,
            "team": team,
            "users": [u for u in users if u],
            "groups": groups,
            "labels": [{"id": l.get("id"), "name": l.get("name")} for l in (d.get("labels") or [])],
            "stats": {
                "issues": len(issues),
                "users": len([u for u in users if u]),
                "in_progress": sum(1 for i in issues if i["state"]["type"] == "started"),
                "done": sum(1 for i in issues if i["state"]["type"] == "completed"),
            },
        }
