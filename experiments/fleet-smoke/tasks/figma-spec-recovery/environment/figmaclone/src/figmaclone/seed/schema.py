"""The canonical seed spec — the single seam every producer targets.

A canonical seed is a plain JSON document mirroring the shapes the Figma REST API
returns, so the importer (a real ``GET /v1/files/:key`` dump), the synthetic
generator, and a hand-authored fixture all emit the same thing and
``seed.load`` writes it to SQLite:

    {
      "team": {"id": "T1", "name": "Acme Design"},
      "projects": [{"id": "P1", "name": "Web App", "files": ["<file_key>"]}],
      "files": [{
        "key": "<22-char key>", "name": "Pricing Redesign",
        "version": "1", "lastModified": "2026-05-01T12:00:00Z",
        "thumbnailUrl": "/static/<key>/thumb.png", "editorType": "figma", "role": "owner",
        "document": { "type": "DOCUMENT", "id": "0:0", "children": [ <canvas → frames → nodes> ] },
        "components": { "<id>": {"key": "...", "name": "...", "description": "..."} },
        "componentSets": { },
        "styles": { "<id>": {"key": "...", "name": "...", "styleType": "FILL", "description": "..."} },
        "comments": [{"id": "1", "message": "...", "user": {"handle": "..."},
                      "client_meta": {"node_id": "1:5"}, "created_at": "...", "resolved_at": null,
                      "parent_id": "", "order_id": 1}],
        "versions": [{"id": "v1", "label": "...", "description": "...",
                      "created_at": "...", "user": {"handle": "..."}}],
        "images": {"1:5": "/static/<key>/1-5.png"}
      }]
    }

It is portable, diff-able, hand-editable — the seam the whole clone is built on.
"""

from __future__ import annotations

import json
from typing import Any


def empty() -> dict[str, Any]:
    return {
        "team": {"id": "T1", "name": "team"},
        "projects": [],
        "files": [],
    }


def normalize(seed: dict[str, Any]) -> dict[str, Any]:
    """Fill defaults / coerce so a partial seed is safe to load."""
    out = empty()
    out["team"].update(seed.get("team") or {})
    out["projects"] = [_norm_project(p) for p in seed.get("projects", [])]
    out["files"] = [_norm_file(f) for f in seed.get("files", [])]
    return out


def _norm_project(p: dict) -> dict:
    return {
        "id": p["id"],
        "name": p.get("name", p["id"]),
        "files": list(p.get("files", [])),
    }


def _norm_file(f: dict) -> dict:
    return {
        "key": f["key"],
        "project_id": f.get("project_id", ""),
        "name": f.get("name", "Untitled"),
        "version": str(f.get("version", "1")),
        "lastModified": f.get("lastModified", ""),
        "thumbnailUrl": f.get("thumbnailUrl", ""),
        "editorType": f.get("editorType", "figma"),
        "role": f.get("role", "owner"),
        "document": f.get("document") or {"type": "DOCUMENT", "id": "0:0", "children": []},
        "components": f.get("components") or {},
        "componentSets": f.get("componentSets") or {},
        "styles": f.get("styles") or {},
        "images": f.get("images") or {},
        "comments": [_norm_comment(c, i) for i, c in enumerate(f.get("comments", []), start=1)],
        "versions": list(f.get("versions", [])),
    }


def _norm_comment(c: dict, default_seq: int) -> dict:
    cid = str(c.get("id", default_seq))
    return {
        "id": cid,
        "parent_id": str(c.get("parent_id", "")),
        "user": c.get("user") or {"handle": "designer", "id": "U1"},
        "message": c.get("message", ""),
        "client_meta": c.get("client_meta") or {},
        "order_id": int(c.get("order_id", default_seq)),
        "created_at": c.get("created_at", ""),
        "resolved_at": c.get("resolved_at"),
    }


def to_json(seed: dict[str, Any]) -> str:
    return json.dumps(seed, indent=2)


def from_json(text: str) -> dict[str, Any]:
    return normalize(json.loads(text))
