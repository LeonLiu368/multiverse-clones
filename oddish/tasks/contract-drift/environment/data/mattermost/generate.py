#!/usr/bin/env python3
"""Deterministically generate a heavy synthetic workspace for the contract-drift task.

Output: scraped.json (~500 messages, 7 channels). The analytics-pipeline v2 schema
migration announcement is buried in #data-platform with a key trap: "bob" posts an
early draft using `author_id`, which is later explicitly corrected to `actor_id` by
the data-platform lead "niaj". Only a careful read of #data-platform yields the agreed
v2 spec.

Run:  python3 generate.py
"""
import json
import os
import random
from datetime import datetime, timedelta, timezone
from collections import Counter

SEED = 1337
rng = random.Random(SEED)

USERS = ["alice", "bob", "carol", "dave", "erin", "frank", "grace", "heidi", "ivan",
         "judy", "mallory", "niaj", "olivia", "peggy", "trent", "victor"]
BOTS  = ["deploybot", "ci-bot", "pagerduty"]

CHANNELS = [
    "general", "engineering", "data-platform", "analytics-eng",
    "product", "random", "backend-migrations",
]

START = datetime(2024, 11, 4, 9, 0, 0, tzinfo=timezone.utc)   # Monday

# ─── filler pools ────────────────────────────────────────────────────────────

FILLER = {
    "general": [
        "Morning everyone ☕",
        "All-hands moved to Thursday — see calendar invite.",
        "Welcome to the new folks joining this week! 👋",
        "WiFi flaky on floor 3, IT is aware.",
        "Lunch order by noon please.",
        "Anyone going to the ML meetup tonight?",
        "PSA: rotate your API tokens this sprint.",
        "Kudos to support for clearing the backlog 🙌",
        "Reminder: Q4 planning docs due Friday.",
        "Happy Friday people, great week 🎉",
        "OOO today, ping bob for urgent stuff.",
        "Office closed on the 28th — public holiday.",
        "New hire onboarding doc is in Notion.",
        "Standup in 5.",
        "EOD sync cancelled today.",
    ],
    "engineering": [
        "PR #1142 up for review — needs a second pair of eyes.",
        "Rebased on main, CI green.",
        "Flaky test in test_scheduler again 😤",
        "Bumped the HTTP client dep to 2.1.",
        "Staging deploy stuck? Looks like the queue is backed up.",
        "Merged #1150 — nice cleanup frank.",
        "Added retries to the webhook worker.",
        "Nightly batch ran long, still investigating.",
        "Who owns the refund worker now?",
        "The rate limiter needs tuning on the /v2 endpoints.",
        "Added tracing to the ingestion gateway.",
        "Deployed hotfix 1.3.7 to prod — all good.",
        "Dependency audit done, 3 minors to bump.",
        "New linter rule enabled — fix your line lengths 😅",
        "Memory leak in the stream consumer, fix incoming.",
    ],
    "product": [
        "Draft PRD for the analytics dashboard is in the Drive.",
        "Customer asked about bulk export — adding to backlog.",
        "Trial conversion analytics deck ready for review.",
        "Pricing page copy refresh — feedback welcome.",
        "Roadmap review next Tuesday.",
        "New feature flag for cohort analysis shipped to beta.",
        "User research sessions scheduled for Thursday.",
        "Competitive teardown doc updated.",
        "NPS survey going out this week.",
        "Sprint review is at 3pm Friday.",
    ],
    "random": [
        "🐶 Dog of the day pic incoming",
        "Coffee machine broken AGAIN",
        "Who took my mug? 😡",
        "Free snacks in the kitchen (thanks carol!)",
        "TIL you can pin messages in channels",
        "🎉 Work anniversary for frank today!",
        "Highly recommend the lunch special today",
        "Friday trivia at 5pm in #random-games",
        "Thunderstorm outside, cozy day ⛈️",
        "Best debugging playlist? Drop links 🎧",
    ],
    "backend-migrations": [
        "Migration M-44 (jobs queue) runs Tuesday night.",
        "Added an index on events(recorded_at) — 3x query speedup.",
        "Schema migration for the new analytics tables landed in staging.",
        "Who owns the rollback plan for M-44?",
        "Postgres connection pool maxed during the spike — bumped max_conn.",
        "Moving secrets to Vault this sprint.",
        "Deprecating old /v1 endpoints after the 15th — send reminders.",
        "Backfill for historical events is 72% done.",
        "M-47 (analytics schema) blocked on the data-platform signoff.",
        "Green light from niaj — M-47 is a go for next Tuesday.",
        "Migration took 40 min, no downtime. ✅",
        "Rollback window closes at midnight.",
    ],
    "analytics-eng": [
        # TRAP: engineers who haven't updated yet, using old v1 field names
        "shipping page_view events with the old schema for now — will update when we have more info",
        "our publisher still uses `name`/`user_id`/`data` — need to migrate after the deadline",
        "does anyone have a snippet for the new publisher? still on v1 on our end",
        "we're emitting: {\"name\": \"checkout\", \"user_id\": \"u99\", \"data\": {}, \"timestamp\": 1700000000.0, \"schema_version\": \"1\"} — is that still ok?",
        "pipeline keeps rejecting our events — probably still on v1 format",
        "v1 to v2 migration effort tracked in JIRA-3310",
        "how many services are still on v1? we show 11 in the dashboard",
        "our team has 3 publishers to migrate, ETA end of sprint",
        "migrating the login event first since it's highest volume",
        "anyone hit issues with the recorded_at conversion? We were off by 1000x initially",
        "note: schema_version needs to be int 2 not string — caught that the hard way",
        "the pipeline validator rejects string schema_version — must be integer",
        "draft migration script is in the analytics-eng wiki",
        "does the new spec have a required `source` field? can't find it in the announcement",
        "no `source` field — checked with niaj. just the 5 fields in the spec.",
    ],
}

