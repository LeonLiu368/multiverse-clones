"""Data-access + Google-shaped serialization (the seam shared by API and seeder)."""

from __future__ import annotations

import base64
import re
from datetime import datetime, timezone
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
    """`files.list` with a faithful subset of Drive's `q` grammar.

    Supports the real operators — ``name``/``fullText``/``mimeType`` with
    ``contains``/``=``/``!=``, ``'<id>' in parents``, ``trashed = true|false`` —
    combined with ``and`` / ``or`` / ``not`` and parentheses. ``fullText contains``
    searches the file's CONTENT (its Doc body) plus its name, like real Drive. An
    unrecognized clause raises :class:`QueryError` (the API returns 400), instead
    of silently matching everything. Trashed files are excluded unless the query
    mentions ``trashed``.
    """
    rows = s.scalars(select(DriveFile).order_by(DriveFile.name)).all()
    pred = _compile_bool(q, _drive_term)  # raises QueryError on a bad query
    needs_text = bool(q) and "fulltext" in q.lower()
    text_map: dict[str, str] = {}
    if needs_text:
        for d in s.scalars(select(Document)).all():
            text_map[d.document_id] = document_text(d.body)
    exclude_trashed = not q or "trashed" not in q.lower()
    out = []
    for f in rows:
        if exclude_trashed and f.trashed:
            continue
        if pred is not None and not pred(f, text_map.get(f.id, "")):
            continue
        out.append(file_resource(f))
        if len(out) >= page_size:
            break
    return out


class QueryError(ValueError):
    """Malformed search query — surfaced by the API as HTTP 400 (like Google)."""


# ---- a small boolean query engine, shared by Drive `q` and Gmail `q` ----------
# Predicates are callables (obj, text) -> bool. `_compile_bool` builds the
# and/or/not/paren tree; per-surface `*_term` functions compile a single clause.


def _tokenize_bool(q: str) -> list:
    toks: list = []
    i, n = 0, len(q)
    while i < n:
        c = q[i]
        if c.isspace():
            i += 1; continue
        if c in "()":
            toks.append(c); i += 1; continue
        m = re.match(r"(and|or|not)\b", q[i:], re.I)
        if m:
            toks.append(m.group(1).upper()); i += m.end(); continue
        j, buf = i, []
        while j < n:
            cj = q[j]
            if cj == "'":                      # consume a quoted string whole
                buf.append(cj); j += 1
                while j < n and q[j] != "'":
                    buf.append(q[j]); j += 1
                if j < n:
                    buf.append(q[j]); j += 1
                continue
            if cj in "()" or re.match(r"\s+(and|or|not)\b", q[j:], re.I):
                break
            buf.append(cj); j += 1
        toks.append(("TERM", "".join(buf).strip()))
        i = j
    return toks


def _tokenize_gmail(q: str) -> list:
    """Gmail tokenizer: atoms are whitespace-separated (space == implicit AND);
    ``OR``/``NOT`` and parens are operators; quotes group a phrase into one atom."""
    toks: list = []
    i, n = 0, len(q)
    while i < n:
        c = q[i]
        if c.isspace():
            i += 1; continue
        if c in "()":
            toks.append(c); i += 1; continue
        j, buf = i, []
        while j < n and not q[j].isspace() and q[j] not in "()":
            if q[j] in "'\"":
                qc = q[j]; buf.append(q[j]); j += 1
                while j < n and q[j] != qc:
                    buf.append(q[j]); j += 1
                if j < n:
                    buf.append(q[j]); j += 1
                continue
            buf.append(q[j]); j += 1
        atom = "".join(buf)
        toks.append(atom.upper() if atom.upper() in ("AND", "OR", "NOT") else ("TERM", atom))
        i = j
    return toks


def _compile_bool(q: str | None, compile_term, tokenizer=_tokenize_bool):
    """Compile a boolean query string to a predicate, or None for an empty query."""
    if not q or not q.strip():
        return None
    tokens = tokenizer(q)
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def primary():
        nonlocal pos
        t = peek()
        if t == "(":
            pos += 1
            node = parse_or()
            if peek() != ")":
                raise QueryError("unbalanced parentheses")
            pos += 1
            return node
        if t == "NOT":
            pos += 1
            inner = primary()
            return lambda o, x: not inner(o, x)
        if isinstance(t, tuple) and t[0] == "TERM":
            pos += 1
            return compile_term(t[1])
        raise QueryError(f"unexpected token: {t!r}")

    def parse_and():
        node = primary()
        while True:
            t = peek()
            if t == "AND":
                pos_advance()
                rhs = primary()
            elif (isinstance(t, tuple) and t[0] == "TERM") or t in ("(", "NOT"):
                rhs = primary()  # implicit AND (Gmail: space == AND)
            else:
                break
            node = (lambda a, b: (lambda o, x: a(o, x) and b(o, x)))(node, rhs)
        return node

    def pos_advance():
        nonlocal pos
        pos += 1

    def parse_or():
        node = parse_and()
        while peek() == "OR":
            pos_advance()
            rhs = parse_and()
            node = (lambda a, b: (lambda o, x: a(o, x) or b(o, x)))(node, rhs)
        return node

    tree = parse_or()
    if pos != len(tokens):
        raise QueryError(f"trailing tokens at {peek()!r}")
    return tree


