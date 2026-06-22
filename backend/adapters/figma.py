"""Figma clone seed viewer.

Two seed sources:
  • a local `fixture.json` (a {team, projects, files} workspace; each file a Figma document node
    tree) — bundled sample or uploaded, and
  • the upstream **figma-service docker image** (`figma-service:prod-v1` bakes a real design corpus at
    /srv/figma.db) — pulled/loaded like the slack/jira gateways; we extract the baked figma.db and
    read it with stdlib sqlite3 (its big payloads are JSON columns).

The frontend renders a Figma-like canvas + layers + inspector + comments, and the file's real
thumbnail image (prod-v1 carries a live Figma S3 thumbnail URL)."""
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

# figma-service:prod-v1 bakes the corpus here; :latest/:empty are data-free.
FIGMA_DB_PATHS = ("/srv/figma.db", "/opt/figmaclone/figma.db", "figma.db")


def _count_nodes(root: dict) -> int:
    if not isinstance(root, dict):
        return 0
    n, stack = 0, [root]
    while stack:
        node = stack.pop()
        n += 1
        stack.extend(node.get("children") or [])
    return n


class FigmaAdapter(FileSeedAdapter):
    id = "figma"
    display_name = "Figma"
    status = "active"
    ui_module = "figma"
    sample_files = ("figma.fixture.json",)

    # ---- bases: docker images (figma-service) + the bundled fixture sample ----
    def list_bases(self) -> list[BaseOption]:
        out: list[BaseOption] = []
        for ref in dockerutil.list_images("figma-service", "figma-seed"):
            out.append(BaseOption(id=ref, kind="image", ref=ref, label=ref,
                                  detail="baked figma.db corpus (docker image)"))
        out.extend(super().list_bases())  # bundled fixture.json sample(s)
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
        else:  # docker image — extract the baked figma.db
            workdir = tempfile.mkdtemp(prefix="seedview-figma-")
            dbpath = os.path.join(workdir, "figma.db")
            last = ""
            for src in FIGMA_DB_PATHS:
                try:
                    dockerutil.extract_file(base_id, src, dbpath)
                    break
                except Exception as e:
                    last = str(e)
            else:
                raise RuntimeError(
                    f"no baked figma.db in {base_id} — only figma-service:prod-v1 carries a corpus "
                    f"(:latest/:empty are data-free). {last}"
                )
            parsed = self._parse_db(dbpath)

        session_id = uuid.uuid4().hex[:12]
        self._sessions[session_id] = {"path": base_id, "parsed": parsed}
        self._current = session_id
        return LoadResult(session_id=session_id, base=base_id, overlay=None, stats=parsed["stats"])

    # ---- build the {team, projects, files} payload --------------------------
    def _payload(self, team: dict, projects: list, files: list) -> dict[str, Any]:
        return {
            "team": team or {},
            "projects": projects or [],
            "files": files,
            "stats": {
                "files": len(files),
                "nodes": sum(_count_nodes(f.get("document") or {}) for f in files),
                "comments": sum(len(f.get("comments") or []) for f in files),
            },
        }

    def _parse(self, raw: str, path: str) -> dict[str, Any]:  # JSON fixture
        d = json.loads(raw)
        return self._payload(d.get("team") or {}, d.get("projects") or [], d.get("files") or [])

    def _parse_db(self, dbpath: str) -> dict[str, Any]:
        c = sqlite3.connect(dbpath)
        c.row_factory = sqlite3.Row

        def J(x):
            return json.loads(x) if x else {}

        teams = [dict(r) for r in c.execute("SELECT id, name FROM teams")]
        proj_rows = [dict(r) for r in c.execute("SELECT id, team_id, name FROM projects")]
        proj_files: dict[str, list] = {}
        files = []
        for f in c.execute(
            "SELECT key, project_id, name, version, last_modified, thumbnail_url, "
            "document, components, component_sets, styles, images FROM files"
        ):
            comments = [
                {"id": cc["id"], "message": cc["message"], "user": J(cc["user"]),
                 "client_meta": J(cc["client_meta"]), "order_id": cc["order_id"],
                 "created_at": cc["created_at"]}
                for cc in c.execute(
                    "SELECT id, message, user, client_meta, order_id, created_at FROM comments "
                    "WHERE file_key=? ORDER BY order_id", (f["key"],))
            ]
            files.append({
                "key": f["key"], "name": f["name"], "thumbnailUrl": f["thumbnail_url"],
                "document": J(f["document"]), "components": J(f["components"]),
                "componentSets": J(f["component_sets"]), "styles": J(f["styles"]),
                "images": J(f["images"]), "comments": comments,
            })
            proj_files.setdefault(f["project_id"], []).append(f["key"])
        c.close()
        projects = [{"id": p["id"], "name": p["name"], "files": proj_files.get(p["id"], [])}
                    for p in proj_rows]
        team = {"id": teams[0]["id"], "name": teams[0]["name"]} if teams else {}
        return self._payload(team, projects, files)