# ─── the real v2 migration thread in #data-platform ─────────────────────────
# This is the authoritative source. We embed it as a list of (author, text) tuples
# and scatter them over ~3 days starting from day 4.

DATA_PLATFORM_THREAD = [
    # Day 4: niaj announces the migration
    ("niaj",
     "📢 Data Platform Update: the analytics event pipeline is migrating to **schema v2** "
     "starting this sprint. All publishers must be updated before the v1 sunset on the 22nd. "
     "I'll post the full spec in this thread. Summary of changes incoming."),

    ("niaj",
     "v2 field changes (from v1 → v2):\n"
     "  • `name`        → `event_name`\n"
     "  • `user_id`     → `actor_id`\n"
     "  • `data`        → `attributes`\n"
     "  • `timestamp`   → `recorded_at`  (int milliseconds, NOT float seconds)\n"
     "  • `schema_version`: integer 2 (was string \"1\")\n"
     "Migration guide in the wiki under /data-platform/v2-migration."),

    ("carol",
     "Thanks niaj! One question — is the timestamp field called `recorded_at` or `event_time`? "
     "I saw `event_time` mentioned in an old RFC doc."),

    ("niaj",
     "It's `recorded_at`. The old RFC used `event_time` as a placeholder — disregard that. "
     "Final spec uses `recorded_at` as an **integer milliseconds** Unix timestamp."),

    # TRAP: bob posts early draft using wrong field name
    ("bob",
     "Getting started on the migration. My initial read: v2 uses `event_name`, `author_id`, "
     "`attributes`, `recorded_at`. Does that look right?"),

    ("alice",
     "Looks close but I think the user field might be different — niaj can confirm?"),

    # Explicit correction of bob's trap
    ("niaj",
     "⚠️ Correction on bob's message above: the field is **`actor_id`**, NOT `author_id`. "
     "`author_id` was used in an early internal draft but was dropped before the spec was finalised. "
     "The correct v2 field is `actor_id`. Please don't copy the `author_id` name from earlier "
     "messages in this thread."),

    ("bob",
     "Thanks for clarifying! Updated my PR — using `actor_id`. Sorry for the confusion."),

    # More Q&A
    ("dave",
     "What type is `recorded_at` exactly? Our publisher uses a float currently."),

    ("niaj",
     "Integer milliseconds. Convert with `int(time.time() * 1000)`. The pipeline rejects "
     "float values — the type check is strict."),

    ("heidi",
     "And `schema_version` — is it the integer 2 or the string \"2\"?"),

    ("niaj",
     "Integer 2. **Not** the string \"2\". The validator does a strict type check: "
     "`isinstance(schema_version, int)` must be True."),

    ("erin",
     "Are any other fields changing? Is there a new required `source` field I saw somewhere?"),

    ("niaj",
     "No `source` field. That was proposed and rejected. The v2 spec has exactly these 5 fields: "
     "`event_name`, `actor_id`, `attributes`, `recorded_at`, `schema_version`. Nothing more, nothing less."),

    # Final canonical summary
    ("niaj",
     "**FINAL v2 analytics event spec (canonical, use this):**\n"
     "```python\n"
     "{\n"
     "    \"event_name\":     str,   # was 'name'\n"
     "    \"actor_id\":       str,   # was 'user_id'  — NOTE: NOT 'author_id'\n"
     "    \"attributes\":     dict,  # was 'data'\n"
     "    \"recorded_at\":    int,   # milliseconds since epoch (int, NOT float)\n"
     "    \"schema_version\": 2,     # integer 2, NOT string '2'\n"
     "}\n"
     "```\n"
     "Deadline: all publishers migrated by EOD on the 22nd. The v1 pipeline endpoint "
     "will return 410 Gone after that date."),

    ("ivan",
     "👍 migrating our publisher now. ETA: tomorrow morning."),

    ("mallory",
     "Updated 4 publishers in the checkout service. Tests passing with the new spec."),

    ("trent",
     "Migration guide is great, niaj. PR for the events service is up: #1189."),

    # Follow-up clarification day 6
    ("frank",
     "Heads up: the backend-migrations team will run M-47 (the DB schema for v2 events) "
     "on Tuesday night. No action needed from publishers — just a heads-up."),

    ("carol",
     "Confirmed our publisher is migrated and events are flowing through the v2 pipeline. ✅"),

    ("niaj",
     "Thanks everyone for the quick turnaround. 17 of 20 publishers updated so far. "
     "Ping me if you hit issues — the remaining 3 teams have until the 22nd."),
]

