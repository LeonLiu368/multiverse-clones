"""Slack clone adapter — host-side seed + read, mirroring the clone's slack-boot.sh.

It reuses the clone's own store.py (reads) and import_export.py (merge) so the viewer is byte-for-byte
faithful to what an agent's tools return. Provenance ("which rows came from the per-task overlay") is
computed from the small overlay export, never by diffing the multi-million-row prod corpus."""
from __future__ import annotations

import glob
import json
import os
import tempfile
import uuid
from typing import Any, Optional

import dockerutil
from adapters.base import BaseOption, CloneAdapter, LoadResult
from clone_bridge import load_slack_clone, slack_clone_base


def _seeds_dir() -> str:
    return os.path.normpath(os.path.join(slack_clone_base(), "..", "seeds"))


def _parse_overlay_identity(overlay_path: str) -> dict[str, Any]:
    """From an overlay export dir, collect what it introduces: channel names, per-channel message
    timestamps, and user ids. Used to tag merged rows as origin='overlay'."""
    ts_by_channel: dict[str, set[str]] = {}
    channel_names: set[str] = set()
    user_ids: set[str] = set()

    ch_json = os.path.join(overlay_path, "channels.json")
    if os.path.isfile(ch_json):
        try:
            for c in json.load(open(ch_json)):
                if c.get("name"):
                    channel_names.add(c["name"])
        except Exception:
            pass
    us_json = os.path.join(overlay_path, "users.json")
    if os.path.isfile(us_json):
        try:
            for u in json.load(open(us_json)):
                if u.get("id"):
                    user_ids.add(u["id"])
        except Exception:
            pass

    for entry in sorted(os.listdir(overlay_path)):
        sub = os.path.join(overlay_path, entry)
        if not os.path.isdir(sub):
            continue
        channel_names.add(entry)
        tss = ts_by_channel.setdefault(entry, set())
        for f in glob.glob(os.path.join(sub, "*.json")):
            try:
                for m in json.load(open(f)):
                    if m.get("ts"):
                        tss.add(str(m["ts"]))
            except Exception:
                pass
    return {"channel_names": channel_names, "ts_by_channel": ts_by_channel, "user_ids": user_ids}


