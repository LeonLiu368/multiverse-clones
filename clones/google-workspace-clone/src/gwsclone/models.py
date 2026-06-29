"""SQLAlchemy ORM models for the Google Workspace clone (SQLite-backed).

Two object types in this slice, mirroring how Google models them:

* **DriveFile** — a Drive v3 file resource (id, name, mimeType, parents, …). A
  Google Doc *is* a Drive file whose mimeType is
  ``application/vnd.google-apps.document``.
* **Document** — the Docs v1 document body for such a file. Its ``document_id``
  equals the Drive file id. The body is the deeply-nested structural-element tree
  (``body.content`` → paragraphs → textRuns → …) that the real ``documents.get``
  returns; we store it as a JSON column and serve it verbatim — the doc tree is
  the gradeable payload (the Figma-node-tree analogue).

* **CalendarEvent** — a Calendar v3 event resource (id, summary, start/end as
  ``{dateTime|date}``, attendees, organizer, status). Belongs to a ``calendar_id``
  (Google's "primary" by default).
* **GmailMessage** — a Gmail v1 message (id, threadId, labelIds, the RFC-2822
  headers we care about — From/To/Subject/Date — plus the plaintext body and a
  snippet). Served back in Gmail's ``payload.headers`` + base64url ``body.data``
  shape; threads group messages by ``thread_id``.

Sheets remains out of scope (cells-as-rows is the next surface).
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DriveFile(Base):
    __tablename__ = "drive_files"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, default="Untitled")
    mime_type: Mapped[str] = mapped_column(String, default="application/vnd.google-apps.document")
    parents: Mapped[list] = mapped_column(JSON, default=list)  # parent folder ids
    created_time: Mapped[str] = mapped_column(String, default="")
    modified_time: Mapped[str] = mapped_column(String, default="")
    owners: Mapped[list] = mapped_column(JSON, default=list)  # [{displayName, emailAddress}]
    size: Mapped[str | None] = mapped_column(String, nullable=True)
    trashed: Mapped[bool] = mapped_column(default=False)


class Document(Base):
    __tablename__ = "documents"
    document_id: Mapped[str] = mapped_column(String, ForeignKey("drive_files.id"), primary_key=True)
    title: Mapped[str] = mapped_column(String, default="Untitled")
    revision_id: Mapped[str] = mapped_column(String, default="1")
    body: Mapped[dict] = mapped_column(JSON, default=dict)  # {"content": [structural elements...]}
    named_styles: Mapped[dict] = mapped_column(JSON, default=dict)
    inline_objects: Mapped[dict] = mapped_column(JSON, default=dict)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    calendar_id: Mapped[str] = mapped_column(String, default="primary")
    summary: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="confirmed")
    start: Mapped[dict] = mapped_column(JSON, default=dict)  # {"dateTime"|"date": ...}
    end: Mapped[dict] = mapped_column(JSON, default=dict)
    attendees: Mapped[list] = mapped_column(JSON, default=list)  # [{email, responseStatus}]
    organizer: Mapped[dict] = mapped_column(JSON, default=dict)  # {email, displayName}
    created: Mapped[str] = mapped_column(String, default="")
    updated: Mapped[str] = mapped_column(String, default="")


class GmailMessage(Base):
    __tablename__ = "gmail_messages"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    thread_id: Mapped[str] = mapped_column(String, default="")
    label_ids: Mapped[list] = mapped_column(JSON, default=list)  # ["INBOX", "UNREAD", ...]
    from_addr: Mapped[str] = mapped_column(String, default="")
    to_addr: Mapped[str] = mapped_column(String, default="")
    subject: Mapped[str] = mapped_column(String, default="")
    date: Mapped[str] = mapped_column(String, default="")       # RFC-2822 Date header
    internal_date: Mapped[str] = mapped_column(String, default="")  # epoch ms, for ordering
    snippet: Mapped[str] = mapped_column(String, default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
