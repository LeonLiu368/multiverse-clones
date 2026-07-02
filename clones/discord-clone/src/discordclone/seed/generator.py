"""Deterministic synthetic Discord guild generator.

Produces a canonical seed doc (see ``schema.py``) for a small but realistic
engineering guild: a handful of members, several text channels, and a body of
message history — including a **buried incident thread** whose decision an agent
must recover (read history / search) to complete a round-trip task. Seeded by a
fixed ``random.Random`` + a deterministic ``Snowflake`` clock so the same
``seed=`` yields a byte-identical corpus (R1.6).
"""

from __future__ import annotations

import random
from typing import Any

from ..ids import Snowflake, timestamp_of
from ..store import iso_from_ms

# A fixed base time (2023-05-01T00:00:00Z in ms) for the deterministic clock, so the
# whole corpus has stable snowflakes + ISO timestamps.
BASE_MS = 1682899200000

BOT_USER_ID = "900000000000000001"

MEMBERS = [
    ("mira",   "Mira Chen",     False),
    ("dev",    "Dev Okoro",     False),
    ("lena",   "Lena Fischer",  False),
    ("sam",    "Sam Rivera",    False),
    ("priya",  "Priya Nair",    False),
    ("watchdog", "Watchdog",    True),
]

CHANNELS = [
    ("announcements", "Company-wide announcements", 0),
    ("general",       "Team chatter",               1),
    ("engineering",   "Eng discussion",             2),
    ("incidents",     "Production incidents and postmortems", 3),
    ("deploys",       "Deploy notifications",        4),
]


def _mk(rng: random.Random) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(8))


def generate(guild: str = "Acme Engineering", seed: int = 0) -> dict[str, Any]:
    rng = random.Random(seed)
    sf = Snowflake(seed_ms=BASE_MS + seed)

    users: list[dict] = []
    members: list[dict] = []
    channels: list[dict] = []
    messages: list[dict] = []

    # --- users (members + the bot) ---
    user_ids: dict[str, str] = {}
    # The bot user is fixed so /users/@me is stable for the verifier.
    users.append({"id": BOT_USER_ID, "username": "clone-bot", "global_name": "Clone Bot",
                  "bot": True})
    user_ids["clone-bot"] = BOT_USER_ID
    for uname, gname, is_bot in MEMBERS:
        uid = sf.next()
        user_ids[uname] = uid
        users.append({"id": uid, "username": uname, "global_name": gname, "bot": is_bot})

    guild_id = sf.next()
    owner_id = user_ids["mira"]
    joined = iso_from_ms(BASE_MS - 86400000)
    for uname in list(user_ids):
        members.append({"guild_id": guild_id, "user_id": user_ids[uname],
                        "nick": None, "roles": [], "joined_at": joined})

    # --- channels ---
    chan_ids: dict[str, str] = {}
    for name, topic, pos in CHANNELS:
        cid = sf.next()
        chan_ids[name] = cid
        channels.append({"id": cid, "type": 0, "guild_id": guild_id, "name": name,
                         "topic": topic, "position": pos})

    def post(channel: str, author: str, content: str, *, pinned: bool = False,
             mentions: list[str] | None = None, reactions: list[tuple[str, str]] | None = None) -> str:
        mid = sf.next()
        ts = iso_from_ms(timestamp_of(mid))
        messages.append({
            "id": mid, "channel_id": chan_ids[channel], "guild_id": guild_id,
            "author_id": user_ids[author], "content": content, "timestamp": ts,
            "pinned": pinned, "mentions": [user_ids[m] for m in (mentions or [])],
            "reactions": [{"emoji": e, "user_id": user_ids[u]} for e, u in (reactions or [])],
        })
        return mid

    # --- general chatter (noise) ---
    post("general", "dev", "morning all, coffee machine is fixed ☕")
    post("general", "priya", "anyone else seeing slow CI today?")
    post("general", "sam", "yeah the runners are backed up, looking into it")
    post("general", "lena", "lunch at 12:30?")
    post("general", "mira", "welcome to the server, Priya! 🎉", mentions=["priya"])

    # --- engineering discussion (noise + one useful config nugget) ---
    post("engineering", "dev", "pushing the new rate-limiter branch for review")
    post("engineering", "lena", "what limit are we going with?")
    post("engineering", "dev",
         "per the load test we settled on 120 requests/min per API key, burst of 20")
    post("engineering", "lena", "cool, I'll wire that into the gateway config")
    post("engineering", "sam", "don't forget the retry-after header should be seconds not ms")

    # --- the BURIED INCIDENT decision (the task hinges on recovering this) ---
    post("incidents", "watchdog",
         "🚨 ALERT: checkout-service p99 latency > 3s for 10m (SEV-2)")
    post("incidents", "mira", "on it. pulling the traces now")
    post("incidents", "sam", "looks like the new pricing cache is cold-missing on every request")
    post("incidents", "mira",
         "root cause: PRICING_CACHE_TTL was set to 0 in the last deploy, so nothing caches")
    inc_decision = post(
        "incidents", "lena",
        "DECISION: set PRICING_CACHE_TTL back to 300 seconds and redeploy checkout-service. "
        "This is the agreed remediation for incident INC-4471.",
        pinned=True, reactions=[("✅", "mira"), ("✅", "sam")])
    post("incidents", "mira", "agreed, rolling it now", mentions=["lena"])
    post("incidents", "sam",
         "confirmed: after TTL=300 the p99 is back under 400ms. closing INC-4471.")

    # --- deploy log (noise) ---
    post("deploys", "watchdog", "deploy: checkout-service v2.31.0 → prod ✅")
    post("deploys", "watchdog", "deploy: checkout-service v2.31.1 (hotfix TTL) → prod ✅")

    # --- announcements (pinned welcome) ---
    post("announcements", "mira",
         "Welcome to Acme Engineering. Incident decisions are recorded in #incidents.",
         pinned=True)

    return {
        "bot_user_id": BOT_USER_ID,
        "users": users,
        "guilds": [{"id": guild_id, "name": guild, "owner_id": owner_id,
                    "description": "Acme's engineering server"}],
        "channels": channels,
        "members": members,
        "messages": messages,
        # A convenience index the tests/task can consult (not persisted).
        "_index": {
            "guild_id": guild_id,
            "channels": chan_ids,
            "users": user_ids,
            "incident_decision_message_id": inc_decision,
        },
    }
