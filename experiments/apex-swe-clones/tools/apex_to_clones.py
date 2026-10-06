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


def convert_plane(issues, *, workspace, key, name, now, chat_authors, assign_agent=True):
    """Plane issues[] -> ticketvector state.json.

    `issues` is the canonical shape from normalize_issues: each has number, title,
    body, labels (list[str]), priority, state, createdAt, and optional assignee_login.
    When assign_agent is True (variant model) every issue is assigned to `agent` so
    `linear issue mine` surfaces it. When False (exact-APEX model, a realistic full
    tracker the agent must SEARCH) real assignees are preserved and `mine` stays empty."""
    label_names = sorted({lbl for iss in issues for lbl in iss.get("labels", [])})
    labels = [{"id": f"label-{_slug(n)}", "name": n} for n in label_names]
    label_by_name = {l["name"]: l for l in labels}

    users = {"agent": {"id": "user-agent", "handle": "agent", "name": "Agent User"}}

    def _user(handle):
        h = _slug(handle) or "unknown"
        users.setdefault(h, {"id": f"user-{h}", "handle": h, "name": handle})
        return users[h]

    for handle in sorted(chat_authors):
        _user(handle)

    out_issues = []
    for iss in issues:
        num = iss.get("number", len(out_issues) + 1)
        identifier = f"{key}-{num}"
        state_name = PLANE_STATE_MAP.get(str(iss.get("state", "open")).lower(), "Todo")
        state = next(s for s in STATES if s[1] == state_name)
        created = iss.get("createdAt") or iss.get("created_at") or now
        if assign_agent:
            assignees = [dict(users["agent"])]
        elif iss.get("assignee_login"):
            assignees = [dict(_user(iss["assignee_login"]))]
        else:
            assignees = []
        out_issues.append({
            "id": f"issue-{_slug(key)}-{num}",
            "identifier": identifier,
            "title": iss.get("title", ""),
            "description": iss.get("body", iss.get("description", "")),
            "state": {"id": state[0], "name": state[1]},
            "assignees": assignees,
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
        "users": list(users.values()),
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
    """Loki streams (variant logs.json) -> gauge state.json. Each stream becomes a
    fixture keyed by its selector; gauge's filter engine then serves any {labels}|="substr"
    query over all entries. Timestamps are kept deterministic (no wall-clock rewrite)."""
    fixtures = {}
    last_ts = None
    for stream in loki.get("streams", []):
        s_labels = {str(k): str(v) for k, v in stream.get("stream", {}).items()}
        selector = "{" + ",".join(f'{k}="{v}"' for k, v in s_labels.items()) + "}"
        entries = []
        for ts_ns, line in stream.get("values", []):
            ts = _ns_to_iso(ts_ns)
            last_ts = ts if last_ts is None or ts > last_ts else last_ts
            entries.append({"ts": ts, "labels": s_labels, "line": line})
        fixtures.setdefault(selector, {"entries": []})["entries"].extend(entries)
    return _assemble_gauge(fixtures, last_ts, workspace=workspace,
                           datasource_uid=datasource_uid, service_hint=service_hint)


# Raw-log level token (first ~40 chars). Handles "[INFO]", "INFO ", "level=ERROR".
_LEVEL_RE = re.compile(r"\b(TRACE|DEBUG|INFO|WARNING|WARN|ERROR|CRIT|CRITICAL|FATAL)\b", re.I)
# Absolute "YYYY-MM-DD HH:MM:SS" timestamp (Django-style); other formats fall back to synth.
_ABS_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})")


