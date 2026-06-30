"""Data-access + Notion-shaped serialization + the database query engine.

This is the single source of truth used by BOTH the HTTP API and the seed loader.
Every read/write goes through here; the serialization helpers emit real Notion
envelopes so responses match the live API:

  * objects carry ``"object": "page"|"database"|"block"|"user"|"comment"``,
  * collections are ``{"object": "list", "results": [...], "next_cursor": ...,
    "has_more": ...}``,
  * timestamps are ISO-8601 ``...Z``, ids are dashed UUIDs.

The **query engine** (`query_database`) is the T2 assessment-grade surface: it
parses Notion's real ``filter`` (single + compound ``and``/``or``) and ``sorts``
grammar over property values and applies it in Python over the seeded rows, then
paginates with an opaque cursor.
"""

from __future__ import annotations

import base64
import time
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .ids import gen_uuid, normalize_id
from .models import Block, Comment, Database, Page, User


# ----------------------------------------------------------------- time helpers
def now_iso() -> str:
    """Current time as Notion renders it: millisecond ISO-8601 in UTC."""
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())


# ----------------------------------------------------------------- rich text
def rich_text(content: str) -> list[dict]:
    """Build a minimal Notion rich-text array for ``content`` (one text run)."""
    return [{
        "type": "text",
        "text": {"content": content, "link": None},
        "annotations": {"bold": False, "italic": False, "strikethrough": False,
                        "underline": False, "code": False, "color": "default"},
        "plain_text": content,
        "href": None,
    }]


def plain_text(rich: list[dict] | None) -> str:
    """Concatenate the plain_text of a rich-text array (filling it in if absent)."""
    out = []
    for r in (rich or []):
        r = r or {}
        out.append(r.get("plain_text") or (r.get("text") or {}).get("content", ""))
    return "".join(out)


def hydrate_rich_text(rich: list[dict] | None) -> list[dict]:
    """Fill in the derived ``plain_text``/``annotations``/``href`` fields Notion
    always returns, so a caller that sends only ``{"text":{"content":…}}`` reads
    back the full shape (matching the live API)."""
    hydrated = []
    for r in (rich or []):
        r = dict(r or {})
        r.setdefault("type", "text")
        content = (r.get("text") or {}).get("content", r.get("plain_text", ""))
        r.setdefault("plain_text", content)
        r.setdefault("annotations", {"bold": False, "italic": False, "strikethrough": False,
                                     "underline": False, "code": False, "color": "default"})
        r.setdefault("href", None)
        if r["type"] == "text":
            r.setdefault("text", {"content": content, "link": None})
        hydrated.append(r)
    return hydrated


def hydrate_properties(props: dict) -> dict:
    """Hydrate the rich-text inside title/rich_text property values on write so the
    page reads back with full ``plain_text`` (matching the live API)."""
    out = {}
    for name, val in (props or {}).items():
        if isinstance(val, dict):
            val = dict(val)
            for key in ("title", "rich_text"):
                if isinstance(val.get(key), list):
                    val[key] = hydrate_rich_text(val[key])
        out[name] = val
    return out


# ----------------------------------------------------------------- serializers
def user_dict(u: User) -> dict:
    out: dict[str, Any] = {
        "object": "user",
        "id": u.id,
        "name": u.name,
        "avatar_url": u.avatar_url,
        "type": u.type,
    }
    if u.type == "person":
        out["person"] = {"email": u.email} if u.email else {}
    elif u.type == "bot":
        out["bot"] = {}
    return out


def _user_ref(uid: str) -> dict:
    return {"object": "user", "id": uid}


def _normalize_parent(parent: dict) -> dict:
    """Add the ``type`` discriminator Notion echoes back, inferring it from the
    present id key when the caller omitted it."""
    parent = dict(parent or {})
    if "type" not in parent:
        if "database_id" in parent:
            parent["type"] = "database_id"
        elif "page_id" in parent:
            parent["type"] = "page_id"
        elif "block_id" in parent:
            parent["type"] = "block_id"
        elif parent.get("workspace"):
            parent["type"] = "workspace"
    return parent


