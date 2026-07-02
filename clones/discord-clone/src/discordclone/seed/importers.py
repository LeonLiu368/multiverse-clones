"""Source-pluggable real-data importers → the canonical seed dict.

Every no-admin real source converges on the SAME canonical seed shape (see
``schema.py``: ``{bot_user_id, users, guilds, channels, members, messages}``) and
reuses the one load path (``load.load_seed``). None of these sources requires server
**admin** (no "Manage Server", no adding a bot):

  * ``from_data_package(dir)``  — Discord's OFFICIAL Data Package (Settings → Privacy
    → Request all of my Data). Your own account export; single real author.
  * ``from_dataset(path, mapping)`` — a GENERIC public dataset (HuggingFace/Kaggle),
    CSV or JSONL, mapped by column. Multi-user real conversation; snowflakes are
    synthesized deterministically from source keys.
  * ``from_dce(path)`` — DiscordChatExporter (Tyrrrz) JSON, produced with a **user**
    token (member-only) or a bot. Near-1:1 with the Discord objects.

Plus ``anonymize(seed)`` — a one-way, structure-preserving remap of real user
ids/handles to synthetic ones (default OFF; strongly recommended for public/
user-token data). The importers keep timestamps and ordering faithful; ids that a
source lacks are minted with ``ids.stable_snowflake`` so re-imports are byte-identical.
"""

from __future__ import annotations

import csv
import datetime
import json
import os
from typing import Any, Iterable

from ..ids import stable_snowflake
from ..store import iso_from_ms

# The bot/exporting identity used when a source doesn't carry one (matches the
# gateway's default DISCORD_BOT_USER_ID so /users/@me stays stable).
DEFAULT_BOT_USER_ID = "900000000000000001"


