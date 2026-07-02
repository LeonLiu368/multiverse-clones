"""The canonical seed spec — the single seam every producer targets.

A canonical seed is a plain JSON document mirroring the shapes the Discord API
returns, so a hand-authored fixture, the synthetic generator, and an imported real
export all emit the same thing and ``seed.load`` writes it to SQLite:

    {
      "bot_user_id": "<snowflake>",
      "users":    [{"id":"<sf>","username":"...","global_name":"...","bot":false}],
      "guilds":   [{"id":"<sf>","name":"...","owner_id":"<sf>"}],
      "channels": [{"id":"<sf>","type":0,"guild_id":"<sf>","name":"...","topic":"...","position":0}],
      "members":  [{"guild_id":"<sf>","user_id":"<sf>","nick":"...","roles":[],"joined_at":"...Z"}],
      "messages": [{"id":"<sf>","channel_id":"<sf>","guild_id":"<sf>","author_id":"<sf>",
                    "content":"...","timestamp":"...","pinned":false,"mentions":[],
                    "reactions":[{"emoji":"👍","user_id":"<sf>"}]}]
    }

Portable, diff-able, hand-editable — the seam the whole clone is built on.
"""

from __future__ import annotations

import json
from typing import Any


def empty() -> dict[str, Any]:
    return {"bot_user_id": None, "users": [], "guilds": [], "channels": [],
            "members": [], "messages": []}


def normalize(seed: dict[str, Any]) -> dict[str, Any]:
    out = empty()
    out["bot_user_id"] = seed.get("bot_user_id")
    out["users"] = [_norm_user(u) for u in seed.get("users", [])]
    out["guilds"] = [_norm_guild(g) for g in seed.get("guilds", [])]
    out["channels"] = [_norm_channel(c) for c in seed.get("channels", [])]
    out["members"] = [_norm_member(m) for m in seed.get("members", [])]
    out["messages"] = [_norm_message(m) for m in seed.get("messages", [])]
    return out


def _norm_user(u: dict) -> dict:
    return {
        "id": u["id"],
        "username": u.get("username", ""),
        "global_name": u.get("global_name"),
        "discriminator": str(u.get("discriminator", "0")),
        "bot": bool(u.get("bot", False)),
        "avatar": u.get("avatar"),
    }


def _norm_guild(g: dict) -> dict:
    return {
        "id": g["id"],
        "name": g.get("name", ""),
        "owner_id": g.get("owner_id", ""),
        "description": g.get("description"),
        "icon": g.get("icon"),
    }


def _norm_channel(c: dict) -> dict:
    return {
        "id": c["id"],
        "type": int(c.get("type", 0)),
        "guild_id": c.get("guild_id", ""),
        "name": c.get("name", ""),
        "topic": c.get("topic"),
        "position": int(c.get("position", 0)),
        "parent_id": c.get("parent_id"),
    }


def _norm_member(m: dict) -> dict:
    return {
        "guild_id": m["guild_id"],
        "user_id": m["user_id"],
        "nick": m.get("nick"),
        "roles": list(m.get("roles", [])),
        "joined_at": m.get("joined_at", ""),
    }


def _norm_message(m: dict) -> dict:
    return {
        "id": m["id"],
        "channel_id": m.get("channel_id", ""),
        "guild_id": m.get("guild_id", ""),
        "author_id": m.get("author_id", ""),
        "content": m.get("content", ""),
        "timestamp": m.get("timestamp", ""),
        "edited_timestamp": m.get("edited_timestamp"),
        "type": int(m.get("type", 0)),
        "pinned": bool(m.get("pinned", False)),
        "mentions": list(m.get("mentions", [])),
        "mention_everyone": bool(m.get("mention_everyone", False)),
        "reactions": list(m.get("reactions", [])),
    }


def to_json(seed: dict[str, Any]) -> str:
    return json.dumps(seed, indent=2)


def from_json(text: str) -> dict[str, Any]:
    return normalize(json.loads(text))
