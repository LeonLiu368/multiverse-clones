"""Google Workspace clone seed viewer (abundant-gworkspace-clone).

Two seed sources, normalized to one shape:
  • a local `fixture.json` — `{drive:[…], documents:[…]}` (camelCase, the shape `gws-cli seed load`
    ingests), optionally also `calendar`/`gmail`; bundled sample or uploaded, and
  • the upstream **gworkspace image** (`…/gws-service:prod-v1` bakes the SQLite corpus at
    `/srv/gws.db`) — pulled/extracted like figma, read with stdlib sqlite3 (snake_case columns +
    JSON blobs for parents/owners/body).

The frontend renders a Google-Drive-style file browser (folder tree by `parents`, icons by
mimeType) + a Google-Docs document renderer (the `body.content` structural tree → headings /
paragraphs / styled textRuns), plus Calendar/Gmail if the corpus carries them."""
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

GWS_DB_PATHS = ("/srv/gws.db", "/data/gws.db", "gws.db")
FOLDER_MIME = "application/vnd.google-apps.folder"


def _doc_text(body: dict) -> tuple[str, list[dict]]:
    """Flatten a Docs `body.content` structural tree to plain text + a heading outline."""
    lines: list[str] = []
    headings: list[dict] = []
    for el in (body or {}).get("content", []):
        para = el.get("paragraph")
        if not para:
            continue
        text = "".join(
            (e.get("textRun") or {}).get("content", "") for e in para.get("elements", [])
        )
        style = (para.get("paragraphStyle") or {}).get("namedStyleType", "NORMAL_TEXT")
        if style.startswith("HEADING_") and text.strip():
            try:
                level = int(style.split("_")[1])
            except Exception:
                level = 1
            headings.append({"level": level, "text": text.strip()})
        lines.append(text)
    return "".join(lines), headings


