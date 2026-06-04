"""The canonical seed spec — the single seam every producer targets.

A canonical seed is a plain JSON document:

    {
      "workspace": {"id": "T…", "name": "...", "domain": "..."},
      "users":    [{"id":"U…","name":"alice","real_name":"Alice A","is_bot":false,
                    "tz":"America/Los_Angeles","profile":{"email":"...","title":"..."}}],
      "channels": [{"id":"C…","name":"general","type":"public_channel",
                    "topic":"...","purpose":"...","created":0,"creator":"U…","members":["U…"]}],
      "messages": [{"channel":"C…","ts":"1700000000.000001","user":"U…","text":"...",
                    "thread_ts":"...","reactions":[{"name":"tada","users":["U…"]}],
                    "edited":{"user":"U…","ts":"..."},"subtype":null,"pinned":false}]
    }

The importer (real Slack export) and the generator (synthetic) both emit this
shape; ``seed.load`` writes it to SQLite. It is portable, diff-able, hand-editable.
"""

from __future__ import annotations

import json
from typing import Any

CHANNEL_TYPES = {"public_channel", "private_channel", "im", "mpim"}


def empty() -> dict[str, Any]:
    return {
        "workspace": {"id": "T0SIMULATED", "name": "workspace", "domain": "workspace"},
        "users": [],
        "channels": [],
        "messages": [],
    }


def normalize(seed: dict[str, Any]) -> dict[str, Any]:
    """Fill defaults / coerce so a partial seed is safe to load."""
    out = empty()
    out["workspace"].update(seed.get("workspace") or {})
    out["users"] = [_norm_user(u) for u in seed.get("users", [])]
    out["channels"] = [_norm_channel(c) for c in seed.get("channels", [])]
    out["messages"] = [_norm_message(m) for m in seed.get("messages", [])]
    return out


def _norm_user(u: dict) -> dict:
    return {
        "id": u["id"],
        "name": u.get("name", u["id"]),
        "real_name": u.get("real_name", ""),
        "is_bot": bool(u.get("is_bot", False)),
        "deleted": bool(u.get("deleted", False)),
        "tz": u.get("tz", "America/Los_Angeles"),
        "profile": u.get("profile", {}),
    }


def _norm_channel(c: dict) -> dict:
    ctype = c.get("type", "public_channel")
    return {
        "id": c["id"],
        "name": c.get("name", c["id"]),
        "type": ctype if ctype in CHANNEL_TYPES else "public_channel",
        "is_private": ctype == "private_channel",
        "is_im": ctype == "im",
        "is_mpim": ctype == "mpim",
        "is_archived": bool(c.get("is_archived", False)),
        "created": int(c.get("created", 0)),
        "creator": c.get("creator", ""),
        "topic": c.get("topic", ""),
        "purpose": c.get("purpose", ""),
        "members": list(c.get("members", [])),
    }


def _norm_message(m: dict) -> dict:
    return {
        "channel": m["channel"],
        "ts": str(m["ts"]),
        "user": m.get("user", ""),
        "text": m.get("text", ""),
        "thread_ts": str(m["thread_ts"]) if m.get("thread_ts") else None,
        "subtype": m.get("subtype"),
        "edited": m.get("edited"),
        "blocks": m.get("blocks"),
        "reactions": m.get("reactions", []),
        "pinned": bool(m.get("pinned", False)),
    }


def to_json(seed: dict[str, Any]) -> str:
    return json.dumps(seed, indent=2)


def from_json(text: str) -> dict[str, Any]:
    return normalize(json.loads(text))
