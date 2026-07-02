"""SQLAlchemy ORM models for the Discord clone (SQLite-backed).

Discord's object graph, modelled faithfully but minimally for the agent-used
surface:

* **User** — a member of the platform (``id`` snowflake, ``username``,
  ``global_name``, ``bot``).
* **Guild** — a server (``id``, ``name``, ``owner_id``).
* **Channel** — a text channel in a guild (``id``, ``type``, ``guild_id``,
  ``name``, ``topic``, ``position``).
* **Member** — the join of a user to a guild (``nick``, ``roles``, ``joined_at``).
* **Message** — a message in a channel (``content``, ``author``, ``timestamp``,
  ``reactions``, ``mentions``, ``pinned``, ``type``).
* **Reaction** — one (message, emoji, user) tuple; the API rolls these up into the
  message's ``reactions`` array and serves reactor lists.

Free-shaped payloads (mentions, roles, embeds) are stored as JSON columns — the JSON
IS the API payload, served back the way the real API does. Snowflake ids double as
creation-time + sort key, so ``ORDER BY id`` is chronological.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # snowflake
    username: Mapped[str] = mapped_column(String, default="")
    global_name: Mapped[str | None] = mapped_column(String, nullable=True)
    discriminator: Mapped[str] = mapped_column(String, default="0")
    bot: Mapped[bool] = mapped_column(Boolean, default=False)
    avatar: Mapped[str | None] = mapped_column(String, nullable=True)


class Guild(Base):
    __tablename__ = "guilds"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # snowflake
    name: Mapped[str] = mapped_column(String, default="")
    owner_id: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    icon: Mapped[str | None] = mapped_column(String, nullable=True)


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # snowflake
    type: Mapped[int] = mapped_column(Integer, default=0)  # 0 = GUILD_TEXT
    guild_id: Mapped[str] = mapped_column(String, index=True, default="")
    name: Mapped[str] = mapped_column(String, default="")
    topic: Mapped[str | None] = mapped_column(String, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    parent_id: Mapped[str | None] = mapped_column(String, nullable=True)


class Member(Base):
    __tablename__ = "members"
    guild_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    nick: Mapped[str | None] = mapped_column(String, nullable=True)
    roles: Mapped[list] = mapped_column(JSON, default=list)  # role-id snowflakes
    joined_at: Mapped[str] = mapped_column(String, default="")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # snowflake
    channel_id: Mapped[str] = mapped_column(String, index=True, default="")
    guild_id: Mapped[str] = mapped_column(String, index=True, default="")
    author_id: Mapped[str] = mapped_column(String, index=True, default="")
    content: Mapped[str] = mapped_column(String, default="")
    timestamp: Mapped[str] = mapped_column(String, default="")  # ISO-8601
    edited_timestamp: Mapped[str | None] = mapped_column(String, nullable=True)
    type: Mapped[int] = mapped_column(Integer, default=0)  # 0 = DEFAULT
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    mentions: Mapped[list] = mapped_column(JSON, default=list)  # user-id snowflakes
    mention_everyone: Mapped[bool] = mapped_column(Boolean, default=False)


class Reaction(Base):
    __tablename__ = "reactions"
    message_id: Mapped[str] = mapped_column(String, primary_key=True)
    emoji: Mapped[str] = mapped_column(String, primary_key=True)  # unicode or name:id
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
