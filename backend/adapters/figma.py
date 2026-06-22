"""Figma clone seed viewer — a `fixture.json` workspace: {team, projects, files}, where each file
holds a Figma document node tree (FRAME/COMPONENT/TEXT/… with absoluteBoundingBox, fills, characters,
cornerRadius, style) plus comments. Read-only; the frontend renders a canvas + layers + inspector."""
from __future__ import annotations

import json
from typing import Any

from adapters.fileseed import FileSeedAdapter


def _count_nodes(n: dict) -> int:
    if not isinstance(n, dict):
        return 0
    return 1 + sum(_count_nodes(c) for c in (n.get("children") or []))


class FigmaAdapter(FileSeedAdapter):
    id = "figma"
    display_name = "Figma"
    status = "active"
    ui_module = "figma"
    sample_files = ("figma.fixture.json",)

    def _parse(self, raw: str, path: str) -> dict[str, Any]:
        d = json.loads(raw)
        files = d.get("files") or []
        return {
            "team": d.get("team") or {},
            "projects": d.get("projects") or [],
            "files": files,
            "stats": {
                "files": len(files),
                "nodes": sum(_count_nodes(f.get("document") or {}) for f in files),
                "comments": sum(len(f.get("comments") or []) for f in files),
            },
        }