class GworkspaceAdapter(FileSeedAdapter):
    id = "gworkspace"
    display_name = "Workspace"
    status = "active"
    ui_module = "gworkspace"
    sample_files = ("gworkspace.fixture.json",)

    def list_bases(self) -> list[BaseOption]:
        out: list[BaseOption] = []
        # multiverse-clones bakes the corpus into `gworkspace-service:prod-v1` at /srv/gws.db.
        for ref in dockerutil.list_images("gworkspace-service", "gws-service", "gws-gateway", "google-workspace"):
            out.append(BaseOption(id=ref, kind="image", ref=ref, label=ref,
                                  detail="baked gws.db corpus (docker image)"))
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
        else:  # docker image — extract the baked gws.db
            workdir = tempfile.mkdtemp(prefix="seedview-gws-")
            dbpath = os.path.join(workdir, "gws.db")
            last = ""
            for src in GWS_DB_PATHS:
                try:
                    dockerutil.extract_file(base_id, src, dbpath)
                    break
                except Exception as e:
                    last = str(e)
            else:
                raise RuntimeError(
                    f"no baked gws.db in {base_id} (probed {GWS_DB_PATHS}); only the prod-v1 "
                    f"gworkspace image bakes a corpus. {last}"
                )
            parsed = self._parse_db(dbpath)

        session_id = uuid.uuid4().hex[:12]
        self._sessions[session_id] = {"path": base_id, "parsed": parsed}
        self._current = session_id
        return LoadResult(session_id=session_id, base=base_id, overlay=None, stats=parsed["stats"])

    # ---- normalization to one shape ----------------------------------------
    def _file(self, *, id, name, mimeType, parents, createdTime, modifiedTime, owners, size, trashed):
        return {
            "id": id, "name": name, "mimeType": mimeType,
            "parents": parents or [], "createdTime": createdTime, "modifiedTime": modifiedTime,
            "owners": owners or [], "size": size, "trashed": bool(trashed),
            "isFolder": mimeType == FOLDER_MIME,
        }

    def _document(self, *, documentId, title, revisionId, body, namedStyles):
        text, headings = _doc_text(body or {})
        return {
            "documentId": documentId, "title": title, "revisionId": revisionId,
            "body": body or {}, "namedStyles": namedStyles or {},
            "text": text, "headings": headings,
        }

    def _build_tree(self, files: list[dict]) -> list[dict]:
        """Nest files under their folder `parents` (roots = parent 'root' or an unknown id)."""
        by_id = {f["id"]: f for f in files}
        children: dict[str, list[dict]] = {}
        roots: list[dict] = []
        for f in files:
            parent = next((p for p in f["parents"] if p in by_id), None)
            (children.setdefault(parent, []) if parent else roots).append(f)
        # parents pointing at "root"/unknown also become roots
        for f in files:
            if f not in roots and not any(p in by_id for p in f["parents"]):
                if f not in roots:
                    roots.append(f)

        def node(f: dict) -> dict:
            kids = sorted(children.get(f["id"], []), key=lambda x: (not x["isFolder"], x["name"].lower()))
            return {**f, "children": [node(k) for k in kids]}

        seen: set[str] = set()
        out = []
        for f in sorted(roots, key=lambda x: (not x["isFolder"], x["name"].lower())):
            if f["id"] in seen:
                continue
            seen.add(f["id"])
            out.append(node(f))
        return out

    def _payload(self, files, documents, events, messages) -> dict[str, Any]:
        return {
            "meta": {"source": "gworkspace"},
            "files": files,
            "tree": self._build_tree(files),
            "documents": documents,
            "events": events,
            "messages": messages,
            "stats": {
                "files": sum(1 for f in files if not f["isFolder"]),
                "folders": sum(1 for f in files if f["isFolder"]),
                "documents": len(documents),
                "events": len(events),
                "messages": len(messages),
            },
        }

    def _parse(self, raw: str, path: str) -> dict[str, Any]:  # JSON fixture (camelCase)
        d = json.loads(raw)
        files = [
            self._file(
                id=f.get("id"), name=f.get("name"), mimeType=f.get("mimeType"),
                parents=f.get("parents"), createdTime=f.get("createdTime"),
                modifiedTime=f.get("modifiedTime"), owners=f.get("owners"),
                size=f.get("size"), trashed=f.get("trashed"),
            )
            for f in (d.get("drive") or d.get("files") or [])
        ]
        documents = [
            self._document(
                documentId=doc.get("documentId") or doc.get("id"), title=doc.get("title"),
                revisionId=doc.get("revisionId"), body=doc.get("body"),
                namedStyles=doc.get("namedStyles"),
            )
            for doc in (d.get("documents") or [])
        ]
        events = list(d.get("calendar") or d.get("events") or [])
        messages = list(d.get("gmail") or d.get("messages") or [])
        return self._payload(files, documents, events, messages)

    def _parse_db(self, dbpath: str) -> dict[str, Any]:  # baked gws.db (snake_case + JSON cols)
        c = sqlite3.connect(dbpath)
        c.row_factory = sqlite3.Row

        def J(x, default):
            try:
                return json.loads(x) if x else default
            except Exception:
                return default

        def table(name: str) -> set[str]:
            return {r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))}

        files = [
            self._file(
                id=r["id"], name=r["name"], mimeType=r["mime_type"], parents=J(r["parents"], []),
                createdTime=r["created_time"], modifiedTime=r["modified_time"],
                owners=J(r["owners"], []), size=r["size"], trashed=r["trashed"],
            )
            for r in c.execute("SELECT * FROM drive_files")
        ] if table("drive_files") else []

        documents = [
            self._document(
                documentId=r["document_id"], title=r["title"], revisionId=r["revision_id"],
                body=J(r["body"], {}), namedStyles=J(r["named_styles"], {}),
            )
            for r in c.execute("SELECT * FROM documents")
        ] if table("documents") else []

        events = [
            {"id": r["id"], "calendarId": r["calendar_id"], "summary": r["summary"],
             "description": r["description"], "location": r["location"], "status": r["status"],
             "start": J(r["start"], {}), "end": J(r["end"], {}), "attendees": J(r["attendees"], []),
             "organizer": J(r["organizer"], {}), "created": r["created"], "updated": r["updated"]}
            for r in c.execute("SELECT * FROM calendar_events")
        ] if table("calendar_events") else []

        messages = [
            {"id": r["id"], "threadId": r["thread_id"], "labelIds": J(r["label_ids"], []),
             "from": r["from_addr"], "to": r["to_addr"], "subject": r["subject"], "date": r["date"],
             "snippet": r["snippet"], "bodyText": r["body_text"]}
            for r in c.execute("SELECT * FROM gmail_messages")
        ] if table("gmail_messages") else []

        c.close()
        return self._payload(files, documents, events, messages)
