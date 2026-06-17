"""Slack clone adapter — host-side seed + read, mirroring the clone's slack-boot.sh.

It reuses the clone's own store.py (reads) and import_export.py (merge) so the viewer is byte-for-byte
faithful to what an agent's tools return. Provenance ("which rows came from the per-task overlay") is
computed from the small overlay export, never by diffing the multi-million-row prod corpus."""
from __future__ import annotations

import glob
import json
import os
import re
import tempfile
import time
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


def _purpose_str(p: Any) -> str:
    return p.get("value", "") if isinstance(p, dict) else (p or "")


def _overlay_records(overlay_path: str) -> dict[str, Any]:
    """Read an overlay export dir into the editable `write_export` shape:
    {channels:[{name,purpose}], messages:[{channel,author,content,ts}]}. This is the source of truth
    the editor mutates and the user downloads (round-trips through slack_export_writer.write_export)."""
    channels: list[dict] = []
    messages: list[dict] = []
    seen_ch: set[str] = set()

    ch_json = os.path.join(overlay_path, "channels.json")
    if os.path.isfile(ch_json):
        try:
            for c in json.load(open(ch_json)):
                if c.get("name") and c["name"] not in seen_ch:
                    seen_ch.add(c["name"])
                    channels.append({"name": c["name"], "purpose": _purpose_str(c.get("purpose"))})
        except Exception:
            pass

    for entry in sorted(os.listdir(overlay_path)):
        sub = os.path.join(overlay_path, entry)
        if not os.path.isdir(sub):
            continue
        if entry not in seen_ch:
            seen_ch.add(entry)
            channels.append({"name": entry, "purpose": ""})
        for f in sorted(glob.glob(os.path.join(sub, "*.json"))):
            try:
                for m in json.load(open(f)):
                    if not m.get("ts") or m.get("subtype"):  # skip join/system events
                        continue
                    up = m.get("user_profile") or {}
                    author = up.get("name") or up.get("display_name") or m.get("user") or "unknown"
                    messages.append({"channel": entry, "author": author,
                                     "content": m.get("text", ""), "ts": str(m["ts"])})
            except Exception:
                pass
    return {"channels": channels, "messages": messages}


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
        baked_overlay = None
        if base.kind == "image":
            dockerutil.extract_db(base.ref, db_path)
            # A gateway sidecar bakes its per-task overlay (unmerged) at /data/slack-overlay; boot
            # merges it. Pull it out so loading the sidecar alone shows the task's real seeded state.
            baked_overlay = dockerutil.extract_overlay(base.ref, workdir)
        else:
            store = Store(db_path)
            import_export.import_export(store, base.ref, None, None, None, overlay=False)
            store.commit()

        # An explicit overlay arg wins; otherwise use the image's own baked overlay if it has one.
        if not overlay_path and baked_overlay:
            overlay_path = baked_overlay

        # snapshot base identity (cheap: channels/users are small) for provenance
        base_store = Store(db_path)
        base_channel_ids = {c["id"] for c in base_store.list_channels()}
        base_user_ids = {u["id"] for u in base_store.list_users()}

        overlay_identity = {"channel_names": set(), "ts_by_channel": {}, "user_ids": set()}
        # spec = the editable overlay (write_export shape); starts from the loaded overlay, then the
        # add/remove endpoints mutate it. It's the source of truth for download/export.
        spec: dict[str, Any] = {"channels": [], "messages": []}
        stats = {"channels": len(base_channel_ids), "users": len(base_user_ids)}
        # 2. overlay -> merge on top (INSERT OR IGNORE entities, all messages), like --overlay
        if overlay_path:
            overlay_path = os.path.abspath(os.path.expanduser(overlay_path))
            if not os.path.isdir(overlay_path):
                raise RuntimeError(f"overlay dir not found: {overlay_path}")
            overlay_identity = _parse_overlay_identity(overlay_path)
            spec = _overlay_records(overlay_path)
            st = import_export.import_export(base_store, overlay_path, None, None, None, overlay=True)
            base_store.commit()
            stats["overlay"] = st

        session_id = uuid.uuid4().hex[:12]
        read_store = Store(db_path)
        name_by_id = {c["id"]: c["name"] for c in base_store.list_channels()}
        id_by_name = {v: k for k, v in name_by_id.items()}
        # give each spec message a stable id + map (channel_id, ts) -> spec id so deletes can target it
        ts_to_specid: dict[tuple, str] = {}
        for m in spec["messages"]:
            m.setdefault("id", uuid.uuid4().hex[:12])
            cid = id_by_name.get(m["channel"])
            if cid:
                ts_to_specid[(cid, str(m["ts"]))] = m["id"]
        self._sessions[session_id] = {
            "store": read_store,  # read+write connection on the merged DB
            "db_path": db_path,
            "base_channel_ids": base_channel_ids,
            "base_user_ids": base_user_ids,
            "overlay": overlay_identity,
            "name_by_id": name_by_id,
            "spec": spec,
            "ts_to_specid": ts_to_specid,
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

    # ---- overlay editor -----------------------------------------------------
    # All edits operate ONLY on the overlay (task-seed) layer: adds always create overlay rows, and
    # removes refuse anything that belongs to the base corpus/image. The spec is mutated in lockstep
    # with the merged DB so the view stays accurate and the download stays faithful.

    def _sid(self, prefix: str, name: str) -> str:
        _, _, sw = load_slack_clone()
        if sw:
            return sw._sid(prefix, name)
        import hashlib
        return prefix + hashlib.sha1(name.encode()).hexdigest()[:10].upper()

    def _ensure_user(self, s: dict[str, Any], author: str) -> str:
        author = (author or "").strip() or "unknown"
        existing = s["store"].user_by_ref(author)
        if existing:
            return existing["id"]  # reuse a real corpus user when the name matches
        uid = self._sid("U", author)
        s["store"].upsert_user(id=uid, name=author, real_name=author.capitalize())
        s["store"].commit()
        s["overlay"]["user_ids"].add(uid)
        return uid

    def _make_ts(self, s: dict[str, Any], cid: str, timestamp: Optional[str]) -> str:
        _, _, sw = load_slack_clone()
        try:
            e = (sw._epoch(timestamp) if sw else float(timestamp)) if timestamp else time.time()
        except Exception:
            e = time.time()
        conn = s["store"].conn
        ts = f"{e:.6f}"
        while conn.execute("SELECT 1 FROM messages WHERE channel_id=? AND ts=?", (cid, ts)).fetchone():
            e += 0.000001
            ts = f"{e:.6f}"
        return ts

    def add_container(self, name: str, purpose: str = "",
                      session_id: Optional[str] = None) -> dict[str, Any]:
        s = self._sess(session_id)
        name = (name or "").strip().lstrip("#")
        if not name:
            raise RuntimeError("channel name required")
        if s["store"].channel_by_ref(name):
            raise RuntimeError(f"#{name} already exists — add messages to it instead")
        cid = self._sid("C", name)
        s["store"].upsert_channel(id=cid, name=name, purpose=purpose)
        s["store"].commit()
        s["name_by_id"][cid] = name
        s["overlay"]["channel_names"].add(name)
        s["overlay"]["ts_by_channel"].setdefault(name, set())
        s["spec"]["channels"].append({"name": name, "purpose": purpose})
        return {"id": cid, "name": name, "origin": "overlay"}

    def add_message(self, channel: str, author: str, text: str, timestamp: Optional[str] = None,
                    session_id: Optional[str] = None) -> dict[str, Any]:
        s = self._sess(session_id)
        ch = s["store"].channel_by_ref(channel)
        if not ch:
            raise RuntimeError(f"no channel '{channel}' — add it first")
        cid, name = ch["id"], ch["name"]
        uid = self._ensure_user(s, author)
        ts = self._make_ts(s, cid, timestamp)
        s["store"].insert_message(ts=ts, channel_id=cid, user=uid, text=text or "")
        s["store"].recount_members([cid])
        s["store"].commit()
        s["overlay"]["ts_by_channel"].setdefault(name, set()).add(ts)
        spec_id = uuid.uuid4().hex[:12]
        s["spec"]["messages"].append({"id": spec_id, "channel": name, "author": author,
                                      "content": text or "", "ts": ts})
        s["ts_to_specid"][(cid, ts)] = spec_id
        return self._decorate_msg(s, {"ts": ts, "channel_id": cid, "user": uid, "text": text or ""})

    def remove_message(self, channel_id: str, ts: str,
                       session_id: Optional[str] = None) -> dict[str, Any]:
        s = self._sess(session_id)
        ch = s["store"].channel_by_ref(channel_id)
        if not ch:
            raise RuntimeError("unknown channel")
        cid, name = ch["id"], ch["name"]
        if str(ts) not in s["overlay"]["ts_by_channel"].get(name, set()):
            raise RuntimeError("refusing to delete: this message is base data, not task-seed overlay")
        s["store"].conn.execute("DELETE FROM messages WHERE channel_id=? AND ts=?", (cid, str(ts)))
        s["store"].recount_members([cid])
        s["store"].commit()
        s["overlay"]["ts_by_channel"][name].discard(str(ts))
        spec_id = s["ts_to_specid"].pop((cid, str(ts)), None)
        s["spec"]["messages"] = [m for m in s["spec"]["messages"]
                                 if m.get("id") != spec_id and not (m["channel"] == name and str(m["ts"]) == str(ts))]
        return {"ok": True}

    def remove_container(self, channel_id: str,
                         session_id: Optional[str] = None) -> dict[str, Any]:
        s = self._sess(session_id)
        ch = s["store"].channel_by_ref(channel_id)
        if not ch:
            raise RuntimeError("unknown channel")
        cid, name = ch["id"], ch["name"]
        if cid in s["base_channel_ids"]:
            raise RuntimeError(
                "refusing to delete: #%s is a base channel. Delete its overlay messages individually." % name
            )
        s["store"].conn.execute("DELETE FROM messages WHERE channel_id=?", (cid,))
        s["store"].conn.execute("DELETE FROM channels WHERE id=?", (cid,))
        s["store"].commit()
        s["overlay"]["ts_by_channel"].pop(name, None)
        s["overlay"]["channel_names"].discard(name)
        s["name_by_id"].pop(cid, None)
        s["spec"]["channels"] = [c for c in s["spec"]["channels"] if c["name"] != name]
        s["spec"]["messages"] = [m for m in s["spec"]["messages"] if m["channel"] != name]
        s["ts_to_specid"] = {k: v for k, v in s["ts_to_specid"].items() if k[0] != cid}
        return {"ok": True}

    def export_overlay(self, session_id: Optional[str] = None) -> dict[str, Any]:
        """The edited overlay in slack_export_writer.write_export input shape — round-trips into a
        task: write_export(json['messages'], out_dir, channel_purposes=json['channel_purposes'])."""
        s = self._sess(session_id)
        spec = s["spec"]
        purposes = {c["name"]: c["purpose"] for c in spec["channels"] if c.get("purpose")}
        messages = [{"channel": m["channel"], "author": m["author"],
                     "content": m["content"], "timestamp": str(m["ts"])}
                    for m in sorted(spec["messages"], key=lambda m: str(m["ts"]))]
        return {
            "messages": messages,
            "channel_purposes": purposes,
            "channels": [c["name"] for c in spec["channels"]],
        }

    def export_overlay_dir(self, dest_parent: str, name: str = "overlay",
                           session_id: Optional[str] = None) -> str:
        """Write the edited overlay as a real Slack-export DIRECTORY `<dest_parent>/<name>/` — the
        exact shape import_export.py / a task's environment/data/overlay expects. Returns the dir."""
        Store, _, sw = load_slack_clone()
        if sw is None:
            raise RuntimeError("slack_export_writer unavailable in the clone checkout")
        s = self._sess(session_id)
        spec = s["spec"]
        name = re.sub(r"[^A-Za-z0-9._-]", "_", (name or "overlay").strip()).strip("._-") or "overlay"
        out = os.path.join(dest_parent, name)
        msgs = [{"channel": m["channel"], "author": m["author"],
                 "content": m["content"], "timestamp": str(m["ts"])} for m in spec["messages"]]
        purposes = {c["name"]: c["purpose"] for c in spec["channels"] if c.get("purpose")}
        sw.write_export(msgs, out, channel_purposes=purposes)

        # write_export only emits channels that have messages; represent any empty added channels too
        # so the exported directory matches what was built in the UI.
        ch_json = os.path.join(out, "channels.json")
        existing = []
        if os.path.isfile(ch_json):
            existing = json.load(open(ch_json))
        have = {c.get("name") for c in existing}
        for c in spec["channels"]:
            if c["name"] not in have:
                existing.append({"id": sw._sid("C", c["name"]), "name": c["name"], "created": 0,
                                 "creator": "", "is_archived": False, "is_general": False,
                                 "members": [], "topic": {"value": "", "creator": "", "last_set": 0},
                                 "purpose": {"value": c.get("purpose", ""), "creator": "", "last_set": 0}})
                os.makedirs(os.path.join(out, c["name"]), exist_ok=True)
        with open(ch_json, "w") as fh:
            json.dump(existing, fh, indent=2)
        return out
