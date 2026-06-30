"""SQLAlchemy ORM models for the Notion clone (SQLite-backed).

Notion's object graph, modelled faithfully but minimally for the agent-used
surface:

* **User** — a person or bot in the workspace (``object: "user"``).
* **Database** — a schema (a map of property definitions) + parent.
* **Page** — a page; either a child of a database (then its ``properties`` map
  matches the database schema) or a standalone page (then it has a single
  ``title`` property). Pages own a tree of blocks.
* **Block** — a content block (paragraph, heading, to-do, …) belonging to a page
  or nested under another block. ``has_children`` is derived.
* **Comment** — a discussion comment attached to a page (or a block).

The nested, free-shaped payloads (a database's property *schema*, a page's
*property values*, a block's type-specific body, rich-text arrays) are stored as
JSON columns rather than shredded into tables — the JSON IS the API payload, and
we serve it back the way the real Notion API does. Ordering and archival flags are
real columns because the query/filter/sort engine and ``archived`` toggles read
them.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # UUID
    type: Mapped[str] = mapped_column(String, default="person")  # person | bot
    name: Mapped[str] = mapped_column(String, default="")
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)


class Database(Base):
    __tablename__ = "databases"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # UUID
    parent: Mapped[dict] = mapped_column(JSON, default=dict)  # {type, page_id|workspace}
    title: Mapped[list] = mapped_column(JSON, default=list)  # rich-text array
    description: Mapped[list] = mapped_column(JSON, default=list)
    icon: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cover: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)  # the schema
    created_time: Mapped[str] = mapped_column(String, default="")
    last_edited_time: Mapped[str] = mapped_column(String, default="")
    created_by: Mapped[str] = mapped_column(String, default="")  # user id
    last_edited_by: Mapped[str] = mapped_column(String, default="")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    url: Mapped[str] = mapped_column(String, default="")


class Page(Base):
    __tablename__ = "pages"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # UUID
    parent: Mapped[dict] = mapped_column(JSON, default=dict)  # {type, database_id|page_id|workspace}
    database_id: Mapped[str | None] = mapped_column(String, ForeignKey("databases.id"), index=True, nullable=True)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)  # property values
    icon: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cover: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_time: Mapped[str] = mapped_column(String, default="")
    last_edited_time: Mapped[str] = mapped_column(String, default="")
    created_by: Mapped[str] = mapped_column(String, default="")
    last_edited_by: Mapped[str] = mapped_column(String, default="")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    in_trash: Mapped[bool] = mapped_column(Boolean, default=False)
    url: Mapped[str] = mapped_column(String, default="")


class Block(Base):
    __tablename__ = "blocks"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # UUID
    parent: Mapped[dict] = mapped_column(JSON, default=dict)  # {type, page_id|block_id}
    parent_id: Mapped[str] = mapped_column(String, index=True)  # page or block id (flat lookup)
    type: Mapped[str] = mapped_column(String, default="paragraph")
    body: Mapped[dict] = mapped_column(JSON, default=dict)  # the type-keyed payload, e.g. {"paragraph": {...}}
    position: Mapped[int] = mapped_column(Integer, default=0)  # order among siblings
    has_children: Mapped[bool] = mapped_column(Boolean, default=False)
    created_time: Mapped[str] = mapped_column(String, default="")
    last_edited_time: Mapped[str] = mapped_column(String, default="")
    created_by: Mapped[str] = mapped_column(String, default="")
    last_edited_by: Mapped[str] = mapped_column(String, default="")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # UUID
    parent: Mapped[dict] = mapped_column(JSON, default=dict)  # {type:"page_id", page_id}
    discussion_id: Mapped[str] = mapped_column(String, index=True, default="")
    page_id: Mapped[str] = mapped_column(String, index=True, default="")  # flat lookup
    rich_text: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String, default="")  # user id
    created_time: Mapped[str] = mapped_column(String, default="")
    last_edited_time: Mapped[str] = mapped_column(String, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
