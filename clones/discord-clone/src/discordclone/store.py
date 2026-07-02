"""Data-access + Discord-shaped serialization + the message-search query grammar.

The single source of truth used by BOTH the HTTP API and the seed loader. Every
read/write goes through here; the serialization helpers emit real Discord envelopes
so responses match the live API:

  * ids are stringified **snowflakes**; timestamps are ISO-8601 (``…+00:00``);
  * message objects carry ``id, channel_id, author:{…}, content, timestamp,
    edited_timestamp, mentions, reactions, type, pinned``;
  * list endpoints are **not** cursor-enveloped — message history uses
    ``before/after/around&limit`` snowflake pagination, newest-first.

The **search engine** (`search_messages`) is the T2 assessment-grade surface: it
parses Discord's real ``messages/search`` param grammar
(``content=&channel_id=&author_id=&mentions=&has=&pinned=&before=&after=``) and
applies it over the seeded rows, newest-first, returning the ``{total_results,
messages:[[msg]]}`` shape.
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ids import gen_snowflake, timestamp_of
from .models import Channel, Guild, Member, Message, Reaction, User


# ----------------------------------------------------------------- time helpers
def iso_from_ms(ms: int) -> str:
    """Render a ms unix timestamp as Discord does: ISO-8601 UTC with microseconds."""
    dt = datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc)
    return dt.isoformat()


def now_iso() -> str:
    return datetime.datetime.now(tz=datetime.timezone.utc).isoformat()


# ----------------------------------------------------------------- serializers
def user_dict(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "global_name": u.global_name,
        "discriminator": u.discriminator or "0",
        "avatar": u.avatar,
        "bot": bool(u.bot),
    }


def _user_ref(uid: str, users: dict[str, User]) -> dict:
    u = users.get(uid)
    if u is not None:
        return user_dict(u)
    # Unknown author (deleted user etc.) — still return a Discord-shaped stub.
    return {"id": uid, "username": "unknown", "global_name": None,
            "discriminator": "0", "avatar": None, "bot": False}


def guild_dict(g: Guild) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "owner_id": g.owner_id,
        "description": g.description,
        "icon": g.icon,
    }


def channel_dict(c: Channel) -> dict:
    out = {
        "id": c.id,
        "type": c.type,
        "guild_id": c.guild_id or None,
        "name": c.name,
        "topic": c.topic,
        "position": c.position,
    }
    if c.parent_id:
        out["parent_id"] = c.parent_id
    return out


def member_dict(m: Member, users: dict[str, User]) -> dict:
    return {
        "user": _user_ref(m.user_id, users),
        "nick": m.nick,
        "roles": list(m.roles or []),
        "joined_at": m.joined_at,
    }


def _reactions_for(s: Session, message_id: str) -> list[dict]:
    """Roll the (message, emoji, user) rows up into Discord's message.reactions array."""
    rows = s.scalars(
        select(Reaction).where(Reaction.message_id == message_id).order_by(Reaction.emoji)
    ).all()
    counts: dict[str, int] = {}
    order: list[str] = []
    for r in rows:
        if r.emoji not in counts:
            counts[r.emoji] = 0
            order.append(r.emoji)
        counts[r.emoji] += 1
    out = []
    for emoji in order:
        out.append({"emoji": _emoji_obj(emoji), "count": counts[emoji], "me": False})
    return out


def _emoji_obj(emoji: str) -> dict:
    """Discord emoji object. Unicode → {id:null,name:'👍'}; custom name:id → {id,name}."""
    if ":" in emoji:
        name, _, eid = emoji.partition(":")
        return {"id": eid or None, "name": name}
    return {"id": None, "name": emoji}


def message_dict(s: Session, m: Message, users: dict[str, User] | None = None) -> dict:
    users = users if users is not None else _user_map(s)
    return {
        "id": m.id,
        "type": m.type,
        "channel_id": m.channel_id,
        "author": _user_ref(m.author_id, users),
        "content": m.content,
        "timestamp": m.timestamp,
        "edited_timestamp": m.edited_timestamp,
        "mentions": [_user_ref(uid, users) for uid in (m.mentions or [])],
        "mention_everyone": bool(m.mention_everyone),
        "mention_roles": [],
        "attachments": [],
        "embeds": [],
        "reactions": _reactions_for(s, m.id),
        "pinned": bool(m.pinned),
        "tts": False,
    }


def _user_map(s: Session) -> dict[str, User]:
    return {u.id: u for u in s.scalars(select(User)).all()}


# ----------------------------------------------------------------- upserts (seed)
def upsert_user(s: Session, u: dict) -> User:
    obj = s.get(User, u["id"])
    if obj is None:
        obj = User(id=u["id"])
        s.add(obj)
    obj.username = u.get("username", "")
    obj.global_name = u.get("global_name")
    obj.discriminator = str(u.get("discriminator", "0"))
    obj.bot = bool(u.get("bot", False))
    obj.avatar = u.get("avatar")
    return obj