def database_dict(d: Database) -> dict:
    return {
        "object": "database",
        "id": d.id,
        "created_time": d.created_time,
        "last_edited_time": d.last_edited_time,
        "created_by": _user_ref(d.created_by),
        "last_edited_by": _user_ref(d.last_edited_by),
        "title": d.title,
        "description": d.description,
        "icon": d.icon,
        "cover": d.cover,
        "properties": d.properties,
        "parent": d.parent,
        "url": d.url,
        "archived": d.archived,
        "is_inline": False,
    }


def page_dict(p: Page) -> dict:
    return {
        "object": "page",
        "id": p.id,
        "created_time": p.created_time,
        "last_edited_time": p.last_edited_time,
        "created_by": _user_ref(p.created_by),
        "last_edited_by": _user_ref(p.last_edited_by),
        "cover": p.cover,
        "icon": p.icon,
        "parent": p.parent,
        "archived": p.archived,
        "in_trash": p.in_trash,
        "properties": p.properties,
        "url": p.url,
    }


def block_dict(b: Block) -> dict:
    out: dict[str, Any] = {
        "object": "block",
        "id": b.id,
        "parent": b.parent,
        "created_time": b.created_time,
        "last_edited_time": b.last_edited_time,
        "created_by": _user_ref(b.created_by),
        "last_edited_by": _user_ref(b.last_edited_by),
        "has_children": b.has_children,
        "archived": b.archived,
        "type": b.type,
    }
    out.update(b.body or {})
    return out


def comment_dict(c: Comment) -> dict:
    return {
        "object": "comment",
        "id": c.id,
        "parent": c.parent,
        "discussion_id": c.discussion_id,
        "created_time": c.created_time,
        "last_edited_time": c.last_edited_time,
        "created_by": _user_ref(c.created_by),
        "rich_text": c.rich_text,
    }


def list_envelope(results: list[dict], *, next_cursor: str | None = None,
                  obj_type: str | None = None) -> dict:
    out = {
        "object": "list",
        "results": results,
        "next_cursor": next_cursor,
        "has_more": next_cursor is not None,
    }
    if obj_type is not None:
        out["type"] = obj_type
        out[obj_type] = {}
    return out


# ----------------------------------------------------------------- cursor
def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"o:{offset}".encode()).decode()


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        if raw.startswith("o:"):
            return int(raw[2:])
    except Exception:
        pass
    raise ValueError("invalid cursor")


def paginate(rows: list, page_size: int, start_cursor: str | None) -> tuple[list, str | None]:
    """Slice ``rows`` by an opaque offset cursor. Returns (page, next_cursor)."""
    offset = _decode_cursor(start_cursor)
    page = rows[offset:offset + page_size]
    nxt = _encode_cursor(offset + page_size) if offset + page_size < len(rows) else None
    return page, nxt


# ----------------------------------------------------------------- upserts (seed)
def upsert_user(s: Session, u: dict) -> User:
    obj = s.get(User, u["id"])
    if obj is None:
        obj = User(id=u["id"])
        s.add(obj)
    obj.type = u.get("type", "person")
    obj.name = u.get("name", "")
    obj.avatar_url = u.get("avatar_url")
    obj.email = (u.get("person") or {}).get("email") if u.get("type") != "bot" else None
    return obj


def upsert_database(s: Session, d: dict) -> Database:
    obj = s.get(Database, d["id"])
    if obj is None:
        obj = Database(id=d["id"])
        s.add(obj)
    obj.parent = d.get("parent") or {"type": "workspace", "workspace": True}
    obj.title = d.get("title") or []
    obj.description = d.get("description") or []
    obj.icon = d.get("icon")
    obj.cover = d.get("cover")
    obj.properties = d.get("properties") or {}
    obj.created_time = d.get("created_time", "")
    obj.last_edited_time = d.get("last_edited_time", d.get("created_time", ""))
    obj.created_by = d.get("created_by", "")
    obj.last_edited_by = d.get("last_edited_by", d.get("created_by", ""))
    obj.archived = bool(d.get("archived", False))
    obj.url = d.get("url", f"https://notion.so/{d['id'].replace('-', '')}")
    return obj


