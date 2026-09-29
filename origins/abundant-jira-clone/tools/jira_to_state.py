#!/usr/bin/env python3
"""Convert a real Jira native (OFBiz-style) XML entity backup into a ticketvector
single-project `state.json` (the runtime seed the ticketvector service serves via
WORLD_ISSUES_STATE_FILE; the same Plane/Linear-flavored shape produced by world_issues).

The Jira export is one big XML document where every entity is a sibling element
(`<Issue .../>`, `<Action .../>`, `<Project .../>`, ...). Long text (issue
descriptions, comment bodies) is either an inline attribute on a self-closing row
OR a nested child element on a non-self-closing row. The file is ~142 MB, so we
stream with `iterparse` and clear elements as we go.

Anonymization is DUAL and must be reconciled into one person registry:
  * The User/ApplicationUser tables key people as `PERSON_<n>_JIRA_KEY`.
  * Issue/comment author/reporter/assignee/creator fields reference people as BOTH
    `PERSON_<n>_JIRA_KEY` AND orphaned `[PERSON_NAME_<n>]` (no User row at all).
We key the registry on the shared PERSON_NAME number when present (`name:<n>`) and
fall back to the JIRA_KEY number otherwise (`jira:<n>`). Each person gets a stable,
deterministic synthetic display name + handle, hashed on the registry key, mirroring
import_export._assign_synthetic_names. (`name:<n>` is the cross-system id that also
appears in the Slack corpus, so keying on it makes identities unifiable later.)

Usage:
    python tools/jira_to_state.py --entities /path/entities.xml --project ENG \
        --out state.json [--max-issues N]
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from xml.etree.ElementTree import iterparse

# ---------------------------------------------------------------------------
# Synthetic-name pools (mirrors abundant-slack-clone import_export._assign_synthetic_names)
# ---------------------------------------------------------------------------
FIRST_NAMES = [
    "Alex", "Jordan", "Sam", "Taylor", "Morgan", "Casey", "Riley", "Avery", "Quinn", "Reese",
    "Devon", "Harper", "Rowan", "Parker", "Emerson", "Skyler", "Cameron", "Drew", "Hayden", "Logan",
    "Maya", "Noah", "Priya", "Diego", "Wei", "Sofia", "Omar", "Hana", "Lucas", "Nadia",
    "Ivan", "Leila", "Kenji", "Amara", "Felix", "Yara", "Mateo", "Zoe", "Arjun", "Elena",
]
LAST_NAMES = [
    "Avila", "Brooks", "Chen", "Diaz", "Okafor", "Fischer", "Gupta", "Haddad", "Ibrahim", "Jensen",
    "Kowalski", "Lopez", "Martin", "Nakamura", "Owusu", "Petrov", "Quintero", "Reyes", "Singh", "Tan",
    "Ueda", "Vargas", "Walsh", "Xu", "Yousef", "Zhang", "Andersen", "Bianchi", "Costa", "Duval",
    "Eriksson", "Ferreira", "Goldberg", "Hassan", "Ivanov", "Johansson", "Kim", "Larsson", "Mensah", "Novak",
]

# Extract the person number from any of the anonymizer token shapes.
_NAME_RE = re.compile(r"\[PERSON_NAME_(\d+)\]")
_JIRA_RE = re.compile(r"PERSON_(\d+)_(?:JIRA_KEY|NAME|EMAIL)")

# Jira's built-in StatusCategory ids -> ticketvector category. There is no separate
# StatusCategory entity in this dump; these are the stable Jira defaults:
#   1 = No Category (undefined), 2 = To Do (new), 3 = Done (complete), 4 = In Progress
STATUS_CATEGORY_MAP = {
    "1": "unstarted",
    "2": "unstarted",
    "3": "completed",
    "4": "started",
}
# Status/resolution names that mean the work was abandoned, not completed.
CANCELLED_RESOLUTIONS = {"won't do", "wont do", "duplicate", "cannot reproduce",
                         "declined", "not a bug", "abandoned", "invalid"}
CANCELLED_STATUS_HINTS = {"cancelled", "canceled", "abandoned", "won't do", "declined"}

# Jira priority name -> ticketvector priority. This export's scheme is P0..P4 + Blocked,
# plus the classic Highest..Lowest. Anything unknown -> none.
PRIORITY_MAP = {
    "blocked": "urgent", "blocker": "urgent", "highest": "urgent", "p0": "urgent",
    "high": "high", "p1": "high",
    "medium": "medium", "p2": "medium",
    "low": "low", "p3": "low",
    "lowest": "none", "p4": "none", "trivial": "none",
}


def _strip_ns(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _person_key(raw):
    """Map a raw anonymized person reference to a stable registry key.

    `[PERSON_NAME_0001]` -> `name:1` (cross-system id, shared with Slack corpus).
    `PERSON_7780_JIRA_KEY` / `PERSON_7780_NAME` -> `jira:7780`.
    Anything else (real-looking handle) -> `raw:<lowered>`.
    """
    if not raw:
        return None
    m = _NAME_RE.search(raw)
    if m:
        return f"name:{int(m.group(1))}"
    m = _JIRA_RE.search(raw)
    if m:
        return f"jira:{int(m.group(1))}"
    return f"raw:{raw.strip().lower()}"


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def _iso(ts):
    """`2022-09-29 02:48:47.336` (no tz, assumed UTC) -> `2022-09-29T02:48:47Z`."""
    if not ts:
        return None
    ts = ts.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return None


class PersonRegistry:
    """Unifies the dual anonymization into one set of named users. Each registry key
    gets ONE stable synthetic name + handle, hashed on the key so it's reproducible."""

    def __init__(self, registry_path=None):
        self.by_key = {}          # registry_key -> user dict {id, handle, name}
        self._used_handles = set()
        # Shared cross-clone identity registry (abundant-identity): number -> canonical record. When
        # present, a person resolves to the SAME name/handle as the Slack corpus (cross-clone unify).
        self._reg = {}
        if registry_path and os.path.isfile(registry_path):
            with open(registry_path, encoding="utf-8") as fh:
                self._reg = {k: v for k, v in json.load(fh).items() if k != "_meta"}
        # Seed an "unknown" fallback so every reference resolves to a real users[] entry.
        self.unknown = {"id": "user-unknown", "handle": "unknown", "name": "Unknown User"}
        self.by_key["__unknown__"] = self.unknown
        self._used_handles.add("unknown")

    def resolve(self, raw):
        key = _person_key(raw)
        if key is None:
            return self.unknown
        if key in self.by_key:
            return self.by_key[key]
        rec = self._from_registry(key) or self._make(key)
        self.by_key[key] = rec
        return rec

    def _from_registry(self, key):
        # key is "name:<n>" or "jira:<n>"; look the bare number up in the shared registry so the
        # person gets the canonical (Slack-matching) name/handle.
        num = key.split(":", 1)[1] if ":" in key else None
        r = self._reg.get(num)
        if not r:
            return None
        handle = r["handle"]
        self._used_handles.add(handle)
        return {"id": f"user-{handle}", "handle": handle, "name": r["real_name"]}

    def _make(self, key):
        h = int(hashlib.sha1(key.encode()).hexdigest(), 16)
        first = FIRST_NAMES[h % len(FIRST_NAMES)]
        last = LAST_NAMES[(h // len(FIRST_NAMES)) % len(LAST_NAMES)]
        name = f"{first} {last}"
        base = f"{first.lower()}.{last.lower()}"
        handle, n = base, 2
        while handle in self._used_handles:
            handle, n = f"{base}{n}", n + 1
        self._used_handles.add(handle)
        return {"id": f"user-{handle}", "handle": handle, "name": name}

    def users(self):
        # Stable order; keep "unknown" only if something actually fell back to it.
        return sorted(self.by_key.values(), key=lambda u: u["handle"])


def _text_field(elem, attr, child_tag):
    """Read a long-text field: inline attribute if present, else nested child element.
    ElementTree already XML-unescapes both attribute values and element text."""
    val = elem.get(attr)
    if val is not None:
        return val
    for child in elem:
        if _strip_ns(child.tag) == child_tag:
            return (child.text or "").strip()
    return None


def convert(entities_path, project_key, max_issues=None, registry_path=None):
    project_key = project_key.upper()

    # Lookup tables, built on the first streaming pass over the (whole) document.
    projects = {}        # id -> {key,name}
    statuses = {}        # id -> {name, category}
    priorities = {}      # id -> name
    resolutions = {}     # id -> name
    registry = PersonRegistry(registry_path)

    issues = []          # collected, project-filtered
    issue_id_to_ident = {}   # jira issue id -> "ENG-2016" (for comment grouping)
    labels_by_issue = {}     # jira issue id -> set(label)
    comments = {}            # identifier -> [comment dicts]
    moved_keys = {}          # old key -> issue id (MovedIssueKey)

    stats = {"issues_seen": 0, "issues_kept": 0, "comments_seen": 0,
             "comments_kept": 0, "labels_seen": 0, "links_seen": 0,
             "malformed": 0, "rows": 0}

    # We need lookups (Project/Status/Priority/Resolution) BEFORE we finalize issues,
    # and labels/comments reference issue ids. Because lookups appear interleaved with
    # issues in the dump, we collect raw issue rows first, then resolve at the end.
    raw_issues = []

    context = iterparse(entities_path, events=("end",))
    for _, elem in context:
        tag = _strip_ns(elem.tag)
        stats["rows"] += 1

        try:
            if tag == "Project":
                pid = elem.get("id")
                if pid:
                    projects[pid] = {"key": elem.get("key"), "name": elem.get("name")}

            elif tag == "Status":
                sid = elem.get("id")
                if sid:
                    statuses[sid] = {
                        "name": elem.get("name") or "Unknown",
                        "category": STATUS_CATEGORY_MAP.get(elem.get("statuscategory", ""), "unstarted"),
                    }

            elif tag == "Priority":
                pid = elem.get("id")
                if pid:
                    priorities[pid] = elem.get("name") or ""

            elif tag == "Resolution":
                rid = elem.get("id")
                if rid:
                    resolutions[rid] = elem.get("name") or ""

            elif tag == "MovedIssueKey":
                # Honors renamed issues: oldIssueKey -> issue id.
                old = elem.get("oldIssueKey") or elem.get("key")
                iid = elem.get("issue") or elem.get("issueId")
                if old and iid:
                    moved_keys[iid] = old

            elif tag == "Issue":
                stats["issues_seen"] += 1
                if elem.get("projectKey", "").upper() != project_key:
                    elem.clear()
                    continue
                raw_issues.append({
                    "id": elem.get("id"),
                    "projectKey": elem.get("projectKey"),
                    "number": elem.get("number"),
                    "reporter": elem.get("reporter"),
                    "assignee": elem.get("assignee"),
                    "creator": elem.get("creator"),
                    "priority": elem.get("priority"),
                    "status": elem.get("status"),
                    "resolution": elem.get("resolution"),
                    "summary": elem.get("summary") or "",
                    "description": _text_field(elem, "description", "description"),
                    "created": elem.get("created"),
                    "updated": elem.get("updated"),
                })

            elif tag == "Label":
                stats["labels_seen"] += 1
                iid, name = elem.get("issue"), elem.get("label")
                if iid and name:
                    labels_by_issue.setdefault(iid, set()).add(name)

            elif tag == "Action" and elem.get("type") == "comment":
                stats["comments_seen"] += 1
                # Buffer; we can't know the issue's identifier until issues are resolved,
                # and issues may appear after some comments. Store keyed by issue id.
                body = _text_field(elem, "body", "body")
                comments.setdefault("__by_issue_id__", []).append({
                    "issue_id": elem.get("issue"),
                    "id": elem.get("id"),
                    "author": elem.get("author"),
                    "body": body or "",
                    "created": elem.get("created"),
                })

            elif tag == "IssueLink":
                stats["links_seen"] += 1  # counted only; not represented in single-project state

        except Exception:
            stats["malformed"] += 1

        # Free memory as we stream, but NEVER clear the long-text child elements
        # (`<description>`, `<body>`): their `end` event fires BEFORE the parent
        # Issue/Action `end` event, and clearing them here would wipe `.text`
        # before the parent reads it via _text_field().
        if tag not in ("description", "body"):
            elem.clear()

    # ---- Resolve issues now that all lookups are known ----------------------
    project_name = None
    for p in projects.values():
        if (p.get("key") or "").upper() == project_key:
            project_name = p.get("name")
            break

    for r in raw_issues:
        try:
            number = r["number"]
            if number is None:
                stats["malformed"] += 1
                continue
            identifier = f"{r['projectKey']}-{number}"
            issue_id_to_ident[r["id"]] = identifier

            st = statuses.get(r["status"] or "", {"name": "Unknown", "category": "unstarted"})
            category = st["category"]
            res_name = resolutions.get(r["resolution"] or "", "")
            # Refine cancelled: a completed/closed issue resolved as Won't Do / Duplicate
            # / Cannot Reproduce is "cancelled", not "completed".
            if res_name.lower() in CANCELLED_RESOLUTIONS:
                category = "cancelled"
            if st["name"].lower() in CANCELLED_STATUS_HINTS:
                category = "cancelled"

            prio_name = priorities.get(r["priority"] or "", "")
            priority = PRIORITY_MAP.get(prio_name.lower(), "none")

            assignee_user = registry.resolve(r["assignee"]) if r["assignee"] else None
            # Ensure reporter/creator resolve too (registers them in users[]).
            registry.resolve(r["reporter"])
            registry.resolve(r["creator"])

            label_set = sorted(labels_by_issue.get(r["id"], set()))

            issues.append({
                "id": f"issue-{_slug(identifier)}",
                "identifier": identifier,
                "title": r["summary"],
                "description": r["description"] or "",
                "state": {"id": f"state-{r['status'] or 'unknown'}", "name": st["name"]},
                "_category": category,  # carried out to states[]; stripped before emit
                "assignees": [dict(assignee_user)] if assignee_user else [],
                "labels": [{"id": f"label-{_slug(n)}", "name": n} for n in label_set],
                "priority": priority,
                "created_at": _iso(r["created"]),
                "updated_at": _iso(r["updated"]) or _iso(r["created"]),
                "comments_count": 0,
            })
            stats["issues_kept"] += 1
            if max_issues and stats["issues_kept"] >= max_issues:
                break
        except Exception:
            stats["malformed"] += 1

    kept_ident = {i["identifier"] for i in issues}

    # ---- Attach comments to kept issues -------------------------------------
    out_comments = {}
    for c in comments.get("__by_issue_id__", []):
        ident = issue_id_to_ident.get(c["issue_id"])
        if ident is None or ident not in kept_ident:
            continue
        author = registry.resolve(c["author"])
        out_comments.setdefault(ident, []).append({
            "id": f"comment-{c['id']}",
            "author": dict(author),
            "body": c["body"],
            "created_at": _iso(c["created"]),
        })
        stats["comments_kept"] += 1
    # Sort comments by time and set comments_count on each issue.
    for ident, lst in out_comments.items():
        lst.sort(key=lambda x: x["created_at"] or "")
    count_by_ident = {k: len(v) for k, v in out_comments.items()}
    for i in issues:
        i["comments_count"] = count_by_ident.get(i["identifier"], 0)

    # ---- States[] (deduped from the statuses actually used) -----------------
    states = {}
    for i in issues:
        sid, sname, cat = i["state"]["id"], i["state"]["name"], i.pop("_category")
        states.setdefault(sid, {"id": sid, "name": sname, "category": cat})
    # Ensure the canonical four categories are representable even if unused.
    states_list = sorted(states.values(), key=lambda s: (s["category"], s["name"]))

    # ---- Labels[] (global, deduped) -----------------------------------------
    all_labels = {}
    for i in issues:
        for lbl in i["labels"]:
            all_labels.setdefault(lbl["name"], lbl)
    labels_list = sorted(all_labels.values(), key=lambda l: l["name"])

    # ---- Users[]: only people that were actually referenced ------------------
    referenced = {"__unknown__"} if any(
        u is registry.unknown for i in issues for u in i["assignees"]
    ) else set()
    # registry.users() returns everyone we resolved (reporter/assignee/creator/author);
    # all of them are legitimately referenced, so emit them all (minus unused unknown).
    users_list = [u for u in registry.users()
                  if u is not registry.unknown or "__unknown__" in registry.by_key]
    # Drop unknown if nothing fell back to it.
    used_unknown = any(u["id"] == "user-unknown"
                       for i in issues for u in i["assignees"]) or \
                   any(c["author"]["id"] == "user-unknown"
                       for lst in out_comments.values() for c in lst)
    if not used_unknown:
        users_list = [u for u in users_list if u["id"] != "user-unknown"]

    state = {
        "workspace": "askzeta",
        "base_url": "https://askzeta.atlassian.net",
        "project": {
            "id": f"proj-{_slug(project_key)}",
            "key": project_key,
            "name": project_name or project_key,
            "archived": False,
        },
        "users": users_list,
        "states": states_list,
        "labels": labels_list,
        "modules": [],
        "cycles": [],
        "relations": {},
        "links": {},
        "history": [],
        "attachments": {},
        "issues": issues,
        "comments": out_comments,
    }
    return state, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entities", default="/Users/leonliu/Downloads/jira/entities.xml",
                    help="path to the Jira entities.xml backup")
    ap.add_argument("--project", default="ENG", help="project key to export (default ENG)")
    ap.add_argument("--out", required=True, help="output state.json path")
    ap.add_argument("--registry",
                    default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "identity_registry.json"),
                    help="shared abundant-identity registry.json for cross-clone name unification (default: vendored beside this script; pass '' to disable)")
    ap.add_argument("--max-issues", type=int, default=None,
                    help="cap issues for a quick smoke test")
    args = ap.parse_args()

    state, stats = convert(args.entities, args.project, args.max_issues, args.registry or None)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"wrote {args.out}", file=sys.stderr)
    print(f"  rows scanned     : {stats['rows']}", file=sys.stderr)
    print(f"  issues seen/kept : {stats['issues_seen']} / {stats['issues_kept']}", file=sys.stderr)
    print(f"  comments seen/kept: {stats['comments_seen']} / {stats['comments_kept']}", file=sys.stderr)
    print(f"  labels seen      : {stats['labels_seen']}", file=sys.stderr)
    print(f"  links seen (dropped): {stats['links_seen']}", file=sys.stderr)
    print(f"  malformed skipped: {stats['malformed']}", file=sys.stderr)
    print(f"  users            : {len(state['users'])}", file=sys.stderr)
    print(f"  states           : {len(state['states'])}", file=sys.stderr)
    print(f"  labels           : {len(state['labels'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