def upsert_guild(s: Session, g: dict) -> Guild:
    obj = s.get(Guild, g["id"])
    if obj is None:
        obj = Guild(id=g["id"])
        s.add(obj)
    obj.name = g.get("name", "")
    obj.owner_id = g.get("owner_id", "")
    obj.description = g.get("description")
    obj.icon = g.get("icon")
    return obj


def upsert_channel(s: Session, c: dict) -> Channel:
    obj = s.get(Channel, c["id"])
    if obj is None:
        obj = Channel(id=c["id"])
        s.add(obj)
    obj.type = int(c.get("type", 0))
    obj.guild_id = c.get("guild_id", "")
    obj.name = c.get("name", "")
    obj.topic = c.get("topic")
    obj.position = int(c.get("position", 0))
    obj.parent_id = c.get("parent_id")
    return obj


def upsert_member(s: Session, guild_id: str, m: dict) -> Member:
    uid = m["user"]["id"] if isinstance(m.get("user"), dict) else m["user_id"]
    obj = s.get(Member, {"guild_id": guild_id, "user_id": uid})
    if obj is None:
        obj = Member(guild_id=guild_id, user_id=uid)
        s.add(obj)
    obj.nick = m.get("nick")
    obj.roles = list(m.get("roles", []))
    obj.joined_at = m.get("joined_at", "")
    return obj


def insert_message(s: Session, m: dict) -> Message:
    obj = s.get(Message, m["id"])
    if obj is None:
        obj = Message(id=m["id"])
        s.add(obj)
    obj.channel_id = m.get("channel_id", "")
    obj.guild_id = m.get("guild_id", "")
    obj.author_id = m["author"]["id"] if isinstance(m.get("author"), dict) else m.get("author_id", "")
    obj.content = m.get("content", "")
    obj.timestamp = m.get("timestamp", "")
    obj.edited_timestamp = m.get("edited_timestamp")
    obj.type = int(m.get("type", 0))
    obj.pinned = bool(m.get("pinned", False))
    obj.mentions = list(m.get("mentions", []))
    obj.mention_everyone = bool(m.get("mention_everyone", False))
    return obj


def insert_reaction(s: Session, message_id: str, emoji: str, user_id: str) -> None:
    obj = s.get(Reaction, {"message_id": message_id, "emoji": emoji, "user_id": user_id})
    if obj is None:
        s.add(Reaction(message_id=message_id, emoji=emoji, user_id=user_id))


# ----------------------------------------------------------------- reads
def get_user(s: Session, user_id: str) -> User | None:
    return s.get(User, user_id)


def list_users(s: Session) -> list[User]:
    return list(s.scalars(select(User).order_by(User.id)).all())


def get_guild(s: Session, guild_id: str) -> Guild | None:
    return s.get(Guild, guild_id)


def list_guilds(s: Session) -> list[Guild]:
    return list(s.scalars(select(Guild).order_by(Guild.id)).all())


def get_channel(s: Session, channel_id: str) -> Channel | None:
    return s.get(Channel, channel_id)


def list_guild_channels(s: Session, guild_id: str) -> list[Channel]:
    return list(s.scalars(
        select(Channel).where(Channel.guild_id == guild_id).order_by(Channel.position, Channel.id)
    ).all())


def list_members(s: Session, guild_id: str, limit: int, after: str | None) -> list[Member]:
    rows = list(s.scalars(select(Member).where(Member.guild_id == guild_id)).all())
    # Discord sorts guild members ascending by user id; paginate with ?after=&limit=.
    # Snowflakes are numeric strings of varying length, so compare as ints (a string
    # `>` would mis-order an 18-digit id against a 19-digit one).
    rows.sort(key=lambda m: int(m.user_id))
    if after:
        rows = [m for m in rows if int(m.user_id) > int(after)]
    return rows[:max(1, min(limit, 1000))]


def get_member(s: Session, guild_id: str, user_id: str) -> Member | None:
    return s.get(Member, {"guild_id": guild_id, "user_id": user_id})


def get_message(s: Session, channel_id: str, message_id: str) -> Message | None:
    m = s.get(Message, message_id)
    if m is None or m.channel_id != channel_id:
        return None
    return m


def channel_messages(s: Session, channel_id: str, *, limit: int = 50,
                     before: str | None = None, after: str | None = None,
                     around: str | None = None) -> list[Message]:
    """Discord ``GET /channels/{id}/messages`` — snowflake pagination, newest-first.

    ``before``/``after`` are message-id snowflakes; results are always returned
    **newest-first** (descending id), matching the real API. ``around`` returns a
    window centred on the given id. ``limit`` is clamped to [1, 100].
    """
    limit = max(1, min(int(limit), 100))
    rows = list(s.scalars(select(Message).where(Message.channel_id == channel_id)).all())
    rows.sort(key=lambda m: int(m.id))  # ascending by snowflake == chronological

    if around:
        target = int(around)
        idx = min(range(len(rows)), key=lambda i: abs(int(rows[i].id) - target)) if rows else 0
        half = limit // 2
        lo = max(0, idx - half)
        hi = min(len(rows), lo + limit)
        window = rows[lo:hi]
        window.sort(key=lambda m: int(m.id), reverse=True)
        return window

    if after:
        rows = [m for m in rows if int(m.id) > int(after)]
        page = rows[:limit]  # oldest-after, then reverse to newest-first
        page.sort(key=lambda m: int(m.id), reverse=True)
        return page

    # default + before: newest-first
    rows.sort(key=lambda m: int(m.id), reverse=True)
    if before:
        rows = [m for m in rows if int(m.id) < int(before)]
    return rows[:limit]