# ─── #analytics-eng TRAP messages (v1 snippets + migration confusion) ────────
ANALYTICS_ENG_TRAPS = [
    ("bob",  "quick question — is it `author_id` or `actor_id`? I keep mixing these up"),
    ("alice", "pretty sure it's actor_id, bob confirmed the correction in #data-platform"),
    ("bob",  "right, actor_id — was confused by my own early message 😅"),
    ("dave", "our v1 snippet: {\"name\": \"signup\", \"user_id\": \"u1\", \"data\": {}, \"timestamp\": 1700000123.4, \"schema_version\": \"1\"}"),
    ("erin", "that's v1, dave — don't send that to the new pipeline"),
    ("frank","I saw someone use author_id in a PR — rejected by CI, actor_id is the correct field"),
    ("heidi","reminder: schema_version must be integer 2, string '2' fails the validator"),
    ("grace","timestamp field is gone — use recorded_at as int milliseconds in v2"),
]

# ─── #backend-migrations partial/incomplete info (trap: don't rely on this) ──
BACKEND_MIGRATIONS_EXTRA = [
    ("trent", "analytics schema v2 migration notes: new field names, recorded_at replaces timestamp"),
    ("victor","is the user field user_id or something else in v2? can't find it in this channel"),
    ("alice", "check #data-platform for the authoritative spec, this channel only has partial info"),
    ("dave",  "M-47 schema adds columns: event_name, actor_id, attributes, recorded_at, schema_version"),
    ("carol", "don't use author_id — that was a draft name that got corrected, see #data-platform"),
    ("ivan",  "confirmed with niaj: actor_id is correct, not author_id"),
]


def iso(dt: datetime) -> str:
    return dt.isoformat()


def main() -> None:
    msgs = []

    def add(ch: str, author: str, content: str, dt: datetime) -> None:
        msgs.append({
            "channel":   ch,
            "author":    author,
            "content":   content,
            "timestamp": iso(dt),
        })

    # ── filler: ~300 messages across all 7 channels over 14 days ─────────────
    for day in range(14):
        day_start = START + timedelta(days=day)
        n = rng.randint(18, 28)
        for _ in range(n):
            ch     = rng.choice(CHANNELS)
            author = rng.choice(USERS)
            pool   = FILLER.get(ch, FILLER["general"])
            add(ch, author, rng.choice(pool),
                day_start + timedelta(minutes=rng.randint(0, 9 * 60)))

    # ── #data-platform thread: ~22 messages over days 4–7 ────────────────────
    base_dp = START + timedelta(days=4, hours=9)
    for i, (author, text) in enumerate(DATA_PLATFORM_THREAD):
        dt = base_dp + timedelta(
            hours=i * 3 + rng.randint(0, 2),
            minutes=rng.randint(0, 59),
        )
        add("data-platform", author, text, dt)

    # ── #analytics-eng: old v1 examples + trap messages ──────────────────────
    base_ae = START + timedelta(days=2, hours=10)
    # first: filler from the pool (already included above), plus extra traps
    for i, (author, text) in enumerate(ANALYTICS_ENG_TRAPS):
        dt = base_ae + timedelta(days=i // 3, hours=i * 4, minutes=rng.randint(0, 59))
        add("analytics-eng", author, text, dt)
    # extra filler in analytics-eng
    for _ in range(30):
        dt = START + timedelta(days=rng.randint(0, 13),
                               minutes=rng.randint(0, 9 * 60))
        add("analytics-eng", rng.choice(USERS), rng.choice(FILLER["analytics-eng"]), dt)

    # ── #backend-migrations: partial info (trap) ──────────────────────────────
    base_bm = START + timedelta(days=3, hours=14)
    for i, (author, text) in enumerate(BACKEND_MIGRATIONS_EXTRA):
        dt = base_bm + timedelta(hours=i * 6, minutes=rng.randint(0, 59))
        add("backend-migrations", author, text, dt)
    for _ in range(25):
        dt = START + timedelta(days=rng.randint(0, 13),
                               minutes=rng.randint(0, 9 * 60))
        add("backend-migrations", rng.choice(USERS),
            rng.choice(FILLER["backend-migrations"]), dt)

    # ── extra filler to push total toward ~500 ────────────────────────────────
    target = 500
    while len(msgs) < target:
        ch     = rng.choice(CHANNELS)
        author = rng.choice(USERS)
        pool   = FILLER.get(ch, FILLER["general"])
        dt     = START + timedelta(
            days=rng.randint(0, 13),
            minutes=rng.randint(0, 9 * 60),
        )
        add(ch, author, rng.choice(pool), dt)

    msgs.sort(key=lambda m: m["timestamp"])

    out = os.path.join(os.path.dirname(__file__), "scraped.json")
    with open(out, "w") as f:
        json.dump({"messages": msgs}, f, indent=1)

    print(f"wrote {len(msgs)} messages to {out}")
    print("per-channel:", dict(Counter(m["channel"] for m in msgs)))


if __name__ == "__main__":
    main()
