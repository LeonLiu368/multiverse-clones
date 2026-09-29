"""Data-access + Slack-shaped serialization.

This is the single source of truth used by BOTH the HTTP API and the seed
loader. Reads/writes go through here; serialization helpers emit Slack Web API
shapes so responses match the real thing.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .ids import decode_cursor, encode_cursor, make_ts
from .models import Channel, Membership, Message, Pin, Reaction, User, Workspace

# ----------------------------------------------------------------- resolution


def resolve_channel(s: Session, id_or_name: str) -> Channel | None:
    if not id_or_name:
        return None
    name = id_or_name.lstrip("#")
    c = s.get(Channel, id_or_name)
    if c:
        return c
    return s.scalars(select(Channel).where(Channel.name == name)).first()


def _ts_key(ts: str) -> float:
    try:
        return float(ts)
    except (TypeError, ValueError):
        return 0.0


def make_unique_ts(s: Session, channel_id: str) -> str:
    """A fresh, monotonic, collision-free ``ts`` for a new message."""
    now = time.time()
    seq = 0
    while True:
        ts = make_ts(now, seq)
        exists = s.scalars(
            select(Message.pk).where(Message.channel_id == channel_id, Message.ts == ts)
        ).first()
        if not exists:
            return ts
        seq += 1


# ----------------------------------------------------------------- serialization


def user_dict(u: User) -> dict[str, Any]:
    profile = dict(u.profile or {})
    profile.setdefault("real_name", u.real_name)
    profile.setdefault("display_name", u.name)
    return {
        "id": u.id,
        "name": u.name,
        "real_name": u.real_name,
        "tz": u.tz,
        "is_bot": u.is_bot,
        "deleted": u.deleted,
        "profile": profile,
    }


def channel_dict(s: Session, c: Channel) -> dict[str, Any]:
    num_members = s.scalar(
        select(func.count()).select_from(Membership).where(Membership.channel_id == c.id)
    )
    return {
        "id": c.id,
        "name": c.name,
        "is_channel": not (c.is_im or c.is_mpim),
        "is_group": c.is_private and not (c.is_im or c.is_mpim),
        "is_im": c.is_im,
        "is_mpim": c.is_mpim,
        "is_private": c.is_private,
        "is_archived": c.is_archived,
        "created": c.created,
        "creator": c.creator,
        "num_members": num_members or 0,
        "topic": {"value": c.topic, "creator": c.creator, "last_set": c.created},
        "purpose": {"value": c.purpose, "creator": c.creator, "last_set": c.created},
    }


def _reactions_for(s: Session, channel_id: str, ts: str) -> list[dict[str, Any]]:
    rows = s.scalars(
        select(Reaction).where(Reaction.channel_id == channel_id, Reaction.ts == ts)
    ).all()
    by_name: dict[str, list[str]] = {}
    for r in rows:
        by_name.setdefault(r.name, []).append(r.user_id)
    return [{"name": n, "count": len(u), "users": u} for n, u in by_name.items()]


def _thread_meta(s: Session, channel_id: str, ts: str) -> dict[str, Any]:
    replies = s.scalars(
        select(Message)
        .where(
            Message.channel_id == channel_id,
            Message.thread_ts == ts,
            Message.ts != ts,
            Message.deleted.is_(False),
        )
    ).all()
    if not replies:
        return {}
    replies = sorted(replies, key=lambda m: _ts_key(m.ts))
    users = list(dict.fromkeys([ts and replies[0].user_id] + [r.user_id for r in replies]))
    return {
        "thread_ts": ts,
        "reply_count": len(replies),
        "reply_users_count": len(set(r.user_id for r in replies)),
        "latest_reply": replies[-1].ts,
        "reply_users": users[:5],
    }


def message_dict(s: Session, m: Message, *, with_thread: bool = True) -> dict[str, Any]:
    d: dict[str, Any] = {
        "type": "message",
        "user": m.user_id,
        "text": m.text,
        "ts": m.ts,
    }
    if m.subtype:
        d["subtype"] = m.subtype
    if m.blocks:
        d["blocks"] = m.blocks
    if m.edited_ts:
        d["edited"] = {"user": m.edited_user or m.user_id, "ts": m.edited_ts}
    reactions = _reactions_for(s, m.channel_id, m.ts)
    if reactions:
        d["reactions"] = reactions
    pin = s.scalars(
        select(Pin).where(Pin.channel_id == m.channel_id, Pin.ts == m.ts)
    ).first()
    if pin:
        d["pinned_to"] = [m.channel_id]
    if m.thread_ts and m.thread_ts != m.ts:
        d["thread_ts"] = m.thread_ts  # this message is a reply
    elif with_thread:
        d.update(_thread_meta(s, m.channel_id, m.ts))  # may add thread_ts/reply_count
    return d


# ----------------------------------------------------------------- reads


def list_channels(
    s: Session,
    *,
    types: list[str] | None = None,
    exclude_archived: bool = False,
    cursor: str | None = None,
    limit: int = 100,
) -> tuple[list[dict], str]:
    types = types or ["public_channel", "private_channel"]
    q = select(Channel)
    if exclude_archived:
        q = q.where(Channel.is_archived.is_(False))
    chans = [c for c in s.scalars(q).all() if _channel_type(c) in types]
    chans.sort(key=lambda c: c.name)
    off = decode_cursor(cursor)
    page = chans[off : off + limit]
    next_cur = encode_cursor(off + limit) if off + limit < len(chans) else ""
    return [channel_dict(s, c) for c in page], next_cur


def _channel_type(c: Channel) -> str:
    if c.is_im:
        return "im"
    if c.is_mpim:
        return "mpim"
    return "private_channel" if c.is_private else "public_channel"


def history(
    s: Session,
    channel: str,
    *,
    oldest: float | None = None,
    latest: float | None = None,
    inclusive: bool = False,
    cursor: str | None = None,
    limit: int = 100,
) -> tuple[list[dict], bool, str]:
    c = resolve_channel(s, channel)
    if not c:
        raise KeyError("channel_not_found")
    msgs = s.scalars(
        select(Message).where(
            Message.channel_id == c.id,
            Message.deleted.is_(False),
            # top-level only (replies are fetched via conversations.replies)
            (Message.thread_ts.is_(None)) | (Message.thread_ts == Message.ts),
        )
    ).all()

    def in_range(m: Message) -> bool:
        k = _ts_key(m.ts)
        if oldest is not None and (k < oldest or (k == oldest and not inclusive)):
            return False
        if latest is not None and (k > latest or (k == latest and not inclusive)):
            return False
        return True

    msgs = [m for m in msgs if in_range(m)]
    msgs.sort(key=lambda m: _ts_key(m.ts), reverse=True)  # newest first (Slack)
    off = decode_cursor(cursor)
    page = msgs[off : off + limit]
    has_more = off + limit < len(msgs)
    next_cur = encode_cursor(off + limit) if has_more else ""
    return [message_dict(s, m) for m in page], has_more, next_cur


def replies(s: Session, channel: str, thread_ts: str) -> list[dict]:
    c = resolve_channel(s, channel)
    if not c:
        raise KeyError("channel_not_found")
    msgs = s.scalars(
        select(Message).where(
            Message.channel_id == c.id,
            Message.deleted.is_(False),
            (Message.ts == thread_ts) | (Message.thread_ts == thread_ts),
        )
    ).all()
    msgs.sort(key=lambda m: _ts_key(m.ts))  # chronological (parent first)
    return [message_dict(s, m) for m in msgs]


def channel_info(s: Session, channel: str) -> dict:
    c = resolve_channel(s, channel)
    if not c:
        raise KeyError("channel_not_found")
    return channel_dict(s, c)


def members(s: Session, channel: str) -> list[str]:
    c = resolve_channel(s, channel)
    if not c:
        raise KeyError("channel_not_found")
    return list(
        s.scalars(select(Membership.user_id).where(Membership.channel_id == c.id)).all()
    )


def list_users(s: Session, *, cursor: str | None = None, limit: int = 100) -> tuple[list[dict], str]:
    users = s.scalars(select(User).order_by(User.id)).all()
    off = decode_cursor(cursor)
    page = users[off : off + limit]
    next_cur = encode_cursor(off + limit) if off + limit < len(users) else ""
    return [user_dict(u) for u in page], next_cur


def get_user(s: Session, user_id: str) -> dict | None:
    u = s.get(User, user_id)
    return user_dict(u) if u else None


def search_messages(s: Session, query: str, *, count: int = 20, page: int = 1) -> dict:
    """Substring search over message text, honoring ``in:#chan`` / ``from:@user`` modifiers."""
    terms, in_chan, from_user = [], None, None
    for tok in query.split():
        if tok.startswith("in:"):
            in_chan = tok[3:].lstrip("#")
        elif tok.startswith("from:"):
            from_user = tok[5:].lstrip("@")
        else:
            terms.append(tok.lower())
    text_q = " ".join(terms)
    chan_ids = {c.id: c for c in s.scalars(select(Channel)).all()}
    name_to_id = {c.name: cid for cid, c in chan_ids.items()}
    user_name_to_id = {u.name: u.id for u in s.scalars(select(User)).all()}
    matches: list[Message] = []
    for m in s.scalars(select(Message).where(Message.deleted.is_(False))).all():
        if text_q and text_q not in m.text.lower():
            continue
        if in_chan and m.channel_id != name_to_id.get(in_chan, in_chan):
            continue
        if from_user and m.user_id != user_name_to_id.get(from_user, from_user):
            continue
        matches.append(m)
    matches.sort(key=lambda m: _ts_key(m.ts), reverse=True)
    total = len(matches)
    start = (page - 1) * count
    page_msgs = matches[start : start + count]
    out = []
    for m in page_msgs:
        d = message_dict(s, m, with_thread=False)
        c = chan_ids.get(m.channel_id)
        d["channel"] = {"id": m.channel_id, "name": c.name if c else ""}
        out.append(d)
    pages = max(1, (total + count - 1) // count)
    return {
        "total": total,
        "pagination": {"total_count": total, "page": page, "page_count": pages, "per_page": count},
        "paging": {"count": count, "total": total, "page": page, "pages": pages},
        "matches": out,
    }


# ----------------------------------------------------------------- writes


def post_message(
    s: Session, channel: str, text: str, user: str, thread_ts: str | None = None
) -> dict:
    c = resolve_channel(s, channel)
    if not c:
        raise KeyError("channel_not_found")
    ts = make_unique_ts(s, c.id)
    m = Message(channel_id=c.id, ts=ts, user_id=user, text=text, thread_ts=thread_ts)
    s.add(m)
    s.commit()
    return {"channel": c.id, "ts": ts, "message": message_dict(s, m)}


def update_message(s: Session, channel: str, ts: str, text: str, user: str | None = None) -> dict:
    c = resolve_channel(s, channel)
    if not c:
        raise KeyError("channel_not_found")
    m = s.scalars(
        select(Message).where(Message.channel_id == c.id, Message.ts == ts)
    ).first()
    if not m or m.deleted:
        raise KeyError("message_not_found")
    m.text = text
    m.edited_ts = make_unique_ts(s, c.id)
    m.edited_user = user or m.user_id
    s.commit()
    return {"channel": c.id, "ts": ts, "text": text, "message": message_dict(s, m)}


def delete_message(s: Session, channel: str, ts: str) -> dict:
    c = resolve_channel(s, channel)
    if not c:
        raise KeyError("channel_not_found")
    m = s.scalars(
        select(Message).where(Message.channel_id == c.id, Message.ts == ts)
    ).first()
    if not m or m.deleted:
        raise KeyError("message_not_found")
    m.deleted = True
    s.commit()
    return {"channel": c.id, "ts": ts}


def add_reaction(s: Session, channel: str, ts: str, name: str, user: str) -> dict:
    c = resolve_channel(s, channel)
    if not c:
        raise KeyError("channel_not_found")
    exists = s.scalars(
        select(Reaction).where(
            Reaction.channel_id == c.id,
            Reaction.ts == ts,
            Reaction.name == name,
            Reaction.user_id == user,
        )
    ).first()
    if exists:
        raise ValueError("already_reacted")
    s.add(Reaction(channel_id=c.id, ts=ts, name=name, user_id=user))
    s.commit()
    return {"ok": True}


def add_pin(s: Session, channel: str, ts: str, user: str) -> dict:
    c = resolve_channel(s, channel)
    if not c:
        raise KeyError("channel_not_found")
    exists = s.scalars(
        select(Pin).where(Pin.channel_id == c.id, Pin.ts == ts)
    ).first()
    if not exists:
        s.add(Pin(channel_id=c.id, ts=ts, user_id=user, created=int(time.time())))
        s.commit()
    return {"ok": True}


# ----------------------------------------------------------------- seed upserts


def upsert_workspace(s: Session, wid: str, name: str, domain: str) -> None:
    w = s.get(Workspace, wid)
    if w:
        w.name, w.domain = name, domain
    else:
        s.add(Workspace(id=wid, name=name, domain=domain))


def upsert_user(s: Session, u: dict) -> None:
    obj = s.get(User, u["id"])
    fields = dict(
        name=u.get("name", u["id"]),
        real_name=u.get("real_name", ""),
        is_bot=bool(u.get("is_bot", False)),
        deleted=bool(u.get("deleted", False)),
        tz=u.get("tz", "America/Los_Angeles"),
        profile=u.get("profile", {}),
    )
    if obj:
        for k, v in fields.items():
            setattr(obj, k, v)
    else:
        s.add(User(id=u["id"], **fields))


def upsert_channel(s: Session, c: dict) -> None:
    obj = s.get(Channel, c["id"])
    fields = dict(
        name=c.get("name", c["id"]),
        is_private=bool(c.get("is_private", c.get("type") == "private_channel")),
        is_im=bool(c.get("is_im", c.get("type") == "im")),
        is_mpim=bool(c.get("is_mpim", c.get("type") == "mpim")),
        is_archived=bool(c.get("is_archived", False)),
        created=int(c.get("created", 0)),
        creator=c.get("creator", ""),
        topic=c.get("topic", ""),
        purpose=c.get("purpose", ""),
    )
    if obj:
        for k, v in fields.items():
            setattr(obj, k, v)
    else:
        s.add(Channel(id=c["id"], **fields))
    for uid in c.get("members", []):
        add_membership(s, c["id"], uid)


def add_membership(s: Session, channel_id: str, user_id: str) -> None:
    if not s.get(Membership, {"channel_id": channel_id, "user_id": user_id}):
        s.add(Membership(channel_id=channel_id, user_id=user_id))


def upsert_message(s: Session, m: dict) -> None:
    existing = s.scalars(
        select(Message).where(
            Message.channel_id == m["channel"], Message.ts == m["ts"]
        )
    ).first()
    fields = dict(
        user_id=m.get("user", ""),
        text=m.get("text", ""),
        thread_ts=m.get("thread_ts"),
        subtype=m.get("subtype"),
        edited_ts=(m.get("edited") or {}).get("ts"),
        edited_user=(m.get("edited") or {}).get("user"),
        blocks=m.get("blocks"),
    )
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
    else:
        s.add(Message(channel_id=m["channel"], ts=m["ts"], **fields))
    for rx in m.get("reactions", []):
        for uid in rx.get("users", []):
            upsert_reaction(s, m["channel"], m["ts"], rx["name"], uid)
    if m.get("pinned"):
        if not s.scalars(
            select(Pin).where(Pin.channel_id == m["channel"], Pin.ts == m["ts"])
        ).first():
            s.add(Pin(channel_id=m["channel"], ts=m["ts"], user_id=m.get("user", "")))


def upsert_reaction(s: Session, channel_id: str, ts: str, name: str, user_id: str) -> None:
    exists = s.scalars(
        select(Reaction).where(
            Reaction.channel_id == channel_id,
            Reaction.ts == ts,
            Reaction.name == name,
            Reaction.user_id == user_id,
        )
    ).first()
    if not exists:
        s.add(Reaction(channel_id=channel_id, ts=ts, name=name, user_id=user_id))
