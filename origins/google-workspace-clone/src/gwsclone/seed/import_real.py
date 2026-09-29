"""Import real Google Workspace data into a canonical seed (real2sim).

Feed it saved real-API dumps and it preserves the original ids/structure so the
imported workspace behaves like the source:

  * a Drive ``files.list`` dump   → ``{"files": [...]}`` (or a bare list)
  * one or more Docs ``documents.get`` dumps → each ``{"documentId","title","body",...}``

Capture them with the real APIs, e.g.:
  GET https://www.googleapis.com/drive/v3/files?fields=files(id,name,mimeType,parents,modifiedTime,owners)
  GET https://docs.googleapis.com/v1/documents/<documentId>
"""

from __future__ import annotations

import json
from typing import Any

from . import schema


def import_real(
    drive_list_path: str | None = None,
    document_paths: list[str] | None = None,
) -> dict[str, Any]:
    drive: list[dict] = []
    if drive_list_path:
        data = json.load(open(drive_list_path))
        drive = data.get("files", data) if isinstance(data, dict) else data

    documents: list[dict] = []
    for p in document_paths or []:
        documents.append(json.load(open(p)))

    return schema.normalize({"drive": drive, "documents": documents})