# --------------------------------------------------------------- time helpers
def _to_iso(value: str) -> str:
    """Normalize a source timestamp to ISO-8601 UTC (…+00:00), best-effort.

    Accepts ISO-8601 (with/without ``Z`` or offset), a unix epoch (s or ms), and a
    few common Discord export formats. Returns the input unchanged only as a last
    resort so a malformed row never crashes the import.
    """
    v = (value or "").strip()
    if not v:
        return ""
    # epoch seconds / milliseconds
    if v.replace(".", "", 1).isdigit():
        num = float(v)
        if num > 1e12:  # ms
            return iso_from_ms(int(num))
        if num > 1e9:  # s
            return iso_from_ms(int(num * 1000))
    s = v.replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %I:%M %p", "%Y-%m-%dT%H:%M:%S"):
        try:
            if fmt is None:
                dt = datetime.datetime.fromisoformat(s)
            else:
                dt = datetime.datetime.strptime(v, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt.astimezone(datetime.timezone.utc).isoformat()
        except (ValueError, TypeError):
            continue
    return v


def _mid_from(source_id: str, ts_iso: str, seq: int) -> str:
    """A message snowflake: use the source id if it's already a real snowflake,
    else synthesize a deterministic one keyed by (timestamp, sequence)."""
    sid = (source_id or "").strip()
    if sid.isdigit() and 8 <= len(sid) <= 20:
        return sid
    return stable_snowflake(f"{ts_iso}\x00{seq}", kind="message")


# --------------------------------------------------------------- 1. Data Package
def from_data_package(directory: str) -> dict[str, Any]:
    """Discord OFFICIAL Data Package → canonical seed (no admin — your own account).

    Layout:
      account/user.json                     -> the exporting user (author of all msgs)
      messages/<channel_id>/channel.json    -> {id, type, guild:{id,name}?, name}
      messages/<channel_id>/messages.csv    -> ID,Timestamp,Contents,Attachments
    """
    account = _read_json(os.path.join(directory, "account", "user.json")) or {}
    uid = str(account.get("id") or DEFAULT_BOT_USER_ID)
    uname = account.get("username") or "me"
    gname = account.get("global_name") or account.get("display_name")
    user = {"id": uid, "username": uname, "global_name": gname, "bot": False}

    guilds: dict[str, dict] = {}
    channels: list[dict] = []
    messages: list[dict] = []
    members: dict[tuple[str, str], dict] = {}

    msg_root = os.path.join(directory, "messages")
    for entry in sorted(os.listdir(msg_root)) if os.path.isdir(msg_root) else []:
        cdir = os.path.join(msg_root, entry)
        if not os.path.isdir(cdir):
            continue
        meta = _read_json(os.path.join(cdir, "channel.json")) or {}
        cid = str(meta.get("id") or entry)
        guild = meta.get("guild") or {}
        gid = str(guild.get("id")) if guild.get("id") else ""
        if gid and gid not in guilds:
            guilds[gid] = {"id": gid, "name": guild.get("name") or f"guild-{gid}",
                           "owner_id": uid}
        ctype = int(meta.get("type", 0)) if str(meta.get("type", "")).isdigit() else 0
        channels.append({"id": cid, "type": ctype, "guild_id": gid,
                         "name": meta.get("name") or f"channel-{cid}",
                         "position": len(channels)})
        if gid:
            members.setdefault((gid, uid),
                               {"guild_id": gid, "user_id": uid, "nick": None,
                                "roles": [], "joined_at": ""})

        csv_path = os.path.join(cdir, "messages.csv")
        if os.path.isfile(csv_path):
            with open(csv_path, newline="", encoding="utf-8") as fh:
                for seq, row in enumerate(csv.DictReader(fh)):
                    ts = _to_iso(row.get("Timestamp", ""))
                    mid = _mid_from(row.get("ID", ""), ts, seq)
                    messages.append({
                        "id": mid, "channel_id": cid, "guild_id": gid, "author_id": uid,
                        "content": row.get("Contents", "") or "", "timestamp": ts,
                        "pinned": False, "mentions": [], "reactions": [],
                    })

    return _assemble(uid, [user], list(guilds.values()), channels,
                     list(members.values()), messages)


# --------------------------------------------------------------- 2. Generic dataset
def from_dataset(path: str, mapping: dict[str, str], *,
                 default_guild: str = "Imported Dataset",
                 default_channel: str = "general") -> dict[str, Any]:
    """A generic public dataset (CSV or JSONL) → canonical seed (multi-user, no admin).

    ``mapping`` maps canonical fields to source columns. Recognized keys:
      author (required)  content (required)  ts  channel  guild  id
    Snowflakes for guild/channels/users are synthesized deterministically from the
    source key strings, so cross-references resolve and re-imports are identical.
    """
    if "author" not in mapping or "content" not in mapping:
        raise ValueError("dataset mapping must include at least 'author' and 'content'")

    rows = list(_read_rows(path))
    guilds: dict[str, dict] = {}
    channels: dict[str, dict] = {}
    users: dict[str, dict] = {}
    members: dict[tuple[str, str], dict] = {}
    messages: list[dict] = []

    def col(row: dict, key: str, default: str = "") -> str:
        src = mapping.get(key)
        if not src:
            return default
        val = row.get(src, default)
        return "" if val is None else str(val)

    for seq, row in enumerate(rows):
        gname = col(row, "guild", default_guild) or default_guild
        cname = col(row, "channel", default_channel) or default_channel
        author = col(row, "author")
        if not author:
            continue
        content = col(row, "content")
        ts = _to_iso(col(row, "ts")) or iso_from_ms(1577836800000 + seq * 1000)

        gid = stable_snowflake(gname, kind="guild")
        cid = stable_snowflake(f"{gname}\x00{cname}", kind="channel")
        uid = stable_snowflake(author, kind="user")

        guilds.setdefault(gid, {"id": gid, "name": gname, "owner_id": uid})
        channels.setdefault(cid, {"id": cid, "type": 0, "guild_id": gid, "name": cname,
                                  "position": len(channels)})
        users.setdefault(uid, {"id": uid, "username": _slug(author), "global_name": author,
                               "bot": False})
        members.setdefault((gid, uid), {"guild_id": gid, "user_id": uid, "nick": None,
                                        "roles": [], "joined_at": ""})

        mid = _mid_from(col(row, "id"), ts, seq)
        messages.append({"id": mid, "channel_id": cid, "guild_id": gid, "author_id": uid,
                         "content": content, "timestamp": ts, "pinned": False,
                         "mentions": [], "reactions": []})

    bot_id = next(iter(users), DEFAULT_BOT_USER_ID)
    return _assemble(bot_id, list(users.values()), list(guilds.values()),
                     list(channels.values()), list(members.values()), messages)


# --------------------------------------------------------------- 3. DiscordChatExporter
def from_dce(path: str) -> dict[str, Any]:
    """DiscordChatExporter (Tyrrrz) JSON → canonical seed (user-token OR bot; no admin).

    Maps ~1:1: top-level ``guild`` → guild, ``channel`` → channel, distinct
    ``messages[].author`` → users + members, ``messages`` → messages (each
    ``reactions[].users[]`` — or an expanded ``count`` — → ``{emoji,user_id}`` rows;
    ``isPinned`` → pinned; ``timestamp``/``timestampEdited`` preserved).
    """
    doc = _read_json(path) or {}
    g = doc.get("guild") or {}
    gid = str(g.get("id") or stable_snowflake(g.get("name", "guild"), kind="guild"))
    guild = {"id": gid, "name": g.get("name") or f"guild-{gid}", "owner_id": ""}

    ch = doc.get("channel") or {}
    cid = str(ch.get("id") or stable_snowflake(ch.get("name", "channel"), kind="channel"))
    ctype = 0 if str(ch.get("type", "GuildTextChat")).lower().find("text") >= 0 else 0
    channel = {"id": cid, "type": ctype, "guild_id": gid,
               "name": ch.get("name") or f"channel-{cid}",
               "topic": ch.get("topic"), "position": 0}

    users: dict[str, dict] = {}
    members: dict[str, dict] = {}
    messages: list[dict] = []

    def author_user(a: dict) -> str:
        aid = str(a.get("id") or stable_snowflake(a.get("name", "user"), kind="user"))
        if aid not in users:
            users[aid] = {
                "id": aid,
                "username": a.get("name") or a.get("nickname") or aid,
                "global_name": a.get("nickname") or a.get("name"),
                "discriminator": str(a.get("discriminator", "0")),
                "bot": bool(a.get("isBot", False)),
            }
            members[aid] = {"guild_id": gid, "user_id": aid, "nick": a.get("nickname"),
                            "roles": [], "joined_at": ""}
        return aid

    for msg in doc.get("messages", []) or []:
        author = msg.get("author") or {}
        aid = author_user(author)
        mid = str(msg.get("id") or _mid_from("", _to_iso(msg.get("timestamp", "")),
                                             len(messages)))
        reactions: list[dict] = []
        for rx in msg.get("reactions", []) or []:
            emoji_obj = rx.get("emoji") or {}
            name = emoji_obj.get("name") or emoji_obj.get("code") or ""
            eid = emoji_obj.get("id")
            emoji = f"{name}:{eid}" if eid else name
            reactors = rx.get("users") or []
            if reactors:
                for ru in reactors:
                    ruid = author_user(ru) if isinstance(ru, dict) else str(ru)
                    reactions.append({"emoji": emoji, "user_id": ruid})
            else:
                # No reactor list — synthesize `count` distinct synthetic reactors so
                # the rollup count is faithful.
                for i in range(int(rx.get("count", 0)) or 0):
                    reactions.append({"emoji": emoji,
                                      "user_id": stable_snowflake(f"{mid}:{emoji}:{i}",
                                                                  kind="reactor")})
        messages.append({
            "id": mid, "channel_id": cid, "guild_id": gid, "author_id": aid,
            "content": msg.get("content", "") or "",
            "timestamp": _to_iso(msg.get("timestamp", "")),
            "edited_timestamp": _to_iso(msg.get("timestampEdited")) if msg.get("timestampEdited") else None,
            "pinned": bool(msg.get("isPinned", False)),
            "mentions": [author_user(m) for m in (msg.get("mentions") or []) if isinstance(m, dict)],
            "reactions": reactions,
        })

    if not guild["owner_id"] and users:
        guild["owner_id"] = next(iter(users))
    bot_id = next(iter(users), DEFAULT_BOT_USER_ID)
    return _assemble(bot_id, list(users.values()), [guild], [channel],
                     list(members.values()), messages)


# --------------------------------------------------------------- anonymize
def anonymize(seed: dict[str, Any], *, strip_attachments: bool = False) -> dict[str, Any]:
    """One-way, structure-preserving anonymization of a canonical seed.

    Remaps every real user id → a synthetic snowflake and every username/global_name
    → a synthetic handle ``user_0001`` (stable within this call), rewriting all
    references (message authors/mentions, member/reaction user ids, guild owner). The
    mapping is derived from a running index so the output carries **no** real handle
    or id. Deterministic given the input ordering. ``strip_attachments`` blanks any
    http(s) URLs in message content.
    """
    id_map: dict[str, str] = {}
    order: list[str] = []

    def _collect(uid: str) -> None:
        if uid and uid not in id_map:
            n = len(order) + 1
            id_map[uid] = stable_snowflake(f"anon-user-{n}", kind="anon")
            order.append(uid)

    for u in seed.get("users", []):
        _collect(u["id"])
    for m in seed.get("members", []):
        _collect(m["user_id"])
    for msg in seed.get("messages", []):
        _collect(msg.get("author_id", ""))
        for uid in msg.get("mentions", []) or []:
            _collect(uid)
        for rx in msg.get("reactions", []) or []:
            _collect(rx.get("user_id", ""))

    handle = {uid: f"user_{i + 1:04d}" for i, uid in enumerate(order)}

    def M(uid: str) -> str:
        return id_map.get(uid, uid)

    out = {
        "bot_user_id": M(seed.get("bot_user_id")) if seed.get("bot_user_id") else None,
        "users": [{**u, "id": M(u["id"]), "username": handle.get(u["id"], "user"),
                   "global_name": None} for u in seed.get("users", [])],
        "guilds": [{**g, "owner_id": M(g.get("owner_id", ""))} for g in seed.get("guilds", [])],
        "channels": list(seed.get("channels", [])),
        "members": [{**m, "user_id": M(m["user_id"]), "nick": None} for m in seed.get("members", [])],
        "messages": [],
    }
    for msg in seed.get("messages", []):
        m = dict(msg)
        m["author_id"] = M(msg.get("author_id", ""))
        m["mentions"] = [M(u) for u in (msg.get("mentions", []) or [])]
        m["reactions"] = [{**rx, "user_id": M(rx.get("user_id", ""))}
                          for rx in (msg.get("reactions", []) or [])]
        if strip_attachments:
            m["content"] = _strip_urls(m.get("content", ""))
        out["messages"].append(m)
    return out


# --------------------------------------------------------------- helpers
def _assemble(bot_user_id: str, users: list, guilds: list, channels: list,
              members: list, messages: list) -> dict[str, Any]:
    return {"bot_user_id": bot_user_id, "users": users, "guilds": guilds,
            "channels": channels, "members": members, "messages": messages}


def _read_json(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _read_rows(path: str) -> Iterable[dict]:
    """Yield dict rows from a CSV or JSONL file (by extension, then by sniffing)."""
    lower = path.lower()
    if lower.endswith((".jsonl", ".ndjson")):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)
        return
    if lower.endswith(".json"):
        data = _read_json(path)
        if isinstance(data, list):
            yield from (r for r in data if isinstance(r, dict))
        elif isinstance(data, dict):
            for key in ("messages", "data", "rows"):
                if isinstance(data.get(key), list):
                    yield from (r for r in data[key] if isinstance(r, dict))
                    return
        return
    # default: CSV
    with open(path, newline="", encoding="utf-8") as fh:
        yield from csv.DictReader(fh)


def _slug(name: str) -> str:
    s = "".join(c.lower() if c.isalnum() else "_" for c in (name or "")).strip("_")
    return s or "user"


def _strip_urls(text: str) -> str:
    import re

    return re.sub(r"https?://\S+", "[link]", text or "")


def parse_mapping(pairs: list[str]) -> dict[str, str]:
    """Parse ``--map author=col content=col ts=col …`` pairs into a mapping dict."""
    mapping: dict[str, str] = {}
    for p in pairs or []:
        if "=" not in p:
            raise ValueError(f"bad --map entry '{p}' (expected key=column)")
        k, v = p.split("=", 1)
        mapping[k.strip()] = v.strip()
    return mapping
