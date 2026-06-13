#!/usr/bin/env python3
"""Convert one APEX-SWE / apex-swe-variants observability task's fixture data into the
three abundant-clone seed files: ticketvector state.json, slack scraped.json, gauge
state.json.

The repo, golden.patch, test.patch and test_metadata.json are NOT touched here — they
pass through verbatim (grading is clone-independent). See tools/SCHEMAS.md for the
target shapes.

Usage:
    apex_to_clones.py --from-variant <dir> --out <env_data_dir> \
        --workspace meridian --project-key OPS [--project-name "..."] [--now <iso>]

`--from-variant` points at the variant's inner data dir (the one containing
data/plane, data/mattermost, data/loki). Individual files can be overridden with
--plane / --mattermost / --loki / --grafana-datasource.
"""
import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Plane priority -> ticketvector priority
PRIORITY_MAP = {"critical": "urgent", "urgent": "urgent", "high": "high",
                "medium": "medium", "low": "low", "none": "none", "": "none"}

# Plane state -> ticketvector (id, name, category)
STATES = [
    ("state-backlog", "Backlog", "unstarted"),
    ("state-todo", "Todo", "unstarted"),
    ("state-progress", "In Progress", "started"),
    ("state-review", "In Review", "started"),
    ("state-done", "Done", "completed"),
    ("state-canceled", "Canceled", "cancelled"),
]
PLANE_STATE_MAP = {"open": "Todo", "in_progress": "In Progress", "closed": "Done",
                   "done": "Done", "": "Todo"}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _ns_to_iso(ts_ns: str) -> str:
    secs = int(ts_ns) / 1_000_000_000
    return datetime.fromtimestamp(secs, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _author_username(author) -> str:
    if isinstance(author, dict):
        return author.get("username") or author.get("global_name") or "unknown"
    return str(author)


def convert_plane(issues, *, workspace, key, name, now, chat_authors):
    """Plane issues[] -> ticketvector state.json. Issues are assigned to `agent` so
    `linear issue mine` surfaces them."""
    label_names = sorted({lbl for iss in issues for lbl in iss.get("labels", [])})
    labels = [{"id": f"label-{_slug(n)}", "name": n} for n in label_names]
    label_by_name = {l["name"]: l for l in labels}

    users = [{"id": "user-agent", "handle": "agent", "name": "Agent User"}]
    for handle in sorted(chat_authors):
        if handle != "agent":
            users.append({"id": f"user-{_slug(handle)}", "handle": handle,
                          "name": handle.capitalize()})

    out_issues = []
    for iss in issues:
        num = iss.get("number", len(out_issues) + 1)
        identifier = f"{key}-{num}"
        state_name = PLANE_STATE_MAP.get(str(iss.get("state", "open")).lower(), "Todo")
        state = next(s for s in STATES if s[1] == state_name)
        created = iss.get("createdAt") or iss.get("created_at") or now
        out_issues.append({
            "id": f"issue-{_slug(key)}-{num}",
            "identifier": identifier,
            "title": iss.get("title", ""),
            "description": iss.get("body", iss.get("description", "")),
            "state": {"id": state[0], "name": state[1]},
            "assignees": [{"id": "user-agent", "handle": "agent", "name": "Agent User"}],
            "labels": [label_by_name[n] for n in iss.get("labels", []) if n in label_by_name],
            "priority": PRIORITY_MAP.get(str(iss.get("priority", "")).lower(), "none"),
            "created_at": created,
            "updated_at": iss.get("updated_at", created),
            "comments_count": 0,
        })

    return {
        "workspace": workspace,
        "base_url": f"https://linear.local/{workspace}",
        "project": {"id": "proj-ops", "key": key, "name": name, "archived": False},
        "users": users,
        "states": [{"id": i, "name": n, "category": c} for i, n, c in STATES],
        "labels": labels,
        "modules": [],
        "cycles": [],
        "relations": {},
        "links": {},
        "history": [],
        "attachments": {},
        "issues": out_issues,
        "comments": {},
    }


def convert_mattermost(payload):
    """Mattermost scraped -> slack scraped (flatten author object to username string)."""
    messages = []
    for msg in payload.get("messages", []):
        messages.append({
            "channel": msg.get("channel", "general"),
            "author": _author_username(msg.get("author", "unknown")),
            "content": msg.get("content", msg.get("text", "")),
            "timestamp": msg.get("timestamp", ""),
        })
    return {"messages": messages}


def convert_loki(loki, *, workspace, datasource_uid, service_hint):
    """Loki streams -> gauge state.json. Each stream becomes a fixture keyed by its
    selector; gauge's filter engine then serves any {labels}|="substr" query over all
    entries. Timestamps are kept deterministic (no wall-clock rewrite)."""
    fixtures = {}
    all_entries = []
    last_ts = None
    for stream in loki.get("streams", []):
        s_labels = {str(k): str(v) for k, v in stream.get("stream", {}).items()}
        selector = "{" + ",".join(f'{k}="{v}"' for k, v in s_labels.items()) + "}"
        entries = []
        for ts_ns, line in stream.get("values", []):
            ts = _ns_to_iso(ts_ns)
            last_ts = ts if last_ts is None or ts > last_ts else last_ts
            entry = {"ts": ts, "labels": s_labels, "line": line}
            entries.append(entry)
            all_entries.append(entry)
        fixtures.setdefault(selector, {"entries": []})["entries"].extend(entries)

    now = (datetime.strptime(last_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
           + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ") if last_ts else \
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    panel = {
        "id": 1,
        "title": f"{service_hint} logs",
        "type": "logs",
        "datasource_uid": datasource_uid,
        "targets": [{"datasource_uid": datasource_uid,
                     "expr": "{" + f'service="{service_hint}"' + "}"}],
    }
    return {
        "meta": {"workspace": workspace, "now": now},
        "users": [{"id": "u-agent", "login": "agent", "name": "Agent User"}],
        "datasources": [
            {"uid": datasource_uid, "name": f"{service_hint} Loki", "type": "loki",
             "mode": "embedded", "health": "ok"},
            {"uid": "prom-default", "name": f"{service_hint} Prometheus",
             "type": "prometheus", "mode": "embedded", "health": "ok"},
        ],
        "dashboards": [{
            "uid": f"dash-{_slug(service_hint)}",
            "title": f"{service_hint} incident",
            "folder": "Incidents",
            "tags": ["incident", service_hint],
            "variables": [],
            "panels": [panel],
        }],
        "alerts": [],
        "metrics": {"queries": {}},
        "logs": {"queries": fixtures},
        "alert_instances": [],
        "alert_state_history": [],
        "annotations": [],
        "mutation_log": [],
    }


def apply_spec(tv, slack, spec, *, now):
    """Merge a per-task overlay onto the converted seeds. Used to make an
    implementation contract discoverable when the hidden F2P test imports exact
    private symbols a fix cannot otherwise infer (a realistic on-call handoff note).

    spec = {
      "ticket_comments": [{"identifier"?: "OPS-1", "author": "maya", "body": "..."}],
      "slack_messages":  [{"channel": "...", "author": "...", "content": "...", "timestamp": "..."}]
    }
    """
    default_id = tv["issues"][0]["identifier"] if tv.get("issues") else None
    handles = {u["handle"] for u in tv["users"]}
    issue_by_id = {i["identifier"]: i for i in tv["issues"]}

    for n, c in enumerate(spec.get("ticket_comments", []), 1):
        ident = c.get("identifier", default_id)
        author = c.get("author", "agent")
        if author not in handles:
            tv["users"].append({"id": f"user-{_slug(author)}", "handle": author,
                                "name": author.capitalize()})
            handles.add(author)
        tv["comments"].setdefault(ident, []).append({
            "id": f"comment-{_slug(ident)}-{n}",
            "author": {"id": f"user-{_slug(author)}", "handle": author, "name": author.capitalize()},
            "body": c["body"],
            "created_at": c.get("created_at", now),
        })
        if ident in issue_by_id:
            issue_by_id[ident]["comments_count"] = len(tv["comments"][ident])

    for m in spec.get("slack_messages", []):
        slack["messages"].append({
            "channel": m.get("channel", "sre-oncall"),
            "author": _author_username(m.get("author", "unknown")),
            "content": m.get("content", ""),
            "timestamp": m.get("timestamp", ""),
        })


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-variant", help="dir containing data/plane, data/mattermost, data/loki")
    ap.add_argument("--plane")
    ap.add_argument("--mattermost")
    ap.add_argument("--loki")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workspace", default="meridian")
    ap.add_argument("--project-key", default="OPS")
    ap.add_argument("--project-name", default="On-call Incidents")
    ap.add_argument("--service", default="service", help="service hint for gauge labels/dashboard")
    ap.add_argument("--spec", default=None, help="optional overlay JSON (ticket_comments / slack_messages)")
    ap.add_argument("--now", default=None)
    args = ap.parse_args()

    base = Path(args.from_variant) if args.from_variant else None
    plane_p = args.plane or (base / "data/plane/issues.json")
    mm_p = args.mattermost or (base / "data/mattermost/scraped.json")
    loki_p = args.loki or (base / "data/loki/logs.json")

    issues = _load(plane_p)
    mm = _load(mm_p)
    loki = _load(loki_p)
    now = args.now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    chat_authors = {_author_username(m.get("author", "")) for m in mm.get("messages", [])}

    tv = convert_plane(issues, workspace=args.workspace, key=args.project_key,
                       name=args.project_name, now=now, chat_authors=chat_authors)
    slack = convert_mattermost(mm)
    gauge = convert_loki(loki, workspace=args.workspace, datasource_uid="loki",
                         service_hint=args.service)

    if args.spec:
        apply_spec(tv, slack, _load(args.spec), now=now)

    out = Path(args.out)
    for sub, data in [("ticketvector/state.json", tv), ("slack/scraped.json", slack),
                      ("gauge/state.json", gauge)]:
        p = out / sub
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {p}")

    print(f"  ticketvector: {len(tv['issues'])} issues, {len(tv['users'])} users")
    print(f"  slack: {len(slack['messages'])} messages")
    nlog = sum(len(v['entries']) for v in gauge['logs']['queries'].values())
    print(f"  gauge: {nlog} log entries across {len(gauge['logs']['queries'])} streams")


if __name__ == "__main__":
    main()
