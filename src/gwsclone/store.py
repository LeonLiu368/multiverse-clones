"""Data-access + Google-shaped serialization (the seam shared by API and seeder)."""

from __future__ import annotations

import base64
import re
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import CalendarEvent, Document, DriveFile, GmailMessage

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


# ----------------------------------------------------------------- Calendar serialization


def get_event(s: Session, event_id: str) -> CalendarEvent | None:
    return s.get(CalendarEvent, event_id)


def event_resource(e: CalendarEvent) -> dict[str, Any]:
    return {
        "kind": "calendar#event",
        "id": e.id,
        "status": e.status,
        "summary": e.summary,
        "description": e.description,
        "location": e.location,
        "start": e.start or {},
        "end": e.end or {},
        "attendees": e.attendees or [],
        "organizer": e.organizer or {},
        "created": e.created,
        "updated": e.updated,
    }


def _event_start_key(e: CalendarEvent) -> str:
    st = e.start or {}
    return st.get("dateTime") or st.get("date") or ""


def list_events(s: Session, calendar_id: str, q: str | None,
                time_min: str | None, time_max: str | None) -> list[dict[str, Any]]:
    """`events.list` — filter by calendarId, free-text `q` (summary/description/
    location), and the [timeMin, timeMax) window (compared on the event start)."""
    rows = s.scalars(select(CalendarEvent)).all()
    out = []
    for e in rows:
        if calendar_id and e.calendar_id != calendar_id:
            continue
        if q and q.lower() not in f"{e.summary} {e.description} {e.location}".lower():
            continue
        sk = _event_start_key(e)
        if time_min and sk and sk < time_min:
            continue
        if time_max and sk and sk >= time_max:
            continue
        out.append(event_resource(e))
    out.sort(key=lambda r: (r["start"].get("dateTime") or r["start"].get("date") or ""))
    return out


# ----------------------------------------------------------------- Gmail serialization


def get_message(s: Session, message_id: str) -> GmailMessage | None:
    return s.get(GmailMessage, message_id)


def message_text(m: GmailMessage) -> str:
    return m.body_text or ""


def message_resource(m: GmailMessage, fmt: str = "full") -> dict[str, Any]:
    """Serialize to a Gmail message resource. `fmt`: minimal | metadata | full."""
    base = {"id": m.id, "threadId": m.thread_id, "labelIds": m.label_ids or [],
            "snippet": m.snippet, "internalDate": m.internal_date}
    if fmt == "minimal":
        return base
    headers = [{"name": "From", "value": m.from_addr}, {"name": "To", "value": m.to_addr},
               {"name": "Subject", "value": m.subject}, {"name": "Date", "value": m.date}]
    payload: dict[str, Any] = {"mimeType": "text/plain", "headers": headers}
    if fmt != "metadata":
        data = base64.urlsafe_b64encode((m.body_text or "").encode()).decode()
        payload["body"] = {"size": len(m.body_text or ""), "data": data}
    base["payload"] = payload
    return base


def list_messages(s: Session, q: str | None, page_size: int) -> list[GmailMessage]:
    rows = s.scalars(select(GmailMessage)).all()
    rows = [m for m in rows if _gmail_q_matches(q, m)]
    rows.sort(key=lambda m: m.internal_date or "", reverse=True)
    return rows[:page_size]


def thread_messages(s: Session, thread_id: str) -> list[GmailMessage]:
    rows = s.scalars(select(GmailMessage).where(GmailMessage.thread_id == thread_id)).all()
    return sorted(rows, key=lambda m: m.internal_date or "")


def _gmail_q_matches(q: str | None, m: GmailMessage) -> bool:
    """Gmail search subset: from:/to:/subject:/label: operators + free-text over
    subject+body. Operators AND together; bare terms must all appear."""
    if not q:
        return True
    hay = f"{m.from_addr} {m.to_addr} {m.subject} {m.body_text}".lower()
    for tok in q.split():
        low = tok.lower()
        if low.startswith("from:"):
            if low[5:] not in m.from_addr.lower():
                return False
        elif low.startswith("to:"):
            if low[3:] not in m.to_addr.lower():
                return False
        elif low.startswith("subject:"):
            if low[8:] not in m.subject.lower():
                return False
        elif low.startswith("label:"):
            if low[6:].upper() not in [l.upper() for l in (m.label_ids or [])]:
                return False
        elif low.startswith("newer_than:") or low.startswith("older_than:"):
            continue  # accepted but not enforced (lenient)
        else:
            if low not in hay:
                return False
    return True


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


def upsert_event(s: Session, e: dict) -> None:
    obj = s.get(CalendarEvent, e["id"])
    fields = dict(
        calendar_id=e.get("calendarId", "primary"),
        summary=e.get("summary", ""),
        description=e.get("description", ""),
        location=e.get("location", ""),
        status=e.get("status", "confirmed"),
        start=e.get("start") or {},
        end=e.get("end") or {},
        attendees=e.get("attendees", []) or [],
        organizer=e.get("organizer") or {},
        created=e.get("created", ""),
        updated=e.get("updated", ""),
    )
    if obj:
        for k, v in fields.items():
            setattr(obj, k, v)
    else:
        s.add(CalendarEvent(id=e["id"], **fields))


def upsert_message(s: Session, m: dict) -> None:
    obj = s.get(GmailMessage, m["id"])
    body = m.get("body", "")
    fields = dict(
        thread_id=m.get("threadId", m["id"]),
        label_ids=m.get("labelIds", []) or [],
        from_addr=m.get("from", ""),
        to_addr=m.get("to", ""),
        subject=m.get("subject", ""),
        date=m.get("date", ""),
        internal_date=str(m.get("internalDate", "")),
        snippet=m.get("snippet") or body[:120],
        body_text=body,
    )
    if obj:
        for k, v in fields.items():
            setattr(obj, k, v)
    else:
        s.add(GmailMessage(id=m["id"], **fields))
