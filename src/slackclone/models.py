"""SQLAlchemy ORM models for the Slack clone (SQLite-backed).

Slack-faithful shape: users (``U…``), channels (``C…``), messages keyed by a
per-channel ``ts``, plus reactions and pins as separate rows so counts/users
aggregate naturally. Threads are modelled with ``thread_ts`` pointing at the
parent message's ``ts`` (Slack's convention), not a separate table.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspace"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, default="workspace")
    domain: Mapped[str] = mapped_column(String, default="workspace")


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # U…
    name: Mapped[str] = mapped_column(String)  # username / handle
    real_name: Mapped[str] = mapped_column(String, default="")
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    tz: Mapped[str] = mapped_column(String, default="America/Los_Angeles")
    profile: Mapped[dict] = mapped_column(JSON, default=dict)  # email, title, image_*, display_name


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # C…
    name: Mapped[str] = mapped_column(String)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    is_im: Mapped[bool] = mapped_column(Boolean, default=False)
    is_mpim: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created: Mapped[int] = mapped_column(Integer, default=0)
    creator: Mapped[str] = mapped_column(String, default="")
    topic: Mapped[str] = mapped_column(Text, default="")
    purpose: Mapped[str] = mapped_column(Text, default="")


class Membership(Base):
    __tablename__ = "memberships"
    channel_id: Mapped[str] = mapped_column(String, ForeignKey("channels.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), primary_key=True)


class Message(Base):
    __tablename__ = "messages"
    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[str] = mapped_column(String, ForeignKey("channels.id"), index=True)
    ts: Mapped[str] = mapped_column(String, index=True)
    user_id: Mapped[str] = mapped_column(String, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    thread_ts: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    subtype: Mapped[str | None] = mapped_column(String, nullable=True)
    edited_ts: Mapped[str | None] = mapped_column(String, nullable=True)
    edited_user: Mapped[str | None] = mapped_column(String, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    blocks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    __table_args__ = (UniqueConstraint("channel_id", "ts", name="uq_channel_ts"),)


class Reaction(Base):
    __tablename__ = "reactions"
    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[str] = mapped_column(String, index=True)
    ts: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)  # emoji short name, e.g. "thumbsup"
    user_id: Mapped[str] = mapped_column(String)
    __table_args__ = (
        UniqueConstraint("channel_id", "ts", "name", "user_id", name="uq_reaction"),
    )


class Pin(Base):
    __tablename__ = "pins"
    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[str] = mapped_column(String, index=True)
    ts: Mapped[str] = mapped_column(String)
    user_id: Mapped[str] = mapped_column(String, default="")
    created: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("channel_id", "ts", name="uq_pin"),)