def _drive_term(term: str):
    t = term.strip()
    m = re.fullmatch(r"name\s+contains\s+'(.*)'", t, re.I)
    if m:
        v = m.group(1).lower(); return lambda f, x: v in f.name.lower()
    m = re.fullmatch(r"name\s*=\s*'(.*)'", t, re.I)
    if m:
        v = m.group(1); return lambda f, x: f.name == v
    m = re.fullmatch(r"name\s*!=\s*'(.*)'", t, re.I)
    if m:
        v = m.group(1); return lambda f, x: f.name != v
    m = re.fullmatch(r"fullText\s+contains\s+'(.*)'", t, re.I)
    if m:
        v = m.group(1).lower(); return lambda f, x: v in x.lower() or v in f.name.lower()
    m = re.fullmatch(r"mimeType\s*=\s*'(.*)'", t, re.I)
    if m:
        v = m.group(1); return lambda f, x: f.mime_type == v
    m = re.fullmatch(r"mimeType\s*!=\s*'(.*)'", t, re.I)
    if m:
        v = m.group(1); return lambda f, x: f.mime_type != v
    m = re.fullmatch(r"'(.*)'\s+in\s+parents", t, re.I)
    if m:
        v = m.group(1); return lambda f, x: v in (f.parents or [])
    m = re.fullmatch(r"trashed\s*=\s*(true|false)", t, re.I)
    if m:
        val = m.group(1).lower() == "true"; return lambda f, x: bool(f.trashed) == val
    raise QueryError(f"Invalid query term: {term!r}")


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


def file_text(s: Session, file_id: str) -> str | None:
    """Plain-text content of a file, if we have an extractable body (else None)."""
    d = s.get(Document, file_id)
    return document_text(d.body) if d else None


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


def _norm_when(v: Any) -> dict[str, Any]:
    """Coerce a Calendar start/end into Google's {dateTime|date} object."""
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v:
        return {"date": v} if len(v) == 10 else {"dateTime": v}
    return {}


def insert_event(s: Session, calendar_id: str, body: dict[str, Any]) -> CalendarEvent:
    """`events.insert` — create a Calendar event (Google allocates the id).

    Mirrors the real API: a POST body with at least ``summary`` + ``start`` + ``end``;
    the server mints an opaque id and ``created``/``updated`` timestamps. Raises
    :class:`QueryError` (surfaced as 400) when the required fields are missing, like
    Google's INVALID_ARGUMENT.
    """
    summary = body.get("summary")
    start = _norm_when(body.get("start"))
    end = _norm_when(body.get("end"))
    if not summary or not start or not end:
        raise QueryError("events.insert requires summary, start, and end")
    from .ids import gen_event_id
    eid = body.get("id") or gen_event_id()
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    ev = CalendarEvent(
        id=eid,
        calendar_id=calendar_id or "primary",
        summary=summary,
        description=body.get("description", "") or "",
        location=body.get("location", "") or "",
        status=body.get("status", "confirmed") or "confirmed",
        start=start,
        end=end,
        attendees=body.get("attendees", []) or [],
        organizer=body.get("organizer") or {},
        created=now,
        updated=now,
    )
    s.add(ev)
    s.commit()
    return ev


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
    """`messages.list` — Gmail search: from:/to:/subject:/label: operators + bare
    free-text (over from+to+subject+body), combined with implicit AND (space),
    explicit ``OR``, and parentheses."""
    pred = _compile_bool(q, _gmail_term, tokenizer=_tokenize_gmail)
    rows = s.scalars(select(GmailMessage)).all()
    if pred is not None:
        rows = [m for m in rows if pred(m, "")]
    rows.sort(key=lambda m: m.internal_date or "", reverse=True)
    return rows[:page_size]


def thread_messages(s: Session, thread_id: str) -> list[GmailMessage]:
    rows = s.scalars(select(GmailMessage).where(GmailMessage.thread_id == thread_id)).all()
    return sorted(rows, key=lambda m: m.internal_date or "")


def _gmail_term(term: str):
    t = term.strip()
    low = t.lower()
    for op, attr in (("from:", "from_addr"), ("to:", "to_addr"), ("subject:", "subject")):
        if low.startswith(op):
            v = t[len(op):].strip().strip("'\"").lower()
            return lambda m, _x, attr=attr, v=v: v in (getattr(m, attr) or "").lower()
    if low.startswith("label:"):
        v = t[6:].strip().strip("'\"").upper()
        return lambda m, _x, v=v: v in [l.upper() for l in (m.label_ids or [])]
    if low.split(":", 1)[0] in ("newer_than", "older_than", "after", "before", "in", "has", "is"):
        return lambda m, _x: True  # accepted but not enforced
    v = t.strip("'\"").lower()
    return lambda m, _x, v=v: v in f"{m.from_addr} {m.to_addr} {m.subject} {m.body_text}".lower()


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
