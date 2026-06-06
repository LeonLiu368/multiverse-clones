#!/usr/bin/env python3
"""Deterministically generate a HEAVY synthetic workspace for the contract-drift task.

Output: scraped.json. Hundreds of noisy messages across channels, into which the charges-API
**v2 migration** announcement is buried. Earlier/other messages describe the deprecated v1
body ({amount: dollars, account}) as TRAPS, and the v2 announcement itself contains a
CORRECTION (customer_id -> customer) — so only a careful read of #api-changes yields the
agreed v2 contract.

Run:  python3 generate.py
"""
import json
import os
import random
from datetime import datetime, timedelta, timezone

SEED = 4242
rng = random.Random(SEED)

USERS = ["alice", "bob", "carol", "dave", "erin", "frank", "grace", "heidi", "ivan",
         "judy", "mallory", "niaj", "olivia", "peggy", "trent", "victor"]
BOTS = ["deploybot", "ci-bot", "pagerduty"]
CHANNELS = ["general", "engineering", "backend", "api-changes", "product", "random", "incidents"]
START = datetime(2024, 10, 7, 9, 0, 0, tzinfo=timezone.utc)

FILLER = {
    "general": [
        "morning all ☕", "all-hands moved to Thursday", "welcome to the new folks 👋",
        "wifi flaky again, IT on it", "lunch order by noon", "anyone at the meetup tonight?",
        "PSA: rotate your tokens this week", "kudos to support for clearing the backlog 🙌",
    ],
    "engineering": [
        "PR #771 up for review", "rebased, CI green", "flaky test in test_scheduler again",
        "bumped the http client to 1.4", "staging deploy stuck again?", "merged #780",
        "added retries to the webhook worker", "the nightly batch ran long, looking",
    ],
    "backend": [
        "migrating the jobs queue Tuesday", "added an index on orders(created_at)",
        "the rate limiter needs tuning", "who owns the refunds worker now?",
        "psql connection pool maxed during the spike", "moving secrets to vault this sprint",
        "deprecating the old /v1 endpoints soon", "added tracing to the gateway",
    ],
    "api-changes": [
        "changelog: bumped the search API page size cap to 200", "reminder: read the API style guide",
        "the webhooks signing secret rotates next week", "OpenAPI spec is regenerated nightly now",
        "deprecation calendar is in the wiki", "please version new endpoints from day one",
    ],
    "product": [
        "draft PRD for Q4 in the drive", "customer asked about bulk export again",
        "trial conversion analytics please", "pricing page copy refresh", "roadmap review next week",
    ],
    "random": [
        "🐶 dog of the day", "coffee machine broken again", "who took my mug",
        "free snacks in the kitchen", "TIL you can pin messages", "🎉 work anniversary",
    ],
    "incidents": [
        "[resolved] elevated 5xx 14:02-14:18", "checkout latency normal", "db failover done",
        "[resolved] email provider degraded", "oncall handoff: nothing active",
    ],
}

# TRAPS: stale/wrong references to the deprecated v1 body. A naive search surfaces these.
TRAPS = [
    ("backend", "trent", "the charge body is just {amount, account} right? that's what the old client sends"),
    ("general", "olivia", "does the payments API take dollars or cents? i can never remember"),
    ("engineering", "victor", "old payments code posts {\"amount\": 12.5, \"account\": \"cus_x\"} to /v1/charges, fyi"),
    ("product", "mallory", "i told a customer charges are in dollars — is that still true?"),
]

# The REAL v2 migration thread, in #api-changes. Note the customer_id -> customer correction.
THREAD = [
    ("frank", "Heads up: the charges API v1 is being deprecated. v2 is live on the gateway — please migrate clients this sprint. The v1 endpoint returns 410 after the 15th."),
    ("frank", "v2 body: POST /v2/charges with a top-level api_version: 2, and fields amount_cents (integer MINOR units — cents, not dollars), customer_id, currency. idempotency_key is now required on every charge."),
    ("grace", "quick q — is the field customer_id or customer? the regenerated OpenAPI spec shows `customer`."),
    ("frank", "Good catch — we renamed it to `customer` right before GA, the first message above is stale. So the v2 body is: {api_version: 2, amount_cents, customer, currency, idempotency_key}."),
    ("heidi", "and currency — required or optional?"),
    ("frank", "Send `currency` explicitly. It defaults to \"usd\" server-side, but clients should always include it. Recap of the agreed v2 charge body: api_version 2; amount_cents (int cents); customer; currency (\"usd\" unless otherwise); idempotency_key (required). v1's `amount` (dollars) and `account` are both gone."),
    ("ivan", "👍 updating payments.charge.build_charge_request now."),
]


def iso(dt):
    return dt.isoformat()


def main():
    msgs = []

    def add(ch, author, content, dt):
        msgs.append({"channel": ch, "author": author, "content": content, "timestamp": iso(dt)})

    t0 = START
    for day in range(12):
        day_start = t0 + timedelta(days=day)
        for _ in range(rng.randint(35, 52)):
            ch = rng.choice(CHANNELS)
            author = rng.choice(USERS + BOTS) if ch == "incidents" else rng.choice(USERS)
            add(ch, author, rng.choice(FILLER[ch]), day_start + timedelta(minutes=rng.randint(0, 9 * 60)))

    for i, (ch, author, text) in enumerate(TRAPS):
        add(ch, author, text, START + timedelta(days=1 + i % 3, hours=2, minutes=11 * i))

    base = START + timedelta(days=3, hours=1)
    for i, (author, text) in enumerate(THREAD):
        dt = base + timedelta(hours=i * 5 + rng.randint(0, 3), minutes=rng.randint(0, 59))
        add("api-changes", author, text, dt)

    msgs.sort(key=lambda m: m["timestamp"])
    out = os.path.join(os.path.dirname(__file__), "scraped.json")
    with open(out, "w") as f:
        json.dump({"messages": msgs}, f, indent=1)
    print(f"wrote {len(msgs)} messages to {out}")
    from collections import Counter
    print("per-channel:", dict(Counter(m["channel"] for m in msgs)))


if __name__ == "__main__":
    main()