def upsert_page(s: Session, p: dict) -> Page:
    obj = s.get(Page, p["id"])
    if obj is None:
        obj = Page(id=p["id"])
        s.add(obj)
    parent = p.get("parent") or {"type": "workspace", "workspace": True}
    obj.parent = parent
    obj.database_id = parent.get("database_id") if parent.get("type") == "database_id" else None
    obj.properties = p.get("properties") or {}
    obj.icon = p.get("icon")
    obj.cover = p.get("cover")
    obj.created_time = p.get("created_time", "")
    obj.last_edited_time = p.get("last_edited_time", p.get("created_time", ""))
    obj.created_by = p.get("created_by", "")
    obj.last_edited_by = p.get("last_edited_by", p.get("created_by", ""))
    obj.archived = bool(p.get("archived", False))
    obj.in_trash = bool(p.get("in_trash", p.get("archived", False)))
    obj.url = p.get("url", f"https://notion.so/{p['id'].replace('-', '')}")
    return obj


def upsert_block(s: Session, b: dict, position: int) -> Block:
    obj = s.get(Block, b["id"])
    if obj is None:
        obj = Block(id=b["id"])
        s.add(obj)
    parent = b.get("parent") or {}
    obj.parent = parent
    obj.parent_id = parent.get("page_id") or parent.get("block_id") or b.get("parent_id", "")
    obj.type = b.get("type", "paragraph")
    obj.body = {obj.type: b.get(obj.type, {})}
    obj.position = position
    obj.has_children = bool(b.get("has_children", False))
    obj.created_time = b.get("created_time", "")
    obj.last_edited_time = b.get("last_edited_time", b.get("created_time", ""))
    obj.created_by = b.get("created_by", "")
    obj.last_edited_by = b.get("last_edited_by", b.get("created_by", ""))
    obj.archived = bool(b.get("archived", False))
    return obj


def upsert_comment(s: Session, c: dict, position: int) -> Comment:
    obj = s.get(Comment, c["id"])
    if obj is None:
        obj = Comment(id=c["id"])
        s.add(obj)
    parent = c.get("parent") or {}
    obj.parent = parent
    obj.page_id = parent.get("page_id") or c.get("page_id", "")
    obj.discussion_id = c.get("discussion_id", "")
    obj.rich_text = c.get("rich_text") or []
    obj.created_by = c.get("created_by", "")
    obj.created_time = c.get("created_time", "")
    obj.last_edited_time = c.get("last_edited_time", c.get("created_time", ""))
    obj.position = position
    return obj


# ----------------------------------------------------------------- reads
def get_page(s: Session, page_id: str) -> Page | None:
    return s.get(Page, normalize_id(page_id))


def get_database(s: Session, database_id: str) -> Database | None:
    return s.get(Database, normalize_id(database_id))


def get_user(s: Session, user_id: str) -> User | None:
    return s.get(User, normalize_id(user_id))


def list_users(s: Session, page_size: int, start_cursor: str | None) -> dict:
    rows = list(s.scalars(select(User).order_by(User.id)).all())
    page, nxt = paginate(rows, page_size, start_cursor)
    return list_envelope([user_dict(u) for u in page], next_cursor=nxt, obj_type="user")


def block_children(s: Session, parent_id: str, page_size: int, start_cursor: str | None) -> dict:
    pid = normalize_id(parent_id)
    rows = list(s.scalars(
        select(Block).where(Block.parent_id == pid, Block.archived == False)  # noqa: E712
        .order_by(Block.position)
    ).all())
    page, nxt = paginate(rows, page_size, start_cursor)
    return list_envelope([block_dict(b) for b in page], next_cursor=nxt, obj_type="block")


