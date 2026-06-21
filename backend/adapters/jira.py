"""Jira clone adapter — host-side load + read + edit of a ticketvector `state.json`.

The Jira clone (abundant-jira-clone) ships its data as a single `state.json` (ticketvector format)
baked into `jira-gateway:prod-v1` or mounted onto `jira-gateway:empty`. We reuse ticketvector's own
`FakePlaneBackend` (imported by path) to read/write that state — byte-for-byte what the agent's
`jira` CLI sees. Edits are an overlay layer (added/edited issues+comments); base data is protected
from deletion; export is the merged `state.json` (mountable onto `jira-gateway:empty`)."""
from __future__ import annotations

import copy
import glob
import json
import os
import shutil
import tempfile
import uuid
from typing import Any, Optional

import dockerutil
from adapters.base import BaseOption, CloneAdapter, LoadResult
from clone_bridge import jira_data_base, load_jira_clone

# state.json top-level fields by container type — used to normalize sparse/variant task states so
# FakePlaneBackend._load (which indexes data["modules"] etc.) and update_issue (history.setdefault)
# never blow up on a hand-authored state.
_LIST_FIELDS = ("users", "states", "labels", "modules", "cycles", "issues")
_DICT_FIELDS = ("comments", "links", "attachments", "relations", "history")
_DEFAULT_STATES = [
    {"id": "state-todo", "name": "To Do", "category": "unstarted"},
    {"id": "state-progress", "name": "In Progress", "category": "started"},
    {"id": "state-done", "name": "Done", "category": "completed"},
]

# where the clone bakes its state inside a gateway image
IMAGE_STATE_PATH = "/var/lib/ticketvector/state.json"


def _normalize_state(d: dict) -> dict:
    d.setdefault("workspace", "acme")
    d.setdefault("base_url", "https://plane.local")
    d.setdefault("project", {"id": "proj-new", "key": "NEW", "name": "New Project", "archived": False})
    for k in _LIST_FIELDS:
        if not isinstance(d.get(k), list):
            d[k] = []
    for k in _DICT_FIELDS:
        if not isinstance(d.get(k), dict):
            d[k] = {}
    if not d["states"]:
        d["states"] = copy.deepcopy(_DEFAULT_STATES)
    return d


def _empty_state() -> dict:
    return _normalize_state({
        "workspace": "acme",
        "base_url": "https://plane.local",
        "project": {"id": "proj-new", "key": "NEW", "name": "New Project", "archived": False},
    })


def _assignee_handles(issue: dict) -> list:
    return [a.get("handle") or a.get("id") for a in issue.get("assignees", [])]


def _label_names(issue: dict) -> list:
    return [l.get("name") for l in issue.get("labels", [])]


def _issue_changes(base_i: dict, cur_i: dict) -> dict:
    """Fields that differ base→current, in apply_state_patch update-op `set` shape (state/labels by
    name, assignees by handle)."""
    ch: dict = {}
    if base_i.get("title") != cur_i.get("title"):
        ch["title"] = cur_i.get("title", "")
    if base_i.get("description") != cur_i.get("description"):
        ch["description"] = cur_i.get("description", "")
    if base_i.get("priority") != cur_i.get("priority"):
        ch["priority"] = cur_i.get("priority")
    if (base_i.get("state") or {}).get("name") != (cur_i.get("state") or {}).get("name"):
        ch["state"] = (cur_i.get("state") or {}).get("name")
    if _assignee_handles(base_i) != _assignee_handles(cur_i):
        ch["assignees"] = _assignee_handles(cur_i)
    if _label_names(base_i) != _label_names(cur_i):
        ch["labels"] = _label_names(cur_i)
    return ch


def _issue_authoring(issue: dict) -> dict:
    """A new issue in apply_state_patch add-op `set` shape."""
    return {
        "identifier": issue["identifier"],
        "title": issue.get("title", ""),
        "description": issue.get("description", ""),
        "state": (issue.get("state") or {}).get("name"),
        "priority": issue.get("priority", "medium"),
        "assignees": _assignee_handles(issue),
        "labels": _label_names(issue),
    }


def _natural_key(ident: str) -> tuple:
    key, _, num = ident.rpartition("-")
    return (key, int(num) if num.isdigit() else 0)


