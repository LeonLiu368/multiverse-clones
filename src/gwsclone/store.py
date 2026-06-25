"""Data-access + Google-shaped serialization (the seam shared by API and seeder)."""

from __future__ import annotations

import re
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Document, DriveFile

# ----------------------------------------------------------------- doc-tree helpers


def iter_text_runs(body: dict) -> Iterator[dict]:
    """Yield every textRun dict in a Docs body (walks paragraphs + nested tables)."""
    def walk(elements):
        for el in elements or []:
            para = el.get("paragraph")
            if para:
                for pe in para.get("elements", []):
                    if "textRun" in pe:
                        yield pe["textRun"]
            table = el.get("table")
            if table:
                for row in table.get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        yield from walk(cell.get("content", []))
    yield from walk(body.get("content", []))


def document_text(body: dict) -> str:
    """The plain-text content of a Docs body (concatenated textRuns)."""
    return "".join(tr.get("content", "") for tr in iter_text_runs(body))


def iter_paragraphs(body: dict) -> Iterator[tuple[str, str]]:
    """Yield (namedStyleType, text) per top-level paragraph (for search/structure)."""
    for el in body.get("content", []) or []:
        para = el.get("paragraph")
        if not para:
            continue
        style = (para.get("paragraphStyle") or {}).get("namedStyleType", "NORMAL_TEXT")
        text = "".join(pe.get("textRun", {}).get("content", "") for pe in para.get("elements", []))
        yield style, text


# ----------------------------------------------------------------- Drive serialization


def get_file(s: Session, file_id: str) -> DriveFile | None:
    return s.get(DriveFile, file_id)


def file_resource(f: DriveFile) -> dict[str, Any]:
    r = {
        "kind": "drive#file",
        "id": f.id,
        "name": f.name,
        "mimeType": f.mime_type,
        "parents": f.parents or [],
        "createdTime": f.created_time,
        "modifiedTime": f.modified_time,
        "owners": f.owners or [],
        "trashed": f.trashed,
    }
    if f.size is not None:
        r["size"] = f.size
    return r


def list_files(s: Session, q: str | None, page_size: int) -> list[dict[str, Any]]:
    """`files.list` with a minimal subset of Drive's `q`: name contains/=, mimeType=, trashed=."""
    rows = s.scalars(select(DriveFile).order_by(DriveFile.name)).all()
    out = []
    for f in rows:
        if not _q_matches(q, f):
            continue
        out.append(file_resource(f))
        if len(out) >= page_size:
            break
    return out


def _q_matches(q: str | None, f: DriveFile) -> bool:
    if not q:
        return f.trashed is False  # Drive default excludes trashed
    ok = True
    for clause in re.split(r"\s+and\s+", q.strip(), flags=re.I):
        c = clause.strip()
        m = re.match(r"name\s+contains\s+'(.*)'", c, re.I)
        if m:
            ok = ok and (m.group(1).lower() in f.name.lower()); continue
        m = re.match(r"name\s*=\s*'(.*)'", c, re.I)
        if m:
            ok = ok and (f.name == m.group(1)); continue
        m = re.match(r"mimeType\s*=\s*'(.*)'", c, re.I)
        if m:
            ok = ok and (f.mime_type == m.group(1)); continue
        m = re.match(r"'(.*)'\s+in\s+parents", c, re.I)
        if m:
            ok = ok and (m.group(1) in (f.parents or [])); continue
        m = re.match(r"trashed\s*=\s*(true|false)", c, re.I)
        if m:
            ok = ok and (f.trashed == (m.group(1).lower() == "true")); continue
        # unknown clause -> ignore (lenient)
    return ok


# ----------------------------------------------------------------- Docs serialization


def get_document(s: Session, document_id: str) -> Document | None:
    return s.get(Document, document_id)


def document_resource(d: Document) -> dict[str, Any]:
    return {
        "documentId": d.document_id,
        "title": d.title,
        "revisionId": d.revision_id,
        "body": d.body or {"content": []},
        "namedStyles": d.named_styles or {},
        "inlineObjects": d.inline_objects or {},
    }


# ----------------------------------------------------------------- seed upserts


def upsert_file(s: Session, f: dict) -> None:
    obj = s.get(DriveFile, f["id"])
    fields = dict(
        name=f.get("name", "Untitled"),
        mime_type=f.get("mimeType", "application/vnd.google-apps.document"),
        parents=f.get("parents", []) or [],
        created_time=f.get("createdTime", ""),
        modified_time=f.get("modifiedTime", ""),
        owners=f.get("owners", []) or [],
        size=f.get("size"),
        trashed=bool(f.get("trashed", False)),
    )
    if obj:
        for k, v in fields.items():
            setattr(obj, k, v)
    else:
        s.add(DriveFile(id=f["id"], **fields))


def upsert_document(s: Session, d: dict) -> None:
    did = d.get("documentId") or d["id"]
    obj = s.get(Document, did)
    fields = dict(
        title=d.get("title", "Untitled"),
        revision_id=str(d.get("revisionId", "1")),
        body=d.get("body") or {"content": []},
        named_styles=d.get("namedStyles") or {},
        inline_objects=d.get("inlineObjects") or {},
    )
    if obj:
        for k, v in fields.items():
            setattr(obj, k, v)
    else:
        s.add(Document(document_id=did, **fields))
