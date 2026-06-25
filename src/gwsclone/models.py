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

Sheets/Gmail/Calendar are deliberately out of scope for this vertical slice.
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