def channel_pins(s: Session, channel_id: str) -> list[Message]:
    rows = list(s.scalars(
        select(Message).where(Message.channel_id == channel_id, Message.pinned == True)  # noqa: E712
    ).all())
    rows.sort(key=lambda m: int(m.id), reverse=True)
    return rows


def reaction_users(s: Session, message_id: str, emoji: str, *, limit: int = 25,
                   after: str | None = None) -> list[User]:
    rows = s.scalars(
        select(Reaction).where(Reaction.message_id == message_id, Reaction.emoji == emoji)
    ).all()
    uids = sorted({r.user_id for r in rows}, key=lambda x: int(x))
    if after:
        uids = [u for u in uids if int(u) > int(after)]
    uids = uids[:max(1, min(limit, 100))]
    return [s.get(User, uid) for uid in uids if s.get(User, uid) is not None]


# ----------------------------------------------------------------- writes
def create_message(s: Session, channel_id: str, guild_id: str, author_id: str,
                   content: str, *, mentions: list[str] | None = None,
                   mention_everyone: bool = False) -> Message:
    """Post a message; hydrate all derived fields so a read-back is Discord-shaped."""
    mid = gen_snowflake()
    ts = iso_from_ms(timestamp_of(mid))
    msg = Message(
        id=mid, channel_id=channel_id, guild_id=guild_id, author_id=author_id,
        content=content or "", timestamp=ts, edited_timestamp=None, type=0,
        pinned=False, mentions=list(mentions or []), mention_everyone=mention_everyone,
    )
    s.add(msg)
    s.commit()
    return msg


def add_reaction(s: Session, message_id: str, emoji: str, user_id: str) -> None:
    insert_reaction(s, message_id, emoji, user_id)
    s.commit()


def pin_message(s: Session, message: Message) -> Message:
    message.pinned = True
    s.commit()
    return message


# ----------------------------------------------------------------- SEARCH (T2)
class SearchError(ValueError):
    """Raised for a malformed search param — surfaced as Discord's 400 validation."""


def search_messages(s: Session, guild_id: str, *, content: str | None = None,
                    channel_id: str | None = None, author_id: str | None = None,
                    mentions: str | None = None, has: str | None = None,
                    pinned: str | None = None, before: str | None = None,
                    after: str | None = None, limit: int = 25,
                    offset: int = 0) -> dict:
    """Discord ``GET /guilds/{id}/messages/search`` — the real param grammar.

    Filters (ANDed): ``content`` (case-insensitive substring, each whitespace token
    must appear), ``channel_id``, ``author_id``, ``mentions`` (a user id that must
    appear in the message's mentions), ``has`` (``link``/``embed`` — we support
    ``link``), ``pinned`` (``true``/``false``), and ``before``/``after`` snowflake
    bounds. Returns Discord's shape: ``{"total_results": N, "messages": [[msg], …]}``
    — each match wrapped in a one-element array — newest-first.
    """
    rows = list(s.scalars(select(Message).where(Message.guild_id == guild_id)).all())

    if channel_id:
        rows = [m for m in rows if m.channel_id == channel_id]
    if author_id:
        rows = [m for m in rows if m.author_id == author_id]
    if content:
        tokens = [t.lower() for t in content.split() if t]
        rows = [m for m in rows if all(t in (m.content or "").lower() for t in tokens)]
    if mentions:
        rows = [m for m in rows if mentions in (m.mentions or [])]
    if has is not None:
        if has == "link":
            rows = [m for m in rows if ("http://" in m.content or "https://" in m.content)]
        elif has in ("embed", "image", "video", "file", "sound"):
            rows = []  # corpus carries no attachments/embeds
        else:
            raise SearchError(f"Value '{has}' is not a valid value for 'has'.")
    if pinned is not None:
        want = str(pinned).lower()
        if want not in ("true", "false"):
            raise SearchError("Value must be true or false for 'pinned'.")
        flag = want == "true"
        rows = [m for m in rows if bool(m.pinned) == flag]
    if before:
        rows = [m for m in rows if int(m.id) < int(before)]
    if after:
        rows = [m for m in rows if int(m.id) > int(after)]

    rows.sort(key=lambda m: int(m.id), reverse=True)  # newest-first
    total = len(rows)
    limit = max(1, min(int(limit), 25))
    offset = max(0, int(offset))
    page = rows[offset:offset + limit]
    users = _user_map(s)

    def _hit(m: Message) -> dict:
        # Real Discord marks the matched message in each result group with "hit": true.
        d = message_dict(s, m, users)
        d["hit"] = True
        return d

    return {
        "total_results": total,
        "messages": [[_hit(m)] for m in page],
    }
