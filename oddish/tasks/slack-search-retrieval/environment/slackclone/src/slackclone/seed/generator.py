"""Synthetic workspace generator — deterministic given a seed.

Produces a canonical seed (see ``schema``) with realistic users, channels, and
threaded, reacted conversations. Same arguments → byte-identical seed, so it is
safe for reproducible test fixtures and tasks.
"""

from __future__ import annotations

import random
from typing import Any

from ..ids import gen_id, make_ts
from . import schema

_FIRST = [
    "alice", "bob", "carol", "dave", "erin", "frank", "grace", "heidi", "ivan",
    "judy", "mallory", "niaj", "olivia", "peggy", "rupert", "sybil", "trent",
    "victor", "wendy", "yara", "zack", "nina", "omar", "priya", "quinn",
]
_LAST = ["ng", "patel", "kim", "garcia", "chen", "okafor", "silva", "haddad",
         "novak", "rossi", "walsh", "abbas", "duval", "ortiz", "frost"]
_CHANNELS = [
    ("general", "Company-wide announcements and chatter", "public_channel"),
    ("incidents", "Active production incidents and on-call coordination", "public_channel"),
    ("engineering", "Engineering discussion", "public_channel"),
    ("deploys", "Deploy notifications and rollouts", "public_channel"),
    ("random", "Non-work banter", "public_channel"),
    ("design", "Design reviews and assets", "public_channel"),
    ("support", "Customer support escalations", "public_channel"),
    ("oncall", "On-call handoffs", "private_channel"),
    ("announcements", "Official announcements", "public_channel"),
    ("data-platform", "Data platform and pipelines", "public_channel"),
]
_EMOJI = ["thumbsup", "tada", "eyes", "fire", "white_check_mark", "rocket", "sob", "raised_hands"]

_LINES = {
    "incidents": [
        "we're seeing elevated 5xx on the api gateway, anyone else?",
        "paging on-call — checkout latency p99 just spiked to 3s",
        "rolling back the last deploy to be safe",
        "root cause looks like the connection pool getting exhausted",
        "mitigation is in, error rate dropping now",
        "postmortem doc is up, please add timeline notes",
    ],
    "deploys": [
        "deploying v2.41.0 to prod",
        "canary looks healthy, promoting to 100%",
        "deploy complete, watching dashboards",
        "holding the next deploy until the incident clears",
    ],
    "engineering": [
        "PR is up for the retry-backoff change, would love a review",
        "do we have a metric for queue depth yet?",
        "the flaky test is back, it's the timeout assertion again",
        "let's add a healthcheck to the worker before we ship",
        "nice, that cut the p95 in half",
    ],
    "default": [
        "morning all",
        "can someone take a look when they get a sec?",
        "thanks, that worked",
        "lunch?",
        "+1 to that",
        "shipping it",
        "great find",
    ],
}
_BASE_EPOCH = 1_700_000_000  # fixed so ts values are deterministic


def generate(
    *,
    users: int = 12,
    channels: int = 6,
    days: int = 14,
    threads: float = 0.3,
    reactions: float = 0.4,
    seed: int = 0,
) -> dict[str, Any]:
    rng = random.Random(seed)

    # --- users (one bot) ---
    user_objs: list[dict] = []
    seen_names: set[str] = set()
    for i in range(users):
        first = _FIRST[i % len(_FIRST)]
        last = rng.choice(_LAST)
        name = first
        while name in seen_names:
            name = f"{first}.{last}"
        seen_names.add(name)
        uid = gen_id("U", rng)
        user_objs.append({
            "id": uid,
            "name": name,
            "real_name": f"{first.capitalize()} {last.capitalize()}",
            "is_bot": False,
            "tz": "America/Los_Angeles",
            "profile": {"email": f"{name}@example.com", "title": "Engineer"},
        })
    bot = {"id": gen_id("U", rng), "name": "incidentbot", "real_name": "Incident Bot",
           "is_bot": True, "tz": "UTC", "profile": {"email": "bot@example.com"}}
    user_objs.append(bot)
    uids = [u["id"] for u in user_objs]

    # --- channels ---
    chan_objs: list[dict] = []
    for name, purpose, ctype in _CHANNELS[:channels]:
        cid = gen_id("C", rng)
        chan_objs.append({
            "id": cid, "name": name, "type": ctype, "purpose": purpose,
            "topic": purpose, "created": _BASE_EPOCH, "creator": uids[0],
            "members": uids,  # everyone in every channel for simplicity
        })

    # --- messages ---
    messages: list[dict] = []
    clock = _BASE_EPOCH
    seq = 0

    def next_ts() -> str:
        nonlocal clock, seq
        clock += rng.randint(30, 1800)
        seq += 1
        return make_ts(clock, seq)

    def maybe_reactions(ts: str) -> list[dict]:
        if rng.random() >= reactions:
            return []
        n = rng.randint(1, 3)
        chosen = rng.sample(_EMOJI, n)
        return [{"name": e, "users": rng.sample(uids, rng.randint(1, min(3, len(uids))))}
                for e in chosen]

    for c in chan_objs:
        pool = _LINES.get(c["name"], _LINES["default"])
        n_roots = max(3, days * 2)
        for _ in range(n_roots):
            author = rng.choice(uids)
            ts = next_ts()
            msg = {"channel": c["id"], "ts": ts, "user": author,
                   "text": rng.choice(pool), "reactions": maybe_reactions(ts)}
            messages.append(msg)
            # thread?
            if rng.random() < threads:
                n_replies = rng.randint(1, 4)
                for _ in range(n_replies):
                    rts = next_ts()
                    messages.append({
                        "channel": c["id"], "ts": rts, "user": rng.choice(uids),
                        "text": rng.choice(pool + _LINES["default"]),
                        "thread_ts": ts, "reactions": maybe_reactions(rts),
                    })

    messages.sort(key=lambda m: float(m["ts"]))
    return schema.normalize({
        "workspace": {"id": "T0SIMULATED", "name": "Acme Sim", "domain": "acme-sim"},
        "users": user_objs,
        "channels": chan_objs,
        "messages": messages,
    })
