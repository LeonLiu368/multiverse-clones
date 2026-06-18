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
        base_issue_ids = {i["identifier"] for i in backend.issues}
        base_comment_ids = {c["id"] for cs in backend.comments.values() for c in cs}

        session_id = uuid.uuid4().hex[:12]
        self._sessions[session_id] = {
            "backend": backend,
            "state_path": state_path,
            "base": base_id,
            "base_issue_ids": base_issue_ids,
            "base_comment_ids": base_comment_ids,
            "edited": set(),  # base issue identifiers modified via update
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
        issue["origin"] = "base" if ident in s["base_issue_ids"] else "overlay"
        issue["edited"] = ident in s["edited"]
        return issue

    def _decorate_comment(self, s: dict[str, Any], c: dict) -> dict:
        c = copy.deepcopy(c)
        c["origin"] = "base" if c["id"] in s["base_comment_ids"] else "overlay"
        return c

    # ---- normalized reads ---------------------------------------------------
    def meta(self, session_id: Optional[str] = None) -> dict[str, Any]:
        s = self._sess(session_id)
        b = s["backend"]
        return {
            "workspace": b.workspace,
            "project": b.project,
            "states": b.list_states(),
            "labels": b.list_labels(),
            "base": s["base"],
            "stats": {"issues": len(b.issues), "comments": sum(len(v) for v in b.comments.values()),
                      "users": len(b.users)},
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

    def messages(self, container_id: str, limit: int = 200,
                 session_id: Optional[str] = None) -> list[dict[str, Any]]:
        s = self._sess(session_id)
        rows = s["backend"].issue_list(limit=max(1, min(int(limit), 5000)))["results"]
        return [self._decorate_issue(s, i) for i in rows]

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
        if ident in s["base_issue_ids"]:
            s["edited"].add(ident)  # a base issue edited on the overlay layer
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
        b = s["backend"]
        ident = p.get("identifier")
        if ident in s["base_issue_ids"]:
            raise RuntimeError(f"refusing to delete: {ident} is base data, not overlay")
        if not any(i["identifier"] == ident for i in b.issues):
            raise RuntimeError(f"unknown issue: {ident}")
        b.delete_issue(ident)
        b.comments.pop(ident, None)
        b._save()
        return {"ok": True}

    def _op_remove_comment(self, s: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
        b = s["backend"]
        ident, cid = p.get("identifier"), p.get("comment_id")
        if cid in s["base_comment_ids"]:
            raise RuntimeError("refusing to delete: this comment is base data, not overlay")
        lst = b.comments.get(ident, [])
        new = [c for c in lst if c["id"] != cid]
        if len(new) == len(lst):
            raise RuntimeError(f"unknown comment: {cid}")
        b.comments[ident] = new
        b._save()
        return {"ok": True}

    # ---- export: merged state.json (mountable onto jira-gateway:empty) -------
    def export_overlay(self, session_id: Optional[str] = None) -> dict[str, Any]:
        return self._sess(session_id)["backend"].snapshot()
