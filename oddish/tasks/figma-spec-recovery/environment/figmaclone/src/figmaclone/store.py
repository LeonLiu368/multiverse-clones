"""Data-access + Figma-shaped serialization.

This is the single source of truth used by BOTH the HTTP API and the seed loader.
Reads/writes go through here; serialization helpers emit Figma REST shapes so
responses match the real ``GET /v1/files/:key`` / ``/nodes`` / ``/comments`` /
``/components`` / ``/styles`` / ``/versions`` / ``/images`` endpoints.
"""

from __future__ import annotations

import time
from typing import Any, Iterator

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Comment, File, Project, Team, Version

# ----------------------------------------------------------------- node-tree helpers


def iter_nodes(document: dict) -> Iterator[dict]:
    """Depth-first walk over every node in a document tree (root included)."""
    stack = [document]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        yield node
        children = node.get("children")
        if isinstance(children, list):
            # reversed so the walk is left-to-right / top-to-bottom
            stack.extend(reversed(children))


def find_node(document: dict, node_id: str) -> dict | None:
    for node in iter_nodes(document):
        if node.get("id") == node_id:
            return node
    return None


def prune_depth(node: dict, depth: int | None) -> dict:
    """Return a shallow copy of ``node`` trimmed to ``depth`` levels of children.

    ``depth=None`` returns the full subtree; ``depth=1`` returns the node with its
    direct children but their ``children`` removed. Mirrors the ``depth`` query
    param on ``GET /v1/files/:key``.
    """
    if depth is None:
        return node
    out = dict(node)
    children = node.get("children")
    if isinstance(children, list) and depth > 0:
        out["children"] = [prune_depth(c, depth - 1) for c in children]
    elif "children" in out:
        del out["children"]
    return out


# ----------------------------------------------------------------- resolution


def get_file(s: Session, file_key: str) -> File | None:
    return s.get(File, file_key)


def _file_meta(f: File) -> dict[str, Any]:
    return {
        "name": f.name,
        "lastModified": f.last_modified,
        "thumbnailUrl": f.thumbnail_url,
        "version": f.version,
        "role": f.role,
        "editorType": f.editor_type,
        "linkAccess": "view",
    }


# ----------------------------------------------------------------- serialization (reads)


def file_response(s: Session, f: File, *, depth: int | None = None, geometry: str | None = None) -> dict[str, Any]:
    """The ``GET /v1/files/:key`` body."""
    doc = prune_depth(f.document, depth) if depth is not None else f.document
    return {
        "document": doc,
        "components": f.components or {},
        "componentSets": f.component_sets or {},
        "schemaVersion": 0,
        "styles": f.styles or {},
        **_file_meta(f),
    }


def file_nodes_response(s: Session, f: File, node_ids: list[str], *, depth: int | None = None) -> dict[str, Any]:
    """The ``GET /v1/files/:key/nodes?ids=…`` body."""
    nodes: dict[str, Any] = {}
    for nid in node_ids:
        found = find_node(f.document, nid)
        if found is None:
            nodes[nid] = None
            continue
        nodes[nid] = {
            "document": prune_depth(found, depth) if depth is not None else found,
            "components": f.components or {},
            "componentSets": f.component_sets or {},
            "schemaVersion": 0,
            "styles": f.styles or {},
        }
    return {**_file_meta(f), "nodes": nodes}


def comment_dict(c: Comment) -> dict[str, Any]:
    return {
        "id": c.id,
        "file_key": c.file_key,
        "parent_id": c.parent_id or "",
        "user": c.user or {},
        "created_at": c.created_at,
        "resolved_at": c.resolved_at,
        "message": c.message,
        "client_meta": c.client_meta or {},
        "order_id": str(c.order_id),
    }


def list_comments(s: Session, file_key: str) -> list[dict[str, Any]]:
    rows = s.scalars(
        select(Comment).where(Comment.file_key == file_key).order_by(Comment.order_id)
    ).all()
    return [comment_dict(c) for c in rows]


def components_meta(f: File) -> list[dict[str, Any]]:
    out = []
    for node_id, c in (f.components or {}).items():
        out.append({
            "key": c.get("key", ""),
            "file_key": f.key,
            "node_id": node_id,
            "thumbnail_url": (f.images or {}).get(node_id, ""),
            "name": c.get("name", ""),
            "description": c.get("description", ""),
            "containing_frame": c.get("containing_frame", {}),
        })
    return out


def component_sets_meta(f: File) -> list[dict[str, Any]]:
    out = []
    for node_id, c in (f.component_sets or {}).items():
        out.append({
            "key": c.get("key", ""),
            "file_key": f.key,
            "node_id": node_id,
            "thumbnail_url": (f.images or {}).get(node_id, ""),
            "name": c.get("name", ""),
            "description": c.get("description", ""),
        })
    return out


def styles_meta(f: File) -> list[dict[str, Any]]:
    out = []
    for node_id, st in (f.styles or {}).items():
        out.append({
            "key": st.get("key", ""),
            "file_key": f.key,
            "node_id": node_id,
            "style_type": st.get("styleType", st.get("style_type", "")),
            "thumbnail_url": (f.images or {}).get(node_id, ""),
            "name": st.get("name", ""),
            "description": st.get("description", ""),
        })
    return out


def list_versions(s: Session, file_key: str) -> list[dict[str, Any]]:
    rows = s.scalars(
        select(Version).where(Version.file_key == file_key).order_by(Version.pk.desc())
    ).all()
    return [{
        "id": v.id,
        "created_at": v.created_at,
        "label": v.label,
        "description": v.description,
        "user": v.user or {},
    } for v in rows]