class SlackAdapter(CloneAdapter):
    id = "slack"
    display_name = "Slack"
    status = "active"
    ui_module = "slack"

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._current: Optional[str] = None

    # ---- seed process -------------------------------------------------------
    def list_bases(self) -> list[BaseOption]:
        out: list[BaseOption] = []
        for ref in dockerutil.list_images("slack-gateway", "slack-seed"):
            out.append(BaseOption(id=ref, kind="image", ref=ref, label=ref,
                                  detail="baked prebuilt DB (docker image)"))
        for export in sorted(glob.glob(os.path.join(_seeds_dir(), "*", "export"))):
            name = os.path.basename(os.path.dirname(export))
            out.append(BaseOption(id=f"dir:{export}", kind="dir", ref=export,
                                  label=f"seeds/{name}", detail="local Slack export dir"))
        return out

    def pull_base(self, ref: str) -> BaseOption:
        dockerutil.pull_image(ref)
        return BaseOption(id=ref, kind="image", ref=ref, label=ref, detail="pulled from registry")

    def _resolve_base(self, base_id: str) -> BaseOption:
        for b in self.list_bases():
            if b.id == base_id:
                return b
        # Accept a raw image ref or dir path not yet in the list (e.g. just-pulled).
        if base_id.startswith("dir:") or os.path.isdir(base_id):
            path = base_id[4:] if base_id.startswith("dir:") else base_id
            return BaseOption(id=f"dir:{path}", kind="dir", ref=path, label=path)
        return BaseOption(id=base_id, kind="image", ref=base_id, label=base_id)

    def load(self, base_id: str, overlay_path: Optional[str] = None) -> LoadResult:
        Store, import_export, _ = load_slack_clone()
        base = self._resolve_base(base_id)
        workdir = tempfile.mkdtemp(prefix="seedview-slack-")
        db_path = os.path.join(workdir, "slack.db")

        # 1. base corpus -> db_path  (mirror slack-boot.sh: prebuilt DB copy, or import an export dir)
        if base.kind == "image":
            dockerutil.extract_db(base.ref, db_path)
        else:
            store = Store(db_path)
            import_export.import_export(store, base.ref, None, None, None, overlay=False)
            store.commit()

        # snapshot base identity (cheap: channels/users are small) for provenance
        base_store = Store(db_path)
        base_channel_ids = {c["id"] for c in base_store.list_channels()}
        base_user_ids = {u["id"] for u in base_store.list_users()}

        overlay_identity = {"channel_names": set(), "ts_by_channel": {}, "user_ids": set()}
        stats = {"channels": len(base_channel_ids), "users": len(base_user_ids)}
        # 2. overlay -> merge on top (INSERT OR IGNORE entities, all messages), like --overlay
        if overlay_path:
            overlay_path = os.path.abspath(os.path.expanduser(overlay_path))
            if not os.path.isdir(overlay_path):
                raise RuntimeError(f"overlay dir not found: {overlay_path}")
            overlay_identity = _parse_overlay_identity(overlay_path)
            st = import_export.import_export(base_store, overlay_path, None, None, None, overlay=True)
            base_store.commit()
            stats["overlay"] = st

        session_id = uuid.uuid4().hex[:12]
        self._sessions[session_id] = {
            "store": Store(db_path),  # read connection
            "db_path": db_path,
            "base_channel_ids": base_channel_ids,
            "base_user_ids": base_user_ids,
            "overlay": overlay_identity,
            "name_by_id": {c["id"]: c["name"] for c in base_store.list_channels()},
            "base": base.id,
            "overlay_path": overlay_path,
            "stats": stats,
        }
        self._current = session_id
        return LoadResult(session_id=session_id, base=base.id, overlay=overlay_path, stats=stats)

    # ---- session helpers ----------------------------------------------------
    def _sess(self, session_id: Optional[str] = None) -> dict[str, Any]:
        sid = session_id or self._current
        if not sid or sid not in self._sessions:
            raise RuntimeError("no loaded session — call load() first")
        return self._sessions[sid]

    def _msg_origin(self, s: dict[str, Any], m: dict[str, Any]) -> str:
        name = s["name_by_id"].get(m.get("channel_id"))
        if name and str(m.get("ts")) in s["overlay"]["ts_by_channel"].get(name, set()):
            return "overlay"
        return "base"

    def _decorate_msg(self, s: dict[str, Any], m: dict[str, Any]) -> dict[str, Any]:
        m = dict(m)
        raw = m.get("reactions") or ""
        try:
            m["reactions"] = json.loads(raw) if raw else []
        except Exception:
            m["reactions"] = []
        m["origin"] = self._msg_origin(s, m)
        return m

    # ---- normalized reads ---------------------------------------------------
    def meta(self, session_id: Optional[str] = None) -> dict[str, Any]:
        s = self._sess(session_id)
        st = s["store"]
        return {
            "workspace": st.get_meta("team_name", "workspace"),
            "team_id": st.get_meta("team_id", ""),
            "base": s["base"],
            "overlay_path": s["overlay_path"],
            "stats": s["stats"],
            "session_id": session_id or self._current,
        }

    def containers(self, session_id: Optional[str] = None) -> list[dict[str, Any]]:
        s = self._sess(session_id)
        out = []
        for c in s["store"].list_channels():
            c = dict(c)
            c["origin"] = "base" if c["id"] in s["base_channel_ids"] else "overlay"
            # a prod channel that received overlay messages is flagged so the sidebar can mark it
            name = c.get("name")
            c["has_overlay"] = bool(s["overlay"]["ts_by_channel"].get(name))
            out.append(c)
        return out

    def entities(self, session_id: Optional[str] = None) -> list[dict[str, Any]]:
        s = self._sess(session_id)
        out = []
        for u in s["store"].list_users():
            u = dict(u)
            u["origin"] = "base" if u["id"] in s["base_user_ids"] else "overlay"
            out.append(u)
        return out

    def messages(self, container_id: str, limit: int = 100,
                 session_id: Optional[str] = None) -> list[dict[str, Any]]:
        s = self._sess(session_id)
        ch = s["store"].channel_by_ref(container_id)
        if not ch:
            return []
        rows = s["store"].history(ch["id"], limit=limit)
        return [self._decorate_msg(s, m) for m in rows]

    def thread(self, container_id: str, root_ts: str,
               session_id: Optional[str] = None) -> list[dict[str, Any]]:
        s = self._sess(session_id)
        ch = s["store"].channel_by_ref(container_id)
        if not ch:
            return []
        rows = s["store"].replies(ch["id"], root_ts)
        return [self._decorate_msg(s, m) for m in rows]

    def search(self, query: str, limit: int = 100,
               session_id: Optional[str] = None) -> list[dict[str, Any]]:
        s = self._sess(session_id)
        terms = [t for t in (query or "").split() if t]
        rows = s["store"].search(terms, limit=limit)
        return [self._decorate_msg(s, m) for m in rows]
