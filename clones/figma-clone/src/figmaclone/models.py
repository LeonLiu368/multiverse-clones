"""SQLAlchemy ORM models for the Figma clone (SQLite-backed).

Figma-faithful shape. A Figma *file* is dominated by one deeply-nested
**document node tree** (DOCUMENT → CANVAS → FRAME → … → TEXT/RECTANGLE), plus
maps of components/componentSets/styles and a node→image map. Those nested
structures are stored as JSON columns on ``File`` rather than shredded into
tables — the tree IS the payload, and we serve it back the way the real
``GET /v1/files/:key`` does.

*Comments* and *versions* are separate rows so that an agent posting a comment
(``POST /v1/files/:key/comments``) appends a row a verifier can read back, and so
new comments get a fresh monotonic ``order_id`` distinct from the seeded ones.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # T…
    name: Mapped[str] = mapped_column(String, default="team")


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # P…
    team_id: Mapped[str] = mapped_column(String, ForeignKey("teams.id"), index=True)
    name: Mapped[str] = mapped_column(String, default="project")


class File(Base):
    __tablename__ = "files"
    key: Mapped[str] = mapped_column(String, primary_key=True)  # 22-char file key
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String, default="Untitled")
    version: Mapped[str] = mapped_column(String, default="1")
    last_modified: Mapped[str] = mapped_column(String, default="")
    thumbnail_url: Mapped[str] = mapped_column(String, default="")
    editor_type: Mapped[str] = mapped_column(String, default="figma")
    role: Mapped[str] = mapped_column(String, default="owner")
    # The big nested payloads, served back verbatim as Figma JSON shapes.
    document: Mapped[dict] = mapped_column(JSON, default=dict)
    components: Mapped[dict] = mapped_column(JSON, default=dict)
    component_sets: Mapped[dict] = mapped_column(JSON, default=dict)
    styles: Mapped[dict] = mapped_column(JSON, default=dict)
    images: Mapped[dict] = mapped_column(JSON, default=dict)  # node_id -> rendered PNG url


class Comment(Base):
    __tablename__ = "comments"
    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String, index=True)  # Figma comment id (== order_id)
    file_key: Mapped[str] = mapped_column(String, ForeignKey("files.key"), index=True)
    parent_id: Mapped[str] = mapped_column(String, default="")  # "" for top-level
    user: Mapped[dict] = mapped_column(JSON, default=dict)  # {id, handle, img_url, email}
    message: Mapped[str] = mapped_column(Text, default="")
    client_meta: Mapped[dict] = mapped_column(JSON, default=dict)  # {node_id, node_offset:{x,y}} or {x,y}
    order_id: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String, default="")
    resolved_at: Mapped[str | None] = mapped_column(String, nullable=True)


class Version(Base):
    __tablename__ = "versions"
    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String, index=True)
    file_key: Mapped[str] = mapped_column(String, ForeignKey("files.key"), index=True)
    created_at: Mapped[str] = mapped_column(String, default="")
    label: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    user: Mapped[dict] = mapped_column(JSON, default=dict)