def images_response(f: File, node_ids: list[str], base_url: str) -> dict[str, Any]:
    """The ``GET /v1/images/:key?ids=…`` body — node_id → rendered PNG url.

    The node tree is the source of truth; ``images`` are pre-baked URLs carried in
    the seed. Unknown nodes map to ``None`` (Figma's behavior for un-renderable ids).
    """
    images = f.images or {}
    out: dict[str, Any] = {}
    for nid in node_ids:
        url = images.get(nid)
        if url and url.startswith("/"):
            url = base_url.rstrip("/") + url
        out[nid] = url
    return {"err": None, "images": out}


def list_projects(s: Session, team_id: str) -> dict[str, Any] | None:
    t = s.get(Team, team_id)
    if not t:
        return None
    projects = s.scalars(select(Project).where(Project.team_id == team_id)).all()
    return {"name": t.name, "projects": [{"id": p.id, "name": p.name} for p in projects]}


def list_project_files(s: Session, project_id: str) -> dict[str, Any] | None:
    p = s.get(Project, project_id)
    if not p:
        return None
    files = s.scalars(select(File).where(File.project_id == project_id)).all()
    return {
        "name": p.name,
        "files": [{
            "key": f.key,
            "name": f.name,
            "thumbnail_url": f.thumbnail_url,
            "last_modified": f.last_modified,
        } for f in files],
    }


# ----------------------------------------------------------------- writes


def _next_order_id(s: Session, file_key: str) -> int:
    cur = s.scalar(select(func.max(Comment.order_id)).where(Comment.file_key == file_key))
    return int(cur or 0) + 1


def post_comment(
    s: Session,
    file_key: str,
    message: str,
    *,
    user: dict | None = None,
    client_meta: dict | None = None,
    comment_id: str | None = None,
) -> dict[str, Any]:
    """Create a comment (``POST /v1/files/:key/comments``); returns the new comment.

    ``comment_id`` (Figma's ``comment_id`` body field) sets ``parent_id`` to make
    this a reply. A fresh ``order_id`` (current-epoch-derived monotonic) marks it
    as new vs seeded comments — what a verifier keys on.
    """
    order_id = _next_order_id(s, file_key)
    new_id = str(int(time.time() * 1000))  # millisecond epoch → unambiguous "new" id
    c = Comment(
        id=new_id,
        file_key=file_key,
        parent_id=comment_id or "",
        user=user or {"id": "U_AGENT", "handle": "agent", "img_url": "", "email": ""},
        message=message,
        client_meta=client_meta or {},
        order_id=order_id,
        created_at=_now_iso(),
        resolved_at=None,
    )
    s.add(c)
    s.commit()
    return comment_dict(c)


def delete_comment(s: Session, file_key: str, comment_id: str) -> bool:
    c = s.scalars(
        select(Comment).where(Comment.file_key == file_key, Comment.id == comment_id)
    ).first()
    if not c:
        return False
    s.delete(c)
    s.commit()
    return True


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ----------------------------------------------------------------- seed upserts


def upsert_team(s: Session, tid: str, name: str) -> None:
    t = s.get(Team, tid)
    if t:
        t.name = name
    else:
        s.add(Team(id=tid, name=name))


def upsert_project(s: Session, p: dict, team_id: str) -> None:
    obj = s.get(Project, p["id"])
    if obj:
        obj.name = p.get("name", p["id"])
        obj.team_id = team_id
    else:
        s.add(Project(id=p["id"], team_id=team_id, name=p.get("name", p["id"])))


def upsert_file(s: Session, f: dict, project_id: str) -> None:
    obj = s.get(File, f["key"])
    fields = dict(
        project_id=f.get("project_id") or project_id,
        name=f.get("name", "Untitled"),
        version=str(f.get("version", "1")),
        last_modified=f.get("lastModified", ""),
        thumbnail_url=f.get("thumbnailUrl", ""),
        editor_type=f.get("editorType", "figma"),
        role=f.get("role", "owner"),
        document=f.get("document") or {"type": "DOCUMENT", "id": "0:0", "children": []},
        components=f.get("components") or {},
        component_sets=f.get("componentSets") or {},
        styles=f.get("styles") or {},
        images=f.get("images") or {},
    )
    if obj:
        for k, v in fields.items():
            setattr(obj, k, v)
    else:
        s.add(File(key=f["key"], **fields))
    for c in f.get("comments", []):
        upsert_comment(s, f["key"], c)
    for v in f.get("versions", []):
        upsert_version(s, f["key"], v)


def upsert_comment(s: Session, file_key: str, c: dict) -> None:
    existing = s.scalars(
        select(Comment).where(Comment.file_key == file_key, Comment.id == str(c["id"]))
    ).first()
    fields = dict(
        parent_id=str(c.get("parent_id", "")),
        user=c.get("user") or {},
        message=c.get("message", ""),
        client_meta=c.get("client_meta") or {},
        order_id=int(c.get("order_id", 0)),
        created_at=c.get("created_at", ""),
        resolved_at=c.get("resolved_at"),
    )
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
    else:
        s.add(Comment(id=str(c["id"]), file_key=file_key, **fields))


def upsert_version(s: Session, file_key: str, v: dict) -> None:
    existing = s.scalars(
        select(Version).where(Version.file_key == file_key, Version.id == str(v["id"]))
    ).first()
    fields = dict(
        created_at=v.get("created_at", ""),
        label=v.get("label", ""),
        description=v.get("description", ""),
        user=v.get("user") or {},
    )
    if existing:
        for k, val in fields.items():
            setattr(existing, k, val)
    else:
        s.add(Version(id=str(v["id"]), file_key=file_key, **fields))