def list_comments(s: Session, block_id: str, page_size: int, start_cursor: str | None) -> dict:
    pid = normalize_id(block_id)
    rows = list(s.scalars(
        select(Comment).where(Comment.page_id == pid).order_by(Comment.position)
    ).all())
    page, nxt = paginate(rows, page_size, start_cursor)
    return list_envelope([comment_dict(c) for c in page], next_cursor=nxt)


# ----------------------------------------------------------------- writes
def create_page(s: Session, parent: dict, properties: dict, *,
                children: list | None = None, icon=None, cover=None,
                actor: str = "") -> Page:
    ts = now_iso()
    pid = gen_uuid()
    # Notion infers the parent kind from the present key; tolerate a bare
    # {"database_id": …} without an explicit "type".
    db_id = parent.get("database_id")
    parent = _normalize_parent(parent)
    page = Page(
        id=pid, parent=parent, database_id=normalize_id(db_id) if db_id else None,
        properties=hydrate_properties(properties or {}), icon=icon, cover=cover,
        created_time=ts, last_edited_time=ts, created_by=actor, last_edited_by=actor,
        archived=False, in_trash=False,
        url=f"https://notion.so/{pid.replace('-', '')}",
    )
    s.add(page)
    s.flush()
    for i, child in enumerate(children or []):
        _add_block(s, {"type": "page_id", "page_id": pid}, pid, child, i, ts, actor)
    s.commit()
    return page


def update_page(s: Session, page: Page, *, properties: dict | None = None,
                archived: bool | None = None, icon=None, cover=None,
                actor: str = "") -> Page:
    if properties:
        merged = dict(page.properties or {})
        merged.update(hydrate_properties(properties))
        page.properties = merged
    if archived is not None:
        page.archived = bool(archived)
        page.in_trash = bool(archived)
    if icon is not None:
        page.icon = icon
    if cover is not None:
        page.cover = cover
    page.last_edited_time = now_iso()
    page.last_edited_by = actor
    s.commit()
    return page


def append_children(s: Session, parent_id: str, children: list, *, actor: str = "") -> list[Block]:
    pid = normalize_id(parent_id)
    ts = now_iso()
    existing = s.scalar(select(func.max(Block.position)).where(Block.parent_id == pid))
    start = (existing + 1) if existing is not None else 0
    created = []
    # the parent is a page if a Page row exists, else a block
    parent_kind = "page_id" if s.get(Page, pid) else "block_id"
    for i, child in enumerate(children):
        blk = _add_block(s, {"type": parent_kind, parent_kind: pid}, pid, child, start + i, ts, actor)
        created.append(blk)
    if parent_kind == "block_id":
        parent_block = s.get(Block, pid)
        if parent_block:
            parent_block.has_children = True
    s.commit()
    return created


def _add_block(s: Session, parent: dict, parent_id: str, child: dict, position: int,
               ts: str, actor: str) -> Block:
    btype = child.get("type", "paragraph")
    bid = gen_uuid()
    body = dict(child.get(btype, {}))
    if "rich_text" in body:
        body["rich_text"] = hydrate_rich_text(body["rich_text"])
    blk = Block(
        id=bid, parent=parent, parent_id=parent_id, type=btype,
        body={btype: body}, position=position, has_children=False,
        created_time=ts, last_edited_time=ts, created_by=actor, last_edited_by=actor,
        archived=False,
    )
    s.add(blk)
    return blk


def create_comment(s: Session, parent: dict, rich: list, *, discussion_id: str | None = None,
                   actor: str = "") -> Comment:
    ts = now_iso()
    cid = gen_uuid()
    page_id = parent.get("page_id", "")
    pos = s.scalar(select(func.count()).select_from(Comment).where(Comment.page_id == page_id)) or 0
    c = Comment(
        id=cid, parent=parent, page_id=normalize_id(page_id) if page_id else "",
        discussion_id=discussion_id or gen_uuid(), rich_text=hydrate_rich_text(rich),
        created_by=actor, created_time=ts, last_edited_time=ts, position=pos,
    )
    s.add(c)
    s.commit()
    return c


