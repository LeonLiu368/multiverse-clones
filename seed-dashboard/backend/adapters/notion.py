"""Notion clone seed viewer (multiverse notion-clone).

Two seed sources, normalized to one shape:
  • a local `fixture.json` — `{users, databases, pages}` (Notion REST API shapes; pages carry inline
    `blocks`/`comments`), bundled sample or uploaded, and
  • the `notion-service` image — bakes the SQLite corpus at `/srv/notion.db` (tables
    users/databases/pages/blocks/comments); extracted like figma/gworkspace and read with sqlite3.

The frontend renders a Notion-style workspace: a sidebar of databases (→ their pages) + standalone
pages, a database **table** view (rows = pages, columns = properties as status/select pills etc.),
and a **page** with its property list + rendered blocks (headings, paragraphs, to-dos, lists) +
comments."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import uuid
from typing import Any, Optional

import dockerutil
from adapters.base import BaseOption, LoadResult
from adapters.fileseed import FileSeedAdapter

NOTION_DB_PATHS = ("/srv/notion.db", "/data/notion.db", "notion.db")


def _rt_plain(rt: Any) -> str:
    return "".join(
        (x.get("text") or {}).get("content") or x.get("plain_text") or ""
        for x in (rt or [])
        if isinstance(x, dict)
    )


def _rt(rt: Any) -> list[dict]:
    out = []
    for x in rt or []:
        if not isinstance(x, dict):
            continue
        ann = x.get("annotations") or {}
        out.append({
            "text": (x.get("text") or {}).get("content") or x.get("plain_text") or "",
            "bold": bool(ann.get("bold")), "italic": bool(ann.get("italic")),
            "strikethrough": bool(ann.get("strikethrough")), "underline": bool(ann.get("underline")),
            "code": bool(ann.get("code")), "color": ann.get("color"),
            "href": x.get("href"),
        })
    return out


def _J(x: Any, default: Any) -> Any:
    if isinstance(x, (dict, list)):
        return x
    try:
        return json.loads(x) if x else default
    except Exception:
        return default


def _title_of(title_field: Any) -> str:
    # a database `title` is a rich_text array; a page title lives in its title-typed property
    return _rt_plain(title_field) if isinstance(title_field, list) else (title_field or "")


def _prop(p: dict) -> dict:
    """Normalize one page property to {type, display, options?} for the table/detail views."""
    t = p.get("type")
    v = p.get(t)
    if t in ("title", "rich_text"):
        return {"type": t, "display": _rt_plain(v)}
    if t in ("status", "select"):
        o = v or {}
        return {"type": t, "display": o.get("name"), "options": [{"name": o.get("name"), "color": o.get("color")}] if o.get("name") else []}
    if t == "multi_select":
        opts = [{"name": o.get("name"), "color": o.get("color")} for o in (v or [])]
        return {"type": t, "display": ", ".join(o["name"] for o in opts if o["name"]), "options": opts}
    if t == "date":
        d = v or {}
        return {"type": t, "display": (d.get("start") or "") + (f" → {d['end']}" if d.get("end") else "")}
    if t == "checkbox":
        return {"type": t, "display": bool(v)}
    if t == "number":
        return {"type": t, "display": v}
    if t == "people":
        return {"type": t, "display": ", ".join((u.get("name") or u.get("id") or "") for u in (v or []))}
    if t in ("url", "email", "phone_number"):
        return {"type": t, "display": v}
    return {"type": t, "display": v if isinstance(v, (str, int, float)) else _rt_plain(v) if isinstance(v, list) else ""}


def _block(b: dict) -> dict:
    t = b.get("type")
    inner = (b.get("body") or {}).get(t) or (b.get(t) if isinstance(b.get(t), dict) else {}) or {}
    return {
        "id": b.get("id"), "type": t, "rich": _rt(inner.get("rich_text")),
        "checked": inner.get("checked"), "language": inner.get("language"),
        "position": b.get("position") or 0,
    }


class NotionAdapter(FileSeedAdapter):
    id = "notion"
    display_name = "Notion"
    status = "active"
    ui_module = "notion"
    sample_files = ("notion.fixture.json",)

    def list_bases(self) -> list[BaseOption]:
        out: list[BaseOption] = []
        for ref in dockerutil.list_images("notion-service", "notion-gateway", "notion-clone"):
            out.append(BaseOption(id=ref, kind="image", ref=ref, label=ref,
                                  detail="baked notion.db corpus (docker image)"))
        out.extend(super().list_bases())
        return out

    def pull_base(self, ref: str) -> BaseOption:
        dockerutil.pull_image(ref)
        return BaseOption(id=ref, kind="image", ref=ref, label=ref, detail="pulled from registry")

    def load(self, base_id: str, overlay_path: Optional[str] = None) -> LoadResult:
        if base_id.startswith("file:") or (os.path.isfile(base_id) and base_id.endswith(".json")):
            path = os.path.abspath(os.path.expanduser(base_id[5:] if base_id.startswith("file:") else base_id))
            if not os.path.isfile(path):
                raise RuntimeError(f"seed file not found: {path}")
            parsed = self._parse(open(path, encoding="utf-8", errors="replace").read(), path)
        else:
            workdir = tempfile.mkdtemp(prefix="seedview-notion-")
            dbpath = os.path.join(workdir, "notion.db")
            last = ""
            for src in NOTION_DB_PATHS:
                try:
                    dockerutil.extract_file(base_id, src, dbpath)
                    break
                except Exception as e:
                    last = str(e)
            else:
                raise RuntimeError(f"no baked notion.db in {base_id} (probed {NOTION_DB_PATHS}). {last}")
            parsed = self._parse_db(dbpath)

        session_id = uuid.uuid4().hex[:12]
        self._sessions[session_id] = {"path": base_id, "parsed": parsed}
        self._current = session_id
        return LoadResult(session_id=session_id, base=base_id, overlay=None, stats=parsed["stats"])

    # ---- assemble the normalized payload ------------------------------------
    def _page(self, raw: dict, blocks: list[dict], comments: list[dict]) -> dict:
        props = {name: _prop(p) for name, p in (raw.get("properties") or {}).items()}
        title = next((v["display"] for v in props.values() if v["type"] == "title"), "") or "Untitled"
        parent = raw.get("parent") or {}
        db_id = raw.get("database_id") or (parent.get("database_id") if parent.get("type") == "database_id" else None)
        return {
            "id": raw.get("id"), "title": title, "database_id": db_id, "icon": raw.get("icon"),
            "properties": props, "created_time": raw.get("created_time"),
            "last_edited_time": raw.get("last_edited_time"), "url": raw.get("url"),
            "in_trash": bool(raw.get("in_trash") or raw.get("archived")),
            "blocks": sorted((_block(b) for b in blocks), key=lambda b: b["position"]),
            "comments": [{"id": c.get("id"), "rich": _rt(c.get("rich_text")), "author": c.get("created_by"),
                          "created_time": c.get("created_time")} for c in comments],
        }

    def _database(self, raw: dict) -> dict:
        props = raw.get("properties") or {}
        return {
            "id": raw.get("id"), "title": _title_of(raw.get("title")) or "Untitled",
            "description": _rt_plain(raw.get("description")), "icon": raw.get("icon"),
            "property_order": list(props.keys()), "properties": props,
            "created_time": raw.get("created_time"), "url": raw.get("url"),
        }

    def _payload(self, users, databases, pages) -> dict[str, Any]:
        return {
            "meta": {"source": "notion"},
            "users": users,
            "databases": databases,
            "pages": pages,
            "stats": {
                "databases": len(databases), "pages": len(pages),
                "blocks": sum(len(p["blocks"]) for p in pages),
                "comments": sum(len(p["comments"]) for p in pages), "users": len(users),
            },
        }

    def _parse(self, raw: str, path: str) -> dict[str, Any]:  # fixture.json
        d = json.loads(raw)
        users = [{"id": u.get("id"), "name": u.get("name"), "email": (u.get("person") or {}).get("email") or u.get("email"),
                  "avatar_url": u.get("avatar_url"), "type": u.get("type")} for u in (d.get("users") or [])]
        databases = [self._database(db) for db in (d.get("databases") or [])]
        pages = [self._page(p, p.get("blocks") or [], p.get("comments") or []) for p in (d.get("pages") or [])]
        return self._payload(users, databases, pages)

    def _parse_db(self, dbpath: str) -> dict[str, Any]:  # baked notion.db
        c = sqlite3.connect(dbpath)
        c.row_factory = sqlite3.Row
        users = [{"id": r["id"], "name": r["name"], "email": r["email"], "avatar_url": r["avatar_url"],
                  "type": r["type"]} for r in c.execute("SELECT * FROM users")]
        databases = [self._database({**dict(r), "title": _J(r["title"], []), "description": _J(r["description"], []),
                                     "properties": _J(r["properties"], {}), "icon": _J(r["icon"], None)})
                     for r in c.execute("SELECT * FROM databases")]
        # group blocks + comments by page id
        blocks_by: dict[str, list] = {}
        for r in c.execute("SELECT * FROM blocks"):
            b = {"id": r["id"], "type": r["type"], "body": _J(r["body"], {}), "position": r["position"]}
            blocks_by.setdefault(r["parent_id"], []).append(b)
        comments_by: dict[str, list] = {}
        for r in c.execute("SELECT * FROM comments"):
            comments_by.setdefault(r["page_id"], []).append(
                {"id": r["id"], "rich_text": _J(r["rich_text"], []), "created_by": _J(r["created_by"], None),
                 "created_time": r["created_time"]})
        pages = []
        for r in c.execute("SELECT * FROM pages"):
            raw = {**dict(r), "properties": _J(r["properties"], {}), "icon": _J(r["icon"], None),
                   "parent": _J(r["parent"], {})}
            pages.append(self._page(raw, blocks_by.get(r["id"], []), comments_by.get(r["id"], [])))
        c.close()
        return self._payload(users, databases, pages)