def convert_loki_log(text, *, workspace, datasource_uid, service_hint):
    """Raw APEX data/loki/*.log -> gauge state.json. Synthesizes {service,level} labels so
    gauge's filter engine serves {service="x"} |= "..." queries. Absolute timestamps are
    parsed when present (e.g. Django logs); otherwise lines get a deterministic sequential ts
    so the default time window includes them.

    Multi-line records (tracebacks, multi-line messages) are folded into their parent entry:
    a line without a leading timestamp is treated as a CONTINUATION of the preceding
    real-timestamped record (inheriting its ts/level), not a new entry. Without this, a
    traceback gets shredded into N separate entries each stamped with the synthetic `base`
    date, stranding them months away from the error they belong to."""
    lines = [ln.rstrip("\n") for ln in text.splitlines() if ln.strip()]
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    entries = []
    last_ts = None
    fold_into = None  # index of the current real-timestamped entry to fold continuations into
    for i, line in enumerate(lines):
        head = line[:48]
        m = _ABS_TS_RE.search(head)
        if m is None and fold_into is not None:
            entries[fold_into]["line"] += "\n" + line
            continue
        lvl = _LEVEL_RE.search(head)
        level = (lvl.group(1).upper() if lvl else "INFO")
        level = {"WARN": "WARNING", "CRIT": "CRITICAL"}.get(level, level)
        if m:
            ts = f"{m.group(1)}T{m.group(2)}Z"
        else:
            ts = (base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if last_ts is None or ts > last_ts:
            last_ts = ts
        entries.append({"ts": ts, "labels": {"service": service_hint, "level": level.lower()},
                        "line": line})
        fold_into = (len(entries) - 1) if m else None
    selector = "{" + f'service="{service_hint}"' + "}"
    fixtures = {selector: {"entries": entries}}
    return _assemble_gauge(fixtures, last_ts, workspace=workspace,
                           datasource_uid=datasource_uid, service_hint=service_hint)


def _assemble_gauge(fixtures, last_ts, *, workspace, datasource_uid, service_hint):
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


def _clean_matrix_user(s):
    """@killefiz:matrix.org -> killefiz ; falls back to the raw string."""
    s = str(s or "unknown")
    return s.lstrip("@").split(":")[0] or "unknown"


def normalize_issues(raw):
    """Detect the issue format and return (canonical_issues, assign_agent).

    - Variant format: small list of {number,title,body,labels:[str],priority,state:"open"}.
      -> assign_agent True (the single ticket IS the spec; `linear issue mine` finds it).
    - Exact-APEX (real GitHub dump): list with author{login}, state OPEN/CLOSED,
      labels:[{name}]. -> assign_agent False (a realistic full tracker to SEARCH; the task
      spec lives in the instruction). Authors/assignees preserved as real handles."""
    if not raw:
        return [], True
    sample = raw[0]
    sample_labels = sample.get("labels") or []
    # Real GitHub dump: author is an object and/or labels are objects. The variant
    # format has no author and string labels (its lowercase state="open" must NOT match).
    is_github = isinstance(sample.get("author"), dict) or (
        bool(sample_labels) and isinstance(sample_labels[0], dict))
    if not is_github:
        return raw, True
    out = []
    for iss in raw:
        labels = [l.get("name") if isinstance(l, dict) else str(l) for l in iss.get("labels", [])]
        assignees = iss.get("assignees") or []
        a0 = assignees[0] if assignees else None
        assignee_login = (a0.get("login") if isinstance(a0, dict) else a0) if a0 else None
        out.append({
            "number": iss.get("number"),
            "title": iss.get("title", ""),
            "body": iss.get("body", "") or "",
            "labels": [l for l in labels if l],
            "priority": "none",
            "state": "closed" if str(iss.get("state", "")).upper() == "CLOSED" else "open",
            "createdAt": iss.get("createdAt") or iss.get("created_at"),
            "assignee_login": _slug(assignee_login) if assignee_login else None,
        })
    return out, False


def normalize_mattermost(raw):
    """Detect chat format and return canonical {messages:[{channel,author,content,timestamp}]}.

    APEX uses a different chat export per task; we auto-detect:
    - Variant: already {messages:[{channel,author,content,timestamp}]}.
    - Matrix export: events with sender/room_id/content{body,msgtype}/origin_server_ts.
    - Discord export: list of messages with type(int)/author{username}/channel_name/content/timestamp."""
    msgs = raw.get("messages", []) if isinstance(raw, dict) else raw
    if not msgs:
        return {"messages": []}
    s = msgs[0]

    # Matrix export
    if "sender" in s or "room_id" in s:
        room_names = {m.get("room_id"): (m.get("content") or {}).get("name")
                      for m in msgs if m.get("type") == "m.room.name"}
        out = []
        for m in msgs:
            if m.get("type") != "m.room.message":
                continue
            c = m.get("content") or {}
            if c.get("msgtype") not in (None, "m.text", "m.notice"):
                continue
            body = c.get("body")
            if not body:
                continue
            channel = room_names.get(m.get("room_id")) or str(m.get("room_id", "chat"))
            ts_ms = m.get("origin_server_ts")
            ts = (datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
                  if isinstance(ts_ms, (int, float)) else "")
            out.append({"channel": _slug(channel) or "chat", "author": _clean_matrix_user(m.get("sender")),
                        "content": body, "timestamp": ts})
        return {"messages": out}

    # Discord export (type 0=default, 19=reply carry user text; others are system events)
    if "channel_name" in s or ("type" in s and isinstance(s.get("author"), dict)):
        out = []
        for m in msgs:
            if m.get("type") not in (0, 19):
                continue
            body = (m.get("content") or "").strip()
            if not body:
                continue
            a = m.get("author") or {}
            author = (a.get("username") or a.get("global_name") or a.get("name")) if isinstance(a, dict) else str(a)
            out.append({"channel": _slug(m.get("channel_name") or "chat") or "chat",
                        "author": author or "unknown",
                        "content": m.get("content", ""),
                        "timestamp": m.get("timestamp", "")})
        return {"messages": out}

    # Variant format (already canonical; convert_mattermost flattens any author objects)
    return convert_mattermost({"messages": msgs})


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
    loki_p = Path(args.loki) if args.loki else (base / "data/loki/logs.json")

    raw_issues = _load(plane_p)
    raw_mm = _load(mm_p)
    now = args.now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    issues, assign_agent = normalize_issues(raw_issues)
    slack = normalize_mattermost(raw_mm)
    chat_authors = {m["author"] for m in slack["messages"]}

    tv = convert_plane(issues, workspace=args.workspace, key=args.project_key,
                       name=args.project_name, now=now, chat_authors=chat_authors,
                       assign_agent=assign_agent)

    # Loki: raw APEX *.log (one line per row) or variant streams JSON.
    if str(loki_p).endswith(".log"):
        gauge = convert_loki_log(Path(loki_p).read_text(encoding="utf-8", errors="replace"),
                                 workspace=args.workspace, datasource_uid="loki",
                                 service_hint=args.service)
    else:
        gauge = convert_loki(_load(loki_p), workspace=args.workspace,
                             datasource_uid="loki", service_hint=args.service)

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
