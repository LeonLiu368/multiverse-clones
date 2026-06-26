"""Import a real **Google Takeout** export into a canonical seed (real2sim).

Takeout gives each surface its own standard on-disk format; this maps them onto
the seed shape in ``schema`` (stdlib only — no extra deps):

  * **Mail**     ``Takeout/Mail/*.mbox``      — RFC-822 mbox. Gmail stamps each
                 message with ``X-GM-THRID`` (thread id), ``X-GM-MSGID`` (message
                 id) and ``X-Gmail-Labels`` (comma-separated), which we use
                 directly so threads/labels survive the round-trip.
  * **Calendar** ``Takeout/Calendar/*.ics``    — iCalendar; each ``VEVENT`` → an
                 event (UID, SUMMARY, DTSTART/DTEND → ``{dateTime}``/``{date}``,
                 DESCRIPTION, LOCATION, STATUS, ORGANIZER, ATTENDEE).
  * **Drive**    ``Takeout/Drive/`` tree        — native files become Drive file
                 resources (mimeType guessed from extension); Google Docs exported
                 as ``.html``/``.txt`` are additionally parsed into a Docs body so
                 ``documents.get`` / ``docs text`` work.

Point it at the unzipped ``Takeout/`` root (auto-discovers all three) or at an
individual ``.mbox`` / ``.ics`` / Drive dir.
"""

from __future__ import annotations

import email.utils
import hashlib
import mailbox
import pathlib
import re
from email.header import decode_header, make_header
from html.parser import HTMLParser
from typing import Any

from . import schema
from .schema import DOC_MIME

# ----------------------------------------------------------------- helpers


def _stable_id(prefix: str, *parts: str) -> str:
    h = hashlib.sha1("|".join(parts).encode()).hexdigest()[:24]
    return f"{prefix}_{h}"


def _hdr(msg, name: str) -> str:
    raw = msg.get(name)
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return str(raw)


def _epoch_ms(date_hdr: str) -> str:
    try:
        dt = email.utils.parsedate_to_datetime(date_hdr)
        return str(int(dt.timestamp() * 1000))
    except Exception:
        return ""


# ----------------------------------------------------------------- Mail (.mbox)


def _mbox_body(msg) -> str:
    """Best-effort plaintext body (prefer text/plain; strip HTML if that's all)."""
    def decode(part) -> str:
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")

    if msg.is_multipart():
        plain, html = "", ""
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and not plain:
                plain = decode(part)
            elif ct == "text/html" and not html:
                html = decode(part)
        return plain or _strip_html(html)
    body = decode(msg)
    return body if msg.get_content_type() != "text/html" else _strip_html(body)


def parse_mbox(path: str, limit: int | None = None) -> list[dict]:
    box = mailbox.mbox(path)
    out: list[dict] = []
    for i, msg in enumerate(box):
        if limit is not None and i >= limit:
            break
        msg_id = (_hdr(msg, "X-GM-MSGID") or _hdr(msg, "Message-ID").strip("<>")
                  or _stable_id("MSG", path, str(i)))
        thread_id = _hdr(msg, "X-GM-THRID") or msg_id
        labels = [l.strip() for l in _hdr(msg, "X-Gmail-Labels").split(",") if l.strip()]
        date = _hdr(msg, "Date")
        body = _mbox_body(msg)
        out.append(schema.message(
            msg_id, _hdr(msg, "Subject"), body,
            frm=_hdr(msg, "From"), to=_hdr(msg, "To"),
            thread_id=str(thread_id), date=date, internal_date=_epoch_ms(date),
            labels=labels or ["INBOX"],
        ))
    return out


# ----------------------------------------------------------------- Calendar (.ics)


def _ics_unfold(text: str) -> list[str]:
    """RFC-5545 line unfolding: a leading space/tab continues the previous line."""
    lines: list[str] = []
    for raw in text.splitlines():
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _ics_when(value: str, params: str) -> dict:
    """DTSTART/DTEND value → {"date": "YYYY-MM-DD"} or {"dateTime": RFC-3339}."""
    if "VALUE=DATE" in params or re.fullmatch(r"\d{8}", value):
        return {"date": f"{value[0:4]}-{value[4:6]}-{value[6:8]}"}
    m = re.match(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z)?", value)
    if m:
        y, mo, d, h, mi, s, z = m.groups()
        return {"dateTime": f"{y}-{mo}-{d}T{h}:{mi}:{s}{'Z' if z else ''}"}
    return {"dateTime": value}


