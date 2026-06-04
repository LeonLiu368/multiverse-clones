"""Import a real Slack workspace export (dir or .zip) into a canonical seed.

Slack export layout:
  users.json                       # array of users
  channels.json                    # public channels (also groups/mpims/dms.json in corporate exports)
  <channel-name>/YYYY-MM-DD.json   # per-channel, per-day arrays of message objects

We preserve original ids/ts/thread_ts/reactions so imported data keeps its identity.
"""

from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from . import schema


def _load_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _channels_from(root: Path) -> list[dict]:
    out: list[dict] = []
    for fname, ctype in [
        ("channels.json", "public_channel"),
        ("groups.json", "private_channel"),
        ("mpims.json", "mpim"),
        ("dms.json", "im"),
    ]:
        data = _load_json(root / fname) or []
        for c in data:
            cid = c.get("id")
            if not cid:
                continue
            name = c.get("name") or cid
            out.append({
                "id": cid,
                "name": name,
                "type": ctype,
                "created": int(c.get("created", 0)),
                "creator": c.get("creator", ""),
                "is_archived": bool(c.get("is_archived", False)),
                "topic": (c.get("topic") or {}).get("value", "") if isinstance(c.get("topic"), dict) else "",
                "purpose": (c.get("purpose") or {}).get("value", "") if isinstance(c.get("purpose"), dict) else "",
                "members": c.get("members", []),
                "_folder": name,  # standard export: message folder named by channel name
            })
    return out


def _users_from(root: Path) -> list[dict]:
    out: list[dict] = []
    for u in _load_json(root / "users.json") or []:
        prof = u.get("profile") or {}
        out.append({
            "id": u["id"],
            "name": u.get("name", u["id"]),
            "real_name": u.get("real_name") or prof.get("real_name", ""),
            "is_bot": bool(u.get("is_bot", False)),
            "deleted": bool(u.get("deleted", False)),
            "tz": u.get("tz", "America/Los_Angeles"),
            "profile": {
                "email": prof.get("email", ""),
                "title": prof.get("title", ""),
                "display_name": prof.get("display_name", ""),
                "image_72": prof.get("image_72", ""),
            },
        })
    return out


def _messages_for(root: Path, channel: dict) -> list[dict]:
    cid = channel["id"]
    # try folder named by channel name, then by id
    for folder_name in (channel.get("_folder"), cid):
        if not folder_name:
            continue
        folder = root / folder_name
        if folder.is_dir():
            break
    else:
        return []
    msgs: list[dict] = []
    for day_file in sorted(folder.glob("*.json")):
        for m in _load_json(day_file) or []:
            if not m.get("ts"):
                continue
            reactions = [
                {"name": r.get("name"), "users": r.get("users", [])}
                for r in m.get("reactions", [])
                if r.get("name")
            ]
            thread_ts = m.get("thread_ts")
            msgs.append({
                "channel": cid,
                "ts": str(m["ts"]),
                "user": m.get("user", m.get("bot_id", "")),
                "text": m.get("text", ""),
                "thread_ts": str(thread_ts) if thread_ts and str(thread_ts) != str(m["ts"]) else None,
                "subtype": m.get("subtype"),
                "edited": m.get("edited"),
                "blocks": m.get("blocks"),
                "reactions": reactions,
                "pinned": cid in (m.get("pinned_to") or []),
            })
    return msgs


def import_export(path: str) -> dict[str, Any]:
    """Parse a Slack export directory or .zip into a canonical seed."""
    p = Path(path)
    tmp: tempfile.TemporaryDirectory | None = None
    if p.is_file() and p.suffix == ".zip":
        tmp = tempfile.TemporaryDirectory()
        with zipfile.ZipFile(p) as z:
            z.extractall(tmp.name)
        root = Path(tmp.name)
        # exports sometimes wrap everything in a single top folder
        entries = [e for e in root.iterdir() if e.is_dir()]
        if not (root / "channels.json").exists() and len(entries) == 1:
            root = entries[0]
    else:
        root = p

    try:
        users = _users_from(root)
        channels = _channels_from(root)
        messages: list[dict] = []
        for c in channels:
            messages.extend(_messages_for(root, c))
            c.pop("_folder", None)
        ws = {"id": "T0IMPORTED", "name": root.name or "imported", "domain": root.name or "imported"}
        return schema.normalize(
            {"workspace": ws, "users": users, "channels": channels, "messages": messages}
        )
    finally:
        if tmp:
            tmp.cleanup()
