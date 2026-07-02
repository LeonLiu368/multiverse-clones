"""Discord clone seed viewer (multiverse discord-clone, Discord REST API v10 shapes).

Two seed sources, normalized to one payload:
  • a canonical `fixture.json` — `{bot_user_id, users, guilds, channels, members, messages}`
    (messages carry inline `reactions: [{emoji, user_id}]`), and
  • the `discord-service:prod-v1` image — bakes the SQLite corpus at `/srv/discord.db`
    (tables users/guilds/channels/members/messages + a separate `reactions` table; JSON blobs
    for members.roles and messages.mentions). Extracted like figma/gworkspace/notion.

The frontend renders a Discord-style guild: server rail + channel sidebar (# channels by
`position`), a message pane (author avatar/name, timestamps, pinned flag, mention highlighting,
reaction pills aggregated per emoji), and a member list (humans vs bots)."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import uuid
from collections import Counter
from typing import Any, Optional

import dockerutil
from adapters.base import BaseOption, LoadResult
from adapters.fileseed import FileSeedAdapter

DISCORD_DB_PATHS = ("/srv/discord.db", "/data/discord.db", "discord.db")


def _J(x: Any, default: Any) -> Any:
    if isinstance(x, (dict, list)):
        return x
    try:
        return json.loads(x) if x else default
    except Exception:
        return default


class DiscordAdapter(FileSeedAdapter):
    id = "discord"
    display_name = "Discord"
    status = "active"
    ui_module = "discord"
    sample_files = ("discord.fixture.json",)

    def list_bases(self) -> list[BaseOption]:
        out: list[BaseOption] = []
        for ref in dockerutil.list_images("discord-service", "discord-clone", "discord-gateway"):
            out.append(BaseOption(id=ref, kind="image", ref=ref, label=ref,
                                  detail="baked discord.db corpus (docker image)"))
        out.extend(super().list_bases())
        return out

    def pull_base(self, ref: str) -> BaseOption:
        dockerutil.pull_image(ref)
        return BaseOption(id=ref, kind="image", ref=ref, label=ref, detail="pulled from registry")

    def load(self, base_id: str, overlay_path: Optional[str] = None) -> LoadResult:
        if base_id.startswith("file:") or (os.path.isfile(base_id) and base_id.endswith(".json")):
            path = os.path.abspath(os.path.expanduser(base_id[5:] if base_id.startswith("file:") else base_id))
            if not os.path.isfile(path):
                raise RuntimeError(f"seed file not found: {path}")
            parsed = self._parse(open(path, encoding="utf-8", errors="replace").read(), path)
        elif os.path.isfile(base_id) and base_id.endswith(".db"):
            parsed = self._parse_db(base_id)  # a local discord.db (e.g. the corpus checkout)
        else:
            workdir = tempfile.mkdtemp(prefix="seedview-discord-")
            dbpath = os.path.join(workdir, "discord.db")
            last = ""
            for src in DISCORD_DB_PATHS:
                try:
                    dockerutil.extract_file(base_id, src, dbpath)
                    break
                except Exception as e:
                    last = str(e)
            else:
                raise RuntimeError(f"no baked discord.db in {base_id} (probed {DISCORD_DB_PATHS}). {last}")
            parsed = self._parse_db(dbpath)

        session_id = uuid.uuid4().hex[:12]
        self._sessions[session_id] = {"path": base_id, "parsed": parsed}
        self._current = session_id
        return LoadResult(session_id=session_id, base=base_id, overlay=None, stats=parsed["stats"])

    # ---- normalization -------------------------------------------------------
    def _payload(self, users, guilds, channels, members, messages) -> dict[str, Any]:
        user_by_id = {u["id"]: u for u in users}
        # aggregate reactions per message: emoji -> {count, users[]}
        for m in messages:
            agg: dict[str, list[str]] = {}
            for r in m.pop("_reactions", []):
                agg.setdefault(r.get("emoji") or "❓", []).append(r.get("user_id") or "")
            m["reactions"] = [
                {"emoji": e, "count": len(uids),
                 "users": [ (user_by_id.get(u) or {}).get("username") or u for u in uids ]}
                for e, uids in agg.items()
            ]
            a = user_by_id.get(m.get("author_id") or "")
            m["author"] = {
                "id": m.get("author_id"),
                "username": (a or {}).get("username") or m.get("author_id"),
                "global_name": (a or {}).get("global_name"),
                "bot": bool((a or {}).get("bot")),
            }
            m["mentions"] = [
                (user_by_id.get(u) or {}).get("username") or u for u in (m.get("mentions") or [])
            ]
        channels.sort(key=lambda c: (c.get("position") or 0, c.get("name") or ""))
        messages.sort(key=lambda m: (m.get("timestamp") or "", m.get("id") or ""))
        by_channel: dict[str, list] = {}
        for m in messages:
            by_channel.setdefault(m.get("channel_id") or "", []).append(m)
        return {
            "meta": {"source": "discord"},
            "guilds": guilds,
            "channels": channels,
            "users": users,
            "members": members,
            "messages_by_channel": by_channel,
            "stats": {
                "guilds": len(guilds), "channels": len(channels), "users": len(users),
                "messages": len(messages),
                "reactions": sum(len(m["reactions"]) for m in messages),
                "pinned": sum(1 for m in messages if m.get("pinned")),
            },
        }

    def _parse(self, raw: str, path: str) -> dict[str, Any]:  # canonical fixture.json
        d = json.loads(raw)
        messages = []
        for m in d.get("messages") or []:
            m = dict(m)
            m["_reactions"] = m.pop("reactions", []) or []
            messages.append(m)
        return self._payload(
            [dict(u) for u in d.get("users") or []],
            [dict(g) for g in d.get("guilds") or []],
            [dict(c) for c in d.get("channels") or []],
            [dict(m) for m in d.get("members") or []],
            messages,
        )

    def _parse_db(self, dbpath: str) -> dict[str, Any]:  # baked discord.db
        c = sqlite3.connect(dbpath)
        c.row_factory = sqlite3.Row
        users = [dict(r) for r in c.execute("SELECT * FROM users")]
        guilds = [dict(r) for r in c.execute("SELECT * FROM guilds")]
        channels = [dict(r) for r in c.execute("SELECT * FROM channels")]
        members = [{**dict(r), "roles": _J(r["roles"], [])} for r in c.execute("SELECT * FROM members")]
        reactions_by_msg: dict[str, list] = {}
        for r in c.execute("SELECT * FROM reactions"):
            reactions_by_msg.setdefault(r["message_id"], []).append(
                {"emoji": r["emoji"], "user_id": r["user_id"]})
        messages = []
        for r in c.execute("SELECT * FROM messages"):
            m = {**dict(r), "mentions": _J(r["mentions"], [])}
            m["_reactions"] = reactions_by_msg.get(r["id"], [])
            messages.append(m)
        c.close()
        return self._payload(users, guilds, channels, members, messages)
