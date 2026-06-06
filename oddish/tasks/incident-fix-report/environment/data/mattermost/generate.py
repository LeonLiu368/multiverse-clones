#!/usr/bin/env python3
"""Deterministically generate a HEAVY synthetic workspace for the incident-fix-report task.

Output: scraped.json. Hundreds of noisy messages across channels. Buried in #incidents is a
pager-fatigue incident: PagerDuty logs + on-call discussion that diagnoses the root cause and
agrees a NEW paging policy. There are red herrings (a "maybe it's the DB" hypothesis) and the
OLD policy values (5% / 1 breach) appear as traps. An empty-ish #postmortems channel exists
for the agent to post its postmortem into.

Run:  python3 generate.py
"""
import json
import os
import random
from datetime import datetime, timedelta, timezone

SEED = 90210
rng = random.Random(SEED)

USERS = ["alice", "bob", "carol", "dave", "erin", "frank", "grace", "heidi", "ivan",
         "judy", "mallory", "niaj", "olivia", "peggy", "trent", "victor"]
BOTS = ["pagerduty", "deploybot", "ci-bot", "grafana"]
CHANNELS = ["general", "engineering", "backend", "incidents", "postmortems", "oncall", "random"]
START = datetime(2024, 11, 4, 9, 0, 0, tzinfo=timezone.utc)

FILLER = {
    "general": ["morning all ☕", "all-hands Thursday", "welcome new folks 👋", "wifi flaky again",
                "lunch by noon", "rotate your tokens", "kudos to support 🙌"],
    "engineering": ["PR #903 up", "rebased, CI green", "flaky test again", "bumped grafana agent",
                    "staging stuck?", "merged #910", "added tracing to the gateway"],
    "backend": ["index added on events(ts)", "jobs queue migration Tuesday", "connection pool tuning",
                "moving secrets to vault", "deprecating /v1 soon", "cache TTL ticket open"],
    "incidents": ["[resolved] elevated 5xx 14:02-14:18", "checkout latency normal", "db failover done",
                  "[resolved] email provider degraded", "cdn cache purge done"],
    "postmortems": ["postmortem template is pinned", "reminder: blameless postmortems",
                    "last week's checkout PM is in the drive", "action items tracked in Jira"],
    "oncall": ["handoff: nothing active", "secondary is heidi this week", "runbook updated",
               "silenced the noisy disk alert for now", "pagerduty schedule swapped"],
    "random": ["🐶 dog of the day", "coffee machine broken", "who took my mug", "free snacks",
               "🎉 work anniversary", "TIL you can pin messages"],
}

TRAPS = [
    ("oncall", "trent", "the api alert is set to fire at 5% error rate on a single sample, like it always has"),
    ("backend", "victor", "could the 3am pages be the DB? we saw a connection blip around then"),
    ("general", "olivia", "why do we keep getting paged at 3am for nothing"),
]

# The incident discussion in #incidents — diagnoses root cause + agrees the new policy.
THREAD = [
    ("pagerduty", ":rotating_light: PagerDuty: api error-rate 6% (1 sample over threshold) — paged on-call at 03:14 UTC"),
    ("alice", "ack — looking. error rate is already back to 0.4%. another single-sample blip."),
    ("bob", "this is the 4th 3am page this week and every one was a single transient spike that self-resolved. our alert pages on ONE breach at 5%."),
    ("victor", "could it be the DB connection blips? we saw one around 03:00."),
    ("carol", "checked — DB was healthy, the 5xx were a brief upstream timeout that cleared in <30s. so the DB is a red herring."),
    ("carol", "root cause of the pager fatigue: should_page has no sustained-breach requirement — a single window at >=5% pages immediately, so transient spikes wake people up."),
    ("dave", "proposal: require multiple consecutive breaches before paging, but keep an immediate path for real emergencies."),
    ("carol", "Agreed new paging policy: page only after >=3 CONSECUTIVE breaches at >=5% error rate. Keep a critical fast-path: if error rate >=25%, page on the first breach. Anything below 5% never pages."),
    ("alice", "👍 implementing should_page with that, and I'll write the postmortem in #postmortems with the root cause."),
]


def iso(dt):
    return dt.isoformat()


def main():
    msgs = []

    def add(ch, author, content, dt):
        msgs.append({"channel": ch, "author": author, "content": content, "timestamp": iso(dt)})

    t0 = START
    for day in range(12):
        ds = t0 + timedelta(days=day)
        for _ in range(rng.randint(34, 50)):
            ch = rng.choice(CHANNELS)
            author = rng.choice(USERS + BOTS) if ch in ("incidents", "oncall") else rng.choice(USERS)
            add(ch, author, rng.choice(FILLER[ch]), ds + timedelta(minutes=rng.randint(0, 9 * 60)))

    for i, (ch, author, text) in enumerate(TRAPS):
        add(ch, author, text, START + timedelta(days=1 + i % 3, hours=2, minutes=11 * i))

    base = START + timedelta(days=4, hours=2)
    for i, (author, text) in enumerate(THREAD):
        dt = base + timedelta(minutes=i * 17 + rng.randint(0, 9))
        add("incidents", author, text, dt)

    msgs.sort(key=lambda m: m["timestamp"])
    out = os.path.join(os.path.dirname(__file__), "scraped.json")
    with open(out, "w") as f:
        json.dump({"messages": msgs}, f, indent=1)
    print(f"wrote {len(msgs)} messages to {out}")
    from collections import Counter
    print("per-channel:", dict(Counter(m["channel"] for m in msgs)))


if __name__ == "__main__":
    main()