def parse_ics(path: str, limit: int | None = None) -> list[dict]:
    lines = _ics_unfold(pathlib.Path(path).read_text(errors="replace"))
    events: list[dict] = []
    cur: dict | None = None
    for line in lines:
        if line.startswith("BEGIN:VEVENT"):
            cur = {"attendees": []}
        elif line.startswith("END:VEVENT") and cur is not None:
            events.append(cur)
            cur = None
            if limit is not None and len(events) >= limit:
                break
        elif cur is not None and ":" in line:
            name_params, _, value = line.partition(":")
            name, _, params = name_params.partition(";")
            name = name.upper()
            if name == "UID":
                cur["uid"] = value
            elif name == "SUMMARY":
                cur["summary"] = value
            elif name == "DESCRIPTION":
                cur["description"] = value.replace("\\n", "\n").replace("\\,", ",")
            elif name == "LOCATION":
                cur["location"] = value.replace("\\,", ",")
            elif name == "STATUS":
                cur["status"] = value.lower()
            elif name == "DTSTART":
                cur["start"] = _ics_when(value, params)
            elif name == "DTEND":
                cur["end"] = _ics_when(value, params)
            elif name == "ORGANIZER":
                cur["organizer"] = {"email": value.replace("mailto:", "")}
            elif name == "ATTENDEE":
                cur["attendees"].append({"email": value.replace("mailto:", "")})

    out: list[dict] = []
    for e in events:
        start = e.get("start", {})
        sval = start.get("dateTime") or start.get("date") or "1970-01-01"
        out.append(schema.event(
            e.get("uid") or _stable_id("EVT", path, e.get("summary", "")),
            e.get("summary", "(no title)"), sval,
            (e.get("end") or {}).get("dateTime") or (e.get("end") or {}).get("date") or sval,
            location=e.get("location", ""), description=e.get("description", ""),
            organizer=e.get("organizer") or {}, attendees=e.get("attendees") or [],
            status=e.get("status", "confirmed"),
        ))
    return out


# ----------------------------------------------------------------- Drive tree


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)

    def handle_starttag(self, tag, attrs) -> None:
        if tag in ("p", "br", "div", "h1", "h2", "h3", "li", "tr"):
            self.parts.append("\n")


def _strip_html(html: str) -> str:
    p = _TextExtractor()
    try:
        p.feed(html)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\n{3,}", "\n\n", "".join(p.parts)).strip()


_MIME = {
    ".pdf": "application/pdf", ".csv": "text/csv", ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".png": "image/png", ".jpg": "image/jpeg", ".json": "application/json",
}
_DOC_EXTS = {".html", ".htm", ".txt"}  # exts we can turn into a Docs body


def parse_drive_dir(root: str, limit: int | None = None) -> tuple[list[dict], list[dict]]:
    base = pathlib.Path(root)
    drive: list[dict] = []
    documents: list[dict] = []
    n = 0
    for path in sorted(base.rglob("*")):
        if path.is_dir() or path.name.endswith("-metadata.json"):
            continue
        if limit is not None and n >= limit:
            break
        n += 1
        rel = path.relative_to(base)
        ext = path.suffix.lower()
        fid = _stable_id("FILE", str(rel))
        mime = _MIME.get(ext, DOC_MIME if ext in _DOC_EXTS else "application/octet-stream")
        parents = ["root"] if rel.parent == pathlib.Path(".") else [_stable_id("FOLDER", str(rel.parent))]
        drive.append({
            "id": fid, "name": path.stem if ext in _DOC_EXTS else path.name,
            "mimeType": mime, "parents": parents,
            "modifiedTime": "", "size": str(path.stat().st_size),
        })
        if ext in _DOC_EXTS:
            raw = path.read_text(errors="replace")
            text = _strip_html(raw) if ext in (".html", ".htm") else raw
            blocks = [schema.paragraph(line + "\n")
                      for line in text.splitlines() if line.strip()]
            documents.append({"documentId": fid, "title": path.stem,
                              "body": schema.make_body(*blocks)})
    return drive, documents


# ----------------------------------------------------------------- top-level


def import_takeout(root: str | None = None, *, mbox: str | None = None,
                   ics: str | None = None, drive_dir: str | None = None,
                   limit: int | None = None) -> dict[str, Any]:
    """Build a canonical seed from a Takeout root and/or individual exports."""
    drive: list[dict] = []
    documents: list[dict] = []
    gmail: list[dict] = []
    calendar: list[dict] = []

    if root:
        base = pathlib.Path(root)

        def _discover(*globs: str) -> list[pathlib.Path]:
            seen: dict[pathlib.Path, None] = {}
            for g in globs:
                for p in sorted(base.glob(g)):
                    seen.setdefault(p.resolve(), None)
            return list(seen)

        mboxes = _discover("Mail/*.mbox", "**/*.mbox")
        if mboxes:
            gmail += parse_mbox(str(mboxes[0]), limit)  # canonical "All mail*.mbox"
        for ic in _discover("Calendar/*.ics", "**/*.ics"):
            calendar += parse_ics(str(ic), limit)
        drive_root = base / "Drive"
        if drive_root.is_dir():
            d, docs = parse_drive_dir(str(drive_root), limit)
            drive += d
            documents += docs

    if mbox:
        gmail += parse_mbox(mbox, limit)
    if ics:
        calendar += parse_ics(ics, limit)
    if drive_dir:
        d, docs = parse_drive_dir(drive_dir, limit)
        drive += d
        documents += docs

    return schema.normalize({"drive": drive, "documents": documents,
                             "calendar": calendar, "gmail": gmail})
