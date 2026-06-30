"""The canonical seed spec — the single seam every producer targets.

A canonical seed is a plain JSON document mirroring the shapes the Notion API
returns, so a hand-authored fixture, the synthetic generator, and an imported real
export all emit the same thing and ``seed.load`` writes it to SQLite:

    {
      "users":     [{"object":"user","id":"<uuid>","type":"person","name":"...",
                     "person":{"email":"..."}}],
      "databases": [{"object":"database","id":"<uuid>","title":[<rich text>],
                     "parent":{"type":"workspace","workspace":true},
                     "properties":{"Name":{"id":"title","type":"title","title":{}}, ...},
                     "created_by":"<uuid>","created_time":"...Z"}],
      "pages":     [{"object":"page","id":"<uuid>",
                     "parent":{"type":"database_id","database_id":"<uuid>"},
                     "properties":{"Name":{"type":"title","title":[<rich text>]}, ...},
                     "blocks":[{"type":"paragraph","paragraph":{"rich_text":[...]}}],
                     "comments":[{"id":"<uuid>","rich_text":[...],"created_by":"<uuid>"}]}]
    }

Portable, diff-able, hand-editable — the seam the whole clone is built on.
"""

from __future__ import annotations

import json
from typing import Any


def empty() -> dict[str, Any]:
    return {"users": [], "databases": [], "pages": []}


def normalize(seed: dict[str, Any]) -> dict[str, Any]:
    out = empty()
    out["users"] = [_norm_user(u) for u in seed.get("users", [])]
    out["databases"] = [_norm_database(d) for d in seed.get("databases", [])]
    out["pages"] = [_norm_page(p) for p in seed.get("pages", [])]
    return out


def _norm_user(u: dict) -> dict:
    return {
        "object": "user",
        "id": u["id"],
        "type": u.get("type", "person"),
        "name": u.get("name", ""),
        "avatar_url": u.get("avatar_url"),
        "person": u.get("person") or ({"email": u.get("email")} if u.get("email") else {}),
    }


def _norm_database(d: dict) -> dict:
    return {
        "id": d["id"],
        "parent": d.get("parent") or {"type": "workspace", "workspace": True},
        "title": d.get("title") or [],
        "description": d.get("description") or [],
        "icon": d.get("icon"),
        "cover": d.get("cover"),
        "properties": d.get("properties") or {},
        "created_time": d.get("created_time", ""),
        "last_edited_time": d.get("last_edited_time", d.get("created_time", "")),
        "created_by": d.get("created_by", ""),
        "last_edited_by": d.get("last_edited_by", d.get("created_by", "")),
        "archived": bool(d.get("archived", False)),
        "url": d.get("url", ""),
    }


def _norm_page(p: dict) -> dict:
    return {
        "id": p["id"],
        "parent": p.get("parent") or {"type": "workspace", "workspace": True},
        "properties": p.get("properties") or {},
        "icon": p.get("icon"),
        "cover": p.get("cover"),
        "created_time": p.get("created_time", ""),
        "last_edited_time": p.get("last_edited_time", p.get("created_time", "")),
        "created_by": p.get("created_by", ""),
        "last_edited_by": p.get("last_edited_by", p.get("created_by", "")),
        "archived": bool(p.get("archived", False)),
        "url": p.get("url", ""),
        "blocks": list(p.get("blocks", [])),
        "comments": list(p.get("comments", [])),
    }


def to_json(seed: dict[str, Any]) -> str:
    return json.dumps(seed, indent=2)


def from_json(text: str) -> dict[str, Any]:
    return normalize(json.loads(text))
