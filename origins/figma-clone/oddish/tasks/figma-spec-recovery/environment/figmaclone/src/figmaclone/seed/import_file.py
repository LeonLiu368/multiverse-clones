"""Import a real Figma file into a canonical seed.

Feed it a saved ``GET /v1/files/:key`` JSON dump (what the real Figma REST API
returns for a file) and, optionally, the matching ``/comments`` and ``/versions``
dumps. We preserve the original node ids, component/style maps, and timestamps so
the imported file behaves exactly like the source. ``images`` (node→PNG urls) are
optional; pass a mapping if you exported rendered assets.
"""

from __future__ import annotations

import json
from typing import Any

from . import schema


def import_file(
    file_dump_path: str,
    *,
    file_key: str | None = None,
    comments_path: str | None = None,
    versions_path: str | None = None,
    images: dict[str, str] | None = None,
    project_name: str = "Imported",
) -> dict[str, Any]:
    """Build a canonical seed from a real ``GET /v1/files/:key`` JSON dump."""
    with open(file_dump_path) as f:
        dump = json.load(f)

    key = file_key or dump.get("key") or dump.get("fileKey") or "imported000000000000000"

    comments = _load_list(comments_path, "comments") if comments_path else []
    versions = _load_list(versions_path, "versions") if versions_path else []

    file_obj = {
        "key": key,
        "name": dump.get("name", "Imported"),
        "version": str(dump.get("version", "1")),
        "lastModified": dump.get("lastModified", ""),
        "thumbnailUrl": dump.get("thumbnailUrl", ""),
        "editorType": dump.get("editorType", "figma"),
        "role": dump.get("role", "owner"),
        "document": dump.get("document") or {"type": "DOCUMENT", "id": "0:0", "children": []},
        "components": dump.get("components") or {},
        "componentSets": dump.get("componentSets") or {},
        "styles": dump.get("styles") or {},
        "images": images or {},
        "comments": comments,
        "versions": versions,
    }
    return schema.normalize({
        "team": {"id": "T1", "name": "Imported Team"},
        "projects": [{"id": "P1", "name": project_name, "files": [key]}],
        "files": [file_obj],
    })


def _load_list(path: str, key: str) -> list[dict]:
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return data.get(key, [])