# ----------------------------------------------------------------- search
def search(s: Session, query: str, *, obj_filter: str | None, page_size: int,
           start_cursor: str | None, sort_direction: str | None) -> dict:
    """Search pages + databases by title (Notion's `POST /v1/search`)."""
    q = (query or "").lower()
    results: list[tuple[str, Any]] = []
    for d in s.scalars(select(Database)).all():
        if obj_filter in (None, "database") and not d.archived:
            if not q or q in plain_text(d.title).lower():
                results.append((d.last_edited_time, database_dict(d)))
    for p in s.scalars(select(Page)).all():
        if obj_filter in (None, "page") and not p.archived:
            if not q or q in _page_title(p).lower():
                results.append((p.last_edited_time, page_dict(p)))
    reverse = (sort_direction or "descending") == "descending"
    results.sort(key=lambda t: t[0], reverse=reverse)
    rows = [r for _, r in results]
    page, nxt = paginate(rows, page_size, start_cursor)
    return list_envelope(page, next_cursor=nxt, obj_type="page_or_database")


def _page_title(p: Page) -> str:
    for prop in (p.properties or {}).values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            return plain_text(prop.get("title"))
    return ""


# ----------------------------------------------------------------- QUERY ENGINE (T2)
class QueryError(ValueError):
    """Raised for a malformed filter/sort — surfaced as Notion's validation error."""


def query_database(s: Session, database_id: str, *, filter_obj: dict | None,
                   sorts: list | None, page_size: int, start_cursor: str | None) -> dict:
    """Notion `POST /v1/databases/:id/query` — real filter + sort grammar.

    Filters: a single condition ``{"property": P, "<ptype>": {"<op>": value}}`` or
    a compound ``{"and": [...]}`` / ``{"or": [...]}`` (one level, like Notion's
    common case). Sorts: ``[{"property": P, "direction": "ascending"|...}]`` and
    ``{"timestamp": "created_time"|"last_edited_time", ...}``.
    """
    db = get_database(s, database_id)
    if db is None:
        return None  # caller -> object_not_found
    schema = db.properties or {}
    pages = list(s.scalars(
        select(Page).where(Page.database_id == db.id, Page.archived == False)  # noqa: E712
    ).all())

    if filter_obj:
        pages = [p for p in pages if _match_filter(p, filter_obj, schema)]

    for srt in reversed(sorts or []):
        pages = _apply_sort(pages, srt, schema)

    rows = [page_dict(p) for p in pages]
    page, nxt = paginate(rows, page_size, start_cursor)
    return list_envelope(page, next_cursor=nxt, obj_type="page_or_database")


def _prop_value(page: Page, name: str) -> dict | None:
    return (page.properties or {}).get(name)


def _extract(prop: dict | None) -> Any:
    """Reduce a Notion property value to a comparable scalar/string."""
    if not isinstance(prop, dict):
        return None
    t = prop.get("type")
    if t == "title":
        return plain_text(prop.get("title"))
    if t == "rich_text":
        return plain_text(prop.get("rich_text"))
    if t == "number":
        return prop.get("number")
    if t == "checkbox":
        return bool(prop.get("checkbox"))
    if t == "select":
        return (prop.get("select") or {}).get("name") if prop.get("select") else None
    if t == "multi_select":
        return [o.get("name") for o in (prop.get("multi_select") or [])]
    if t == "status":
        return (prop.get("status") or {}).get("name") if prop.get("status") else None
    if t == "date":
        return (prop.get("date") or {}).get("start") if prop.get("date") else None
    if t == "people":
        return [o.get("id") for o in (prop.get("people") or [])]
    if t == "url":
        return prop.get("url")
    if t == "email":
        return prop.get("email")
    return None


