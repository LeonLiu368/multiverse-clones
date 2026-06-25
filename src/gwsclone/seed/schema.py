"""The canonical seed spec — the single seam every producer targets.

A plain-JSON document describing a Workspace, mirroring the shapes the Google APIs
return so a real ``GET /v1/documents/:id`` dump and a hand-authored fixture load
the same way:

    {
      "drive": [
        {"id": "<fileId>", "name": "Q3 Planning", "mimeType": "application/vnd.google-apps.document",
         "parents": ["root"], "modifiedTime": "...", "owners": [{"displayName": "...", "emailAddress": "..."}]}
      ],
      "documents": [
        {"documentId": "<fileId>", "title": "Q3 Planning", "revisionId": "5",
         "body": {"content": [ <structural elements: paragraphs, tables, ...> ]}}
      ]
    }

Invariant: a Doc's ``documentId`` equals its Drive file id (a Google Doc IS a
Drive file). It is portable, diff-able, hand-editable.
"""

from __future__ import annotations

import json
from typing import Any

DOC_MIME = "application/vnd.google-apps.document"


def empty() -> dict[str, Any]:
    return {"drive": [], "documents": []}


def normalize(seed: dict[str, Any]) -> dict[str, Any]:
    out = empty()
    out["drive"] = [_norm_file(f) for f in seed.get("drive", [])]
    out["documents"] = [_norm_doc(d) for d in seed.get("documents", [])]
    # ensure every document has a backing Drive file (Docs are Drive files)
    drive_ids = {f["id"] for f in out["drive"]}
    for d in out["documents"]:
        if d["documentId"] not in drive_ids:
            out["drive"].append(_norm_file({
                "id": d["documentId"], "name": d["title"], "mimeType": DOC_MIME,
                "modifiedTime": d.get("_modifiedTime", ""),
            }))
            drive_ids.add(d["documentId"])
    return out


def _norm_file(f: dict) -> dict:
    return {
        "id": f["id"],
        "name": f.get("name", "Untitled"),
        "mimeType": f.get("mimeType", DOC_MIME),
        "parents": list(f.get("parents", []) or []),
        "createdTime": f.get("createdTime", ""),
        "modifiedTime": f.get("modifiedTime", ""),
        "owners": f.get("owners", []) or [],
        "size": f.get("size"),
        "trashed": bool(f.get("trashed", False)),
    }


def _norm_doc(d: dict) -> dict:
    return {
        "documentId": d.get("documentId") or d["id"],
        "title": d.get("title", "Untitled"),
        "revisionId": str(d.get("revisionId", "1")),
        "body": d.get("body") or {"content": []},
        "namedStyles": d.get("namedStyles") or {},
        "inlineObjects": d.get("inlineObjects") or {},
    }


def to_json(seed: dict[str, Any]) -> str:
    return json.dumps(seed, indent=2)


def from_json(text: str) -> dict[str, Any]:
    return normalize(json.loads(text))


# ----------------------------------------------------------------- a tiny doc builder
# Helper for hand-authoring fixtures: build a real-shaped Docs body from simple blocks.

def paragraph(text: str, style: str = "NORMAL_TEXT") -> dict:
    return {"paragraph": {
        "paragraphStyle": {"namedStyleType": style},
        "elements": [{"textRun": {"content": text, "textStyle": {}}}],
    }}


def make_body(*blocks: dict) -> dict:
    # Google docs always start with an empty sectionBreak-ish element index; keep it simple.
    return {"content": [{"sectionBreak": {}}, *blocks]}
