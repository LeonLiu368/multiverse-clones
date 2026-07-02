"""Capture discord-clone parity demos in-process against the real baked corpus.

Boots the clone's actual FastAPI app (`create_app`) on a temp COPY of the committed
`discord_corpus.db` and drives it with TestClient — so `clone_output` is the exact
HTTP envelope the gateway serves (and running this verifies the corpus format is
accepted). `real_output` goldens are authored from the Discord API v10 docs.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

CLONE = Path(__file__).resolve().parents[2] / "clones" / "discord-clone"
sys.path.insert(0, str(CLONE / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from discordclone.api.app import create_app  # noqa: E402

SEED_REL = "discord_corpus.db"
AUTH = {"Authorization": "Bot discord-clone-token"}


def build() -> dict:
    tmp = Path(tempfile.mkdtemp()) / "discord.db"
    shutil.copy(CLONE / SEED_REL, tmp)
    client = TestClient(create_app(str(tmp)))

    def get(path: str, **params):
        r = client.get(path, headers=AUTH, params=params or None)
        r.raise_for_status()
        return r.json()

    me = get("/users/@me")
    guild = get("/users/@me/guilds")[0]
    gid = guild["id"]
    channels = get(f"/guilds/{gid}/channels")
    by_name = {c["name"]: c for c in channels}
    incidents = by_name["incidents"]
    deploys = by_name["deploys"]

    demos = []

    # ---- GET: list guild channels (server sidebar) --------------------------
    demos.append({
        "id": "list-channels",
        "title": "List a guild's channels",
        "method": "GET",
        "capability": "Guild channels",
        "seed_excerpt": {"guilds": [{"id": gid, "name": guild["name"]}],
                         "channels": [{"id": c["id"], "name": c["name"], "type": c["type"]}
                                      for c in channels[:3]]},
        "ui": {"type": "list", "title": f"Discord › {guild['name']}",
               "rows": [{"icon": "#", "title": c["name"], "sub": c["id"],
                         "tags": [c.get("topic") or ""][:1] if c.get("topic") else []}
                        for c in channels]},
        "agent": {"cli": f"discord guilds channels {gid}",
                  "mcp": {"tool": "discord_get_guild_channels", "args": {"guild_id": gid}}},
        "real_mapping": {
            "api": "GET /guilds/{guild.id}/channels",
            "mcp": "discord-mcp › discord_get_guild_channels",
            "doc": "https://discord.com/developers/docs/resources/guild#get-guild-channels"},
        "clone_output": channels,
        "real_output": [{"id": "1046156542114368061", "type": 0, "guild_id": "1046156542114368056",
                         "name": "incidents", "topic": "live incident channel", "position": 3,
                         "nsfw": False, "rate_limit_per_user": 0, "parent_id": None,
                         "permission_overwrites": []}],
    })

    # ---- GET: channel history (the chat view, snowflake pagination) ---------
    history = get(f"/channels/{incidents['id']}/messages", limit=10)
    demos.append({
        "id": "channel-history",
        "title": "Read channel message history",
        "method": "GET",
        "capability": "Message history (before/after/around + limit, newest-first)",
        "seed_excerpt": {"messages": [{"id": m["id"], "author": m["author"]["username"],
                                       "content": m["content"][:60]} for m in history[:3]]},
        "ui": {"type": "chat", "title": f"Discord › #{incidents['name']}",
               "messages": [{"user": m["author"].get("global_name") or m["author"]["username"],
                             "ts": m["timestamp"][:16].replace("T", " "),
                             "text": m["content"]} for m in reversed(history)]},
        "agent": {"cli": f"discord channels messages {incidents['id']} --limit 10",
                  "mcp": {"tool": "discord_get_messages",
                          "args": {"channel_id": incidents["id"], "limit": 10}}},
        "real_mapping": {
            "api": "GET /channels/{channel.id}/messages?limit=10",
            "mcp": "discord-mcp › discord_get_messages",
            "doc": "https://discord.com/developers/docs/resources/message#get-channel-messages"},
        "clone_output": history[:3],
        "real_output": [{"id": "1146245402942428712", "channel_id": "1046156542114368061",
                         "author": {"id": "80351110224678912", "username": "sre.lena",
                                    "global_name": "Lena", "discriminator": "0", "bot": False,
                                    "avatar": None},
                         "content": "confirmed: after TTL=300 the p99 is back under 400ms.",
                         "timestamp": "2026-06-07T12:04:11.000000+00:00",
                         "edited_timestamp": None, "tts": False, "mention_everyone": False,
                         "mentions": [], "mention_roles": [], "attachments": [], "embeds": [],
                         "pinned": False, "type": 0}],
    })

    # ---- GET: guild message search (T2 grammar) ------------------------------
    search = get(f"/guilds/{gid}/messages/search", content="PRICING_CACHE_TTL")
    demos.append({
        "id": "search-messages",
        "title": "Search guild messages",
        "method": "GET",
        "capability": "messages/search param grammar (content/channel_id/author_id/has/pinned)",
        "seed_excerpt": {"needle": "root cause: PRICING_CACHE_TTL was set to 0 …",
                         "channel": f"#{incidents['name']}"},
        "ui": {"type": "chat", "title": "Discord › search: PRICING_CACHE_TTL",
               "messages": [{"user": m["author"].get("global_name") or m["author"]["username"],
                             "ts": m["timestamp"][:16].replace("T", " "),
                             "text": m["content"]}
                            for grp in search["messages"] for m in grp]},
        "agent": {"cli": f'discord guilds search {gid} --content "PRICING_CACHE_TTL"',
                  "mcp": {"tool": "discord_search_messages",
                          "args": {"guild_id": gid, "content": "PRICING_CACHE_TTL"}}},
        "real_mapping": {
            "api": "GET /guilds/{guild.id}/messages/search?content=",
            "mcp": "discord-mcp › discord_search_messages",
            "doc": "https://discord.com/developers/docs/resources/guild"},
        "clone_output": search,
        "real_output": {"total_results": 2, "messages": [[{
            "id": "1146245402942428708", "channel_id": "1046156542114368061",
            "author": {"id": "80351110224678913", "username": "oncall.raj",
                       "global_name": "Raj", "discriminator": "0", "bot": False, "avatar": None},
            "content": "root cause: PRICING_CACHE_TTL was set to 0 in the last deploy",
            "timestamp": "2026-06-07T11:41:03.000000+00:00", "edited_timestamp": None,
            "pinned": False, "type": 0, "hit": True}]]},
    })

    # ---- POST: send message (write→read round-trip) ---------------------------
    before = get(f"/channels/{deploys['id']}/messages", limit=20)
    r = client.post(f"/channels/{deploys['id']}/messages", headers=AUTH,
                    json={"content": "deploy: checkout-service v2.31.1 → prod ✅ (TTL fix)"})
    r.raise_for_status()
    created = r.json()
    after = get(f"/channels/{deploys['id']}/messages", limit=20)
    demos.append({
        "id": "send-message",
        "title": "Send a message",
        "method": "POST",
        "capability": "Create message — write→read round-trip (hydrated snowflake/timestamp/author)",
        "seed_excerpt": {"channel": f"#{deploys['name']}", "messages_before": len(before)},
        "ui": {"type": "chat", "title": f"Discord › #{deploys['name']}",
               "messages": [{"user": m["author"].get("global_name") or m["author"]["username"],
                             "ts": m["timestamp"][:16].replace("T", " "),
                             "text": m["content"]} for m in reversed(after)]},
        "agent": {"cli": f'discord channels send {deploys["id"]} "deploy: checkout-service v2.31.1 → prod ✅ (TTL fix)"',
                  "mcp": {"tool": "discord_send_message",
                          "args": {"channel_id": deploys["id"],
                                   "content": "deploy: checkout-service v2.31.1 → prod ✅ (TTL fix)"}}},
        "real_mapping": {
            "api": "POST /channels/{channel.id}/messages",
            "mcp": "discord-mcp › discord_send_message",
            "doc": "https://discord.com/developers/docs/resources/message#create-message"},
        "clone_output": created,
        "real_output": {"id": "1146245402942428999", "channel_id": deploys["id"],
                        "author": {"id": me["id"], "username": me["username"],
                                   "global_name": me.get("global_name"), "discriminator": "0",
                                   "bot": True, "avatar": None},
                        "content": "deploy: checkout-service v2.31.1 → prod ✅ (TTL fix)",
                        "timestamp": "2026-06-07T12:30:00.000000+00:00", "edited_timestamp": None,
                        "tts": False, "mention_everyone": False, "mentions": [],
                        "mention_roles": [], "attachments": [], "embeds": [],
                        "pinned": False, "type": 0},
        "change": {
            "before": [{"id": m["id"], "text": m["content"][:70]} for m in reversed(before)],
            "after": [{"id": m["id"], "text": m["content"][:70]} for m in reversed(after)],
            "new_id": created["id"]},
    })

    return {
        "clone": "discord-clone",
        "product": "Discord",
        "real_service": {
            "name": "Discord REST API v10",
            "reference": "https://discord.com/developers/docs/reference",
            "api_base": "https://discord.com/api/v10"},
        "parity": {"verdict": "HIGH (audited: meets clone-standard-v1, 0 P0)",
                   "note": "snowflake string ids, ISO-8601 timestamps, Bot-token auth, before/after/around pagination newest-first, real error codes (10003/10008/10004/50035), search results carry hit:true."},
        "capture_note": "captured via the clone's real FastAPI app (TestClient) on a temp copy of the committed baked corpus — the exact HTTP envelopes the gateway serves.",
        "seed_file": SEED_REL,
        "surfaces": {"cli": "discord", "mcp": "discord-mcp"},
        "demos": demos,
    }


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "data" / "discord-clone.json"
    manifest = build()
    out.write_text(json.dumps(manifest, indent=2, default=str))
    print(f"OK discord-clone: {len(manifest['demos'])} demos, seed '{manifest['seed_file']}' accepted -> {out}")