class JiraAdapter(CloneAdapter):
    id = "jira"
    display_name = "Jira"
    status = "active"
    ui_module = "jira"

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._current: Optional[str] = None

    # ---- seed process -------------------------------------------------------
    def list_bases(self) -> list[BaseOption]:
        out: list[BaseOption] = []
        for ref in dockerutil.list_images("jira-gateway", "jira-seed"):
            out.append(BaseOption(id=ref, kind="image", ref=ref, label=ref,
                                  detail="baked state.json (docker image)"))
        root = jira_data_base()
        patterns = [
            os.path.join(root, "selfcontained", "base", "data", "*.json"),
            os.path.join(root, "tasks", "*", "environment", "data", "state.json"),
        ]
        for pat in patterns:
            for f in sorted(glob.glob(pat)):
                out.append(BaseOption(id=f"file:{f}", kind="file", ref=f,
                                      label=os.path.relpath(f, root), detail="local state.json"))
        out.append(BaseOption(id="empty", kind="empty", ref="empty", label="empty workspace",
                              detail="start with no issues"))
        return out

    def pull_base(self, ref: str) -> BaseOption:
        dockerutil.pull_image(ref)
        return BaseOption(id=ref, kind="image", ref=ref, label=ref, detail="pulled from registry")

    def load(self, base_id: str, overlay_path: Optional[str] = None) -> LoadResult:
        FakePlaneBackend, _ = load_jira_clone()
        workdir = tempfile.mkdtemp(prefix="seedview-jira-")
        state_path = os.path.join(workdir, "state.json")

        if base_id == "empty":
            data = _empty_state()
        elif base_id.startswith("file:") or os.path.isfile(base_id):
            src = base_id[5:] if base_id.startswith("file:") else base_id
            data = _normalize_state(json.load(open(src)))
        else:  # docker image — extract the baked state.json
            extracted = os.path.join(workdir, "extracted.json")
            try:
                dockerutil.extract_file(base_id, IMAGE_STATE_PATH, extracted)
                data = _normalize_state(json.load(open(extracted)))
            except Exception:
                data = _empty_state()  # e.g. jira-gateway:empty has no baked state
        json.dump(data, open(state_path, "w"))

        backend = FakePlaneBackend(state_file=state_path)
        # pristine base snapshot — the patch diff is computed against this, so base edits/deletes are
        # recorded as ops without mutating the source state file.
        base_snapshot = backend.snapshot()
        base_issue_ids = {i["identifier"] for i in backend.issues}
        base_issue_by_id = {i["identifier"]: i for i in base_snapshot.get("issues", [])}
        base_comment_ids = {c["id"] for cs in backend.comments.values() for c in cs}

        session_id = uuid.uuid4().hex[:12]
        self._sessions[session_id] = {
            "backend": backend,
            "state_path": state_path,
            "base": base_id,
            "base_snapshot": base_snapshot,
            "base_issue_ids": base_issue_ids,
            "base_issue_by_id": base_issue_by_id,
            "base_comment_ids": base_comment_ids,
        }
        self._current = session_id
        stats = {"issues": len(backend.issues), "comments": len(base_comment_ids),
                 "users": len(backend.users)}
        return LoadResult(session_id=session_id, base=base_id, overlay=None, stats=stats)

    # ---- session helpers ----------------------------------------------------
    def _sess(self, session_id: Optional[str] = None) -> dict[str, Any]:
        sid = session_id or self._current
        if not sid or sid not in self._sessions:
            raise RuntimeError("no loaded session — call load() first")
        return self._sessions[sid]

    def _decorate_issue(self, s: dict[str, Any], issue: dict) -> dict:
        issue = copy.deepcopy(issue)
        ident = issue["identifier"]
        base_i = s["base_issue_by_id"].get(ident)
        issue["origin"] = "base" if base_i else "overlay"
        issue["edited"] = bool(base_i) and bool(_issue_changes(base_i, issue))
        return issue

    def _decorate_comment(self, s: dict[str, Any], c: dict) -> dict:
        c = copy.deepcopy(c)
        c["origin"] = "base" if c["id"] in s["base_comment_ids"] else "overlay"
        return c

    # ---- normalized reads ---------------------------------------------------
    def meta(self, session_id: Optional[str] = None) -> dict[str, Any]:
        s = self._sess(session_id)
        b = s["backend"]
        d = self._diff(s)
        return {
            "workspace": b.workspace,
            "project": b.project,
            "states": b.list_states(),
            "labels": b.list_labels(),
            "base": s["base"],
            "stats": {"issues": len(b.issues), "comments": sum(len(v) for v in b.comments.values()),
                      "users": len(b.users)},
            "changes": {
                "added": [i["identifier"] for i in d["added"]],
                "edited": [k for k, _ in d["edited"]],
                "deleted": [{"identifier": i["identifier"], "title": i.get("title", "")} for i in d["deleted"]],
                "comments_added": len(d["comments_added"]),
                "comments_deleted": len(d["comments_deleted"]),
                "ops": len(d["added"]) + len(d["edited"]) + len(d["deleted"])
                + len(d["comments_added"]) + len(d["comments_deleted"]),
            },
            "session_id": session_id or self._current,
        }

    def containers(self, session_id: Optional[str] = None) -> list[dict[str, Any]]:
        s = self._sess(session_id)
        p = dict(s["backend"].project)
        p["origin"] = "base"  # the project itself comes from the base state
        return [p]

    def entities(self, session_id: Optional[str] = None) -> list[dict[str, Any]]:
        s = self._sess(session_id)
        return [dict(u, origin="base") for u in s["backend"].users]

    def messages(self, container_id: str, limit: int = 500,
                 session_id: Optional[str] = None) -> list[dict[str, Any]]:
        # Natural-sort by issue number (not lexicographic), and ALWAYS include added/edited issues
        # even on a huge corpus where they'd otherwise fall outside the page — so an added issue is
        # never invisible. Returned in natural order for the list view.
        s = self._sess(session_id)
        decorated = [self._decorate_issue(s, i) for i in s["backend"].issues]
        changed = [i for i in decorated if i["origin"] == "overlay" or i["edited"]]
        rest = [i for i in decorated if not (i["origin"] == "overlay" or i["edited"])]
        rest.sort(key=lambda i: _natural_key(i["identifier"]))
        lim = max(1, int(limit))
        keep = changed + rest[: max(0, lim - len(changed))]
        keep.sort(key=lambda i: _natural_key(i["identifier"]))
        return keep

    def thread(self, container_id: str, root_ts: str,
               session_id: Optional[str] = None) -> list[dict[str, Any]]:
        # root_ts carries the issue identifier; return its comments oldest-first
        s = self._sess(session_id)
        try:
            comments = s["backend"].list_comments(root_ts)
        except Exception:
            return []
        return [self._decorate_comment(s, c) for c in comments]

    def search(self, query: str, limit: int = 200,
               session_id: Optional[str] = None) -> list[dict[str, Any]]:
        s = self._sess(session_id)
        rows = s["backend"].issue_list(query=query or None,
                                       limit=max(1, min(int(limit), 5000)))["results"]
        return [self._decorate_issue(s, i) for i in rows]

    # ---- overlay editor (overlay layer only; base protected from deletion) ---
    def overlay_op(self, op: str, payload: dict[str, Any],
                   session_id: Optional[str] = None) -> dict[str, Any]:
        s = self._sess(session_id)
        handler = getattr(self, f"_op_{op}", None)
        if handler is None:
            raise RuntimeError(f"unknown op: {op}")
        return handler(s, payload or {})

    def _next_identifier(self, b) -> str:
        key = b.project["key"]
        nums = [int(i["identifier"].rsplit("-", 1)[1]) for i in b.issues
                if i["identifier"].startswith(key + "-") and i["identifier"].rsplit("-", 1)[1].isdigit()]
        return f"{key}-{(max(nums) + 1) if nums else 1}"

    def _op_add_issue(self, s: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
        # ticketvector's create_issue is hardcoded to PAY-<n> + a default cycle, so we build the
        # issue with the real project key, reusing FakePlaneBackend's field resolvers.
        b = s["backend"]
        _, wi = load_jira_clone()
        if not (p.get("title") or "").strip():
            raise RuntimeError("title required")
        assignees = p.get("assignees") or ([p["assignee"]] if p.get("assignee") else [])
        cyc = p.get("cycle")
        try:
            ident = self._next_identifier(b)
            issue = {
                "id": f"issue-{ident.lower()}", "identifier": ident, "project": copy.deepcopy(b.project),
                "title": p["title"], "description": p.get("description", ""),
                "state": b._state(p.get("state") or b.states[0]["name"]),
                "priority": p.get("priority", "medium"),
                "assignees": [b._user(h) for h in assignees],
                "labels": b._labels(p.get("labels") or []),
                "cycle": b._cycle(cyc) if cyc else None, "module": None,
                "links": [], "relations": [], "comments_count": 0, "attachments_count": 0,
                "created_at": wi.now_iso(), "updated_at": wi.now_iso(),
                "url": wi.issue_url(b.base_url, b.workspace, b.project["key"], ident),
            }
        except wi.NotFoundError as e:  # unknown assignee/state/label/cycle
            raise RuntimeError(str(e))
        b.issues.append(issue)
        b._save()
        return self._decorate_issue(s, issue)

    def _op_update_issue(self, s: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
        b = s["backend"]
        _, wi = load_jira_clone()
        ident = p.get("identifier")
        if not ident:
            raise RuntimeError("identifier required")
        fields = {k: v for k, v in p.items() if k != "identifier"}
        try:
            _before, after = b.update_issue(ident, **fields)
        except wi.NotFoundError as e:
            raise RuntimeError(str(e))
        return self._decorate_issue(s, after)

    def _op_add_comment(self, s: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
        b = s["backend"]
        _, wi = load_jira_clone()
        ident, body = p.get("identifier"), p.get("body")
        if not ident or not (body or "").strip():
            raise RuntimeError("identifier and body required")
        try:
            c = b.add_comment(ident, body, author=p.get("author"))
        except wi.NotFoundError as e:
            raise RuntimeError(str(e))
        return self._decorate_comment(s, c)

    def _op_remove_issue(self, s: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
        # Deleting a base issue is allowed and recorded as a delete op in the patch — the source
        # state file is never mutated, only the in-session working state + the diff.
        b = s["backend"]
        ident = p.get("identifier")
        if not any(i["identifier"] == ident for i in b.issues):
            raise RuntimeError(f"unknown issue: {ident}")
        b.delete_issue(ident)
        b.comments.pop(ident, None)
        b._save()
        return {"ok": True}

    def _op_remove_comment(self, s: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
        b = s["backend"]
        ident, cid = p.get("identifier"), p.get("comment_id")
        lst = b.comments.get(ident, [])
        new = [c for c in lst if c["id"] != cid]
        if len(new) == len(lst):
            raise RuntimeError(f"unknown comment: {cid}")
        b.comments[ident] = new
        b._save()
        return {"ok": True}

    # ---- diff + patch export ------------------------------------------------
    def _diff(self, s: dict[str, Any]) -> dict[str, Any]:
        base = s["base_snapshot"]
        cur = s["backend"].snapshot()
        b = {i["identifier"]: i for i in base.get("issues", [])}
        c = {i["identifier"]: i for i in cur.get("issues", [])}
        added = [c[k] for k in c if k not in b]
        deleted = [b[k] for k in b if k not in c]
        edited = [(k, _issue_changes(b[k], c[k])) for k in c if k in b and _issue_changes(b[k], c[k])]
        bc = {cc["id"]: (k, cc) for k, lst in base.get("comments", {}).items() for cc in lst}
        cc = {cc["id"]: (k, cc) for k, lst in cur.get("comments", {}).items() for cc in lst}
        comments_added = [(k, com) for cid, (k, com) in cc.items() if cid not in bc]
        comments_deleted = [(k, com) for cid, (k, com) in bc.items() if cid not in cc]
        return {"added": added, "deleted": deleted, "edited": edited,
                "comments_added": comments_added, "comments_deleted": comments_deleted}

    def export_patch(self, session_id: Optional[str] = None) -> dict[str, Any]:
        return self.export_overlay(session_id)

    def export_overlay(self, session_id: Optional[str] = None) -> dict[str, Any]:
        """The TASK DIFF as an apply_state_patch.py op-list (`--patch`): add/update/delete issues +
        add/delete comments. Applied onto the base at task standup; the base file is untouched."""
        s = self._sess(session_id)
        d = self._diff(s)
        ops: list[dict[str, Any]] = []
        for i in d["added"]:
            ops.append({"op": "add", "entity": "issue", "set": _issue_authoring(i)})
        for k, ch in d["edited"]:
            ops.append({"op": "update", "entity": "issue", "match": {"key": k}, "set": ch})
        for i in d["deleted"]:
            ops.append({"op": "delete", "entity": "issue", "match": {"key": i["identifier"]}})
        for k, com in d["comments_added"]:
            ops.append({"op": "add", "entity": "comment", "match": {"key": k},
                        "set": {"author": (com.get("author") or {}).get("handle")
                                or (com.get("author") or {}).get("id"), "body": com.get("body", "")}})
        for k, com in d["comments_deleted"]:
            ops.append({"op": "delete", "entity": "comment", "match": {"key": k},
                        "set": {"comment_id": com["id"]}})
        return {"version": 1, "ops": ops}