def _match_filter(page: Page, flt: dict, schema: dict) -> bool:
    if "and" in flt:
        return all(_match_filter(page, c, schema) for c in flt["and"])
    if "or" in flt:
        return any(_match_filter(page, c, schema) for c in flt["or"])
    name = flt.get("property")
    if name is None:
        raise QueryError("filter is missing the 'property' field")
    # find the typed condition block (the single key besides 'property')
    cond_keys = [k for k in flt.keys() if k != "property"]
    if len(cond_keys) != 1:
        raise QueryError("filter must have exactly one condition type")
    ptype = cond_keys[0]
    cond = flt[ptype]
    if not isinstance(cond, dict) or not cond:
        raise QueryError(f"filter condition for '{ptype}' must be a non-empty object")
    op, target = next(iter(cond.items()))
    actual = _extract(_prop_value(page, name))
    return _apply_op(ptype, op, actual, target)


def _apply_op(ptype: str, op: str, actual: Any, target: Any) -> bool:
    # presence ops apply to any type
    if op == "is_empty":
        empty = actual in (None, "", [], {})
        return empty if target else not empty
    if op == "is_not_empty":
        empty = actual in (None, "", [], {})
        return (not empty) if target else empty

    if ptype in ("title", "rich_text", "url", "email", "select", "status"):
        a = "" if actual is None else str(actual)
        t = "" if target is None else str(target)
        if op == "equals":
            return a == t
        if op == "does_not_equal":
            return a != t
        if op == "contains":
            return t.lower() in a.lower()
        if op == "does_not_contain":
            return t.lower() not in a.lower()
        if op == "starts_with":
            return a.lower().startswith(t.lower())
        if op == "ends_with":
            return a.lower().endswith(t.lower())
        raise QueryError(f"unsupported operator '{op}' for type '{ptype}'")

    if ptype == "number":
        if actual is None:
            return False
        if op == "equals":
            return actual == target
        if op == "does_not_equal":
            return actual != target
        if op == "greater_than":
            return actual > target
        if op == "less_than":
            return actual < target
        if op == "greater_than_or_equal_to":
            return actual >= target
        if op == "less_than_or_equal_to":
            return actual <= target
        raise QueryError(f"unsupported operator '{op}' for type 'number'")

    if ptype == "checkbox":
        if op == "equals":
            return bool(actual) == bool(target)
        if op == "does_not_equal":
            return bool(actual) != bool(target)
        raise QueryError(f"unsupported operator '{op}' for type 'checkbox'")

    if ptype == "multi_select" or ptype == "people":
        vals = actual or []
        if op == "contains":
            return target in vals
        if op == "does_not_contain":
            return target not in vals
        raise QueryError(f"unsupported operator '{op}' for type '{ptype}'")

    if ptype == "date":
        if actual is None:
            return False
        if op == "equals":
            return str(actual).startswith(str(target))
        if op == "before":
            return str(actual) < str(target)
        if op == "after":
            return str(actual) > str(target)
        if op == "on_or_before":
            return str(actual) <= str(target)
        if op == "on_or_after":
            return str(actual) >= str(target)
        raise QueryError(f"unsupported operator '{op}' for type 'date'")

    raise QueryError(f"unsupported filter property type '{ptype}'")


def _apply_sort(pages: list[Page], srt: dict, schema: dict) -> list[Page]:
    direction = srt.get("direction", "ascending")
    reverse = direction == "descending"
    if "timestamp" in srt:
        ts = srt["timestamp"]
        key_attr = "created_time" if ts == "created_time" else "last_edited_time"
        return sorted(pages, key=lambda p: getattr(p, key_attr), reverse=reverse)
    name = srt.get("property")
    if name is None:
        raise QueryError("sort must specify 'property' or 'timestamp'")

    def keyfn(p: Page):
        v = _extract(_prop_value(p, name))
        if v is None:
            return (1, "")  # Nones sort last regardless of direction
        if isinstance(v, bool):
            return (0, int(v))
        if isinstance(v, (int, float)):
            return (0, v)
        if isinstance(v, list):
            return (0, ",".join(map(str, v)))
        return (0, str(v).lower())

    return sorted(pages, key=keyfn, reverse=reverse)
