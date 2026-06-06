#!/usr/bin/env python3
"""Deterministically generate a HEAVY synthetic workspace for the buried-spec task.

Output: scraped.json  ({messages:[{channel,author,content,timestamp}]}) — hundreds of
believable but noisy messages across several channels, into which the real billing
overdue-fee policy discussion is buried. Earlier messages contain SUPERSEDED proposals
(grace 7, rates 2/4/6, min $10) and there are off-channel traps; the agreed final policy is
only recoverable by actually reading the #billing-policy discussion in order.

Run:  python3 generate.py   (writes scraped.json next to this file)
"""
import json
import os
import random
from datetime import datetime, timedelta, timezone

SEED = 1337
rng = random.Random(SEED)

USERS = ["alice", "bob", "carol", "dave", "erin", "frank", "grace", "heidi", "ivan",
         "judy", "mallory", "niaj", "olivia", "peggy", "trent", "victor"]
BOTS = ["deploybot", "ci-bot", "pagerduty"]

CHANNELS = ["general", "engineering", "billing-policy", "product", "random", "incidents", "design"]

START = datetime(2024, 9, 2, 9, 0, 0, tzinfo=timezone.utc)

FILLER = {
    "general": [
        "morning all ☕", "reminder: all-hands moved to Thursday 10am",
        "who has the Figma link for the new onboarding?", "lunch order going out, reply by noon",
        "welcome to the new folks joining this week 👋", "office wifi is flaky again, IT is on it",
        "PSA: please update your 1Password before Friday", "anyone going to the meetup tonight?",
        "kudos to the support team for clearing the backlog 🙌", "is prod slow for anyone else right now?",
    ],
    "engineering": [
        "PR #482 up for review when someone has a sec", "rebased the feature branch, CI is green",
        "flaky test in test_scheduler again, retrying", "bumped the postgres driver to 2.9",
        "anyone know why the staging deploy is stuck?", "merged #491, deploying to staging",
        "we should add a linter rule for that", "the cache layer needs a TTL, opening a ticket",
        "can someone approve the infra terraform change?", "heads up: migrating the jobs queue Tuesday",
        "added type hints to the invoices module", "the nightly batch ran 40min, investigating",
    ],
    "product": [
        "draft PRD for Q4 is in the drive", "customer asked about bulk export again",
        "can we get analytics on trial conversion?", "the pricing page copy needs a refresh",
        "competitor shipped a similar feature, fyi", "roadmap review pushed to next week",
        "what's our SLA on support tickets these days?", "we need a decision on the dunning emails",
    ],
    "random": [
        "🐶 dog of the day", "coffee machine is broken again", "anyone watch the game last night?",
        "free snacks in the kitchen", "the grace period for the office plants is clearly zero, RIP",
        "TIL you can pin messages here", "🎉 it's someone's work anniversary", "who keeps stealing my mug",
    ],
    "billing-policy": [
        "can we get the dunning email copy finalized this week?", "Stripe webhook retries are noisy, fyi",
        "reminder: invoice run is the 1st of the month", "do refunds count against MRR? asking for the deck",
        "the tax rounding ticket is still open", "who owns the chargeback flow now?",
        "finance close is Friday, please tag any billing PRs", "proration logic needs docs",
    ],
    "design": [
        "new icon set in Figma", "accessibility audit results are in", "updated the color tokens",
        "can eng confirm the spacing on the modal?", "user testing notes from yesterday",
        "the empty-state illustration is ready", "dark mode tokens need another pass",
    ],
    "incidents": [
        "[resolved] elevated 5xx on the api gateway 14:02-14:18", "checkout latency back to normal",
        "db failover completed, monitoring", "[resolved] email provider degraded earlier",
        "rolling back the last deploy to be safe", "oncall handoff: nothing active",
    ],
}

# Off-channel TRAPS: plausible but wrong/stale numbers a naive keyword search will surface.
TRAPS = [
    ("product", "olivia", "btw what's our late fee these days? i told a customer it's about 2% of balance, hope that's still right"),
    ("general", "trent", "someone asked support what the overdue grace period is — i said 7 days from memory, can someone confirm?"),
    ("random", "victor", "the late fee on my gym membership is like $10 flat, wild"),
    ("engineering", "frank", "old invoices code had a hardcoded 2% late fee and no cap, we ripped it out months ago"),
]

# The REAL discussion, in order, in #billing-policy. Earlier entries are SUPERSEDED.
THREAD = [
    ("alice", "Kicking off the overdue-fee policy thread. Right now billing.fees.overdue_fee does nothing. Strawman v0: flat 2% of balance after a 7-day grace period."),
    ("bob", "2% flat undercharges the really old stuff. What about tiers by days overdue — say 2% (0-30), 4% (30-60), 6% (60+)?"),
    ("carol", "Tiers are fine but legal flagged 4/6% as too high (usury). Finance is comfortable with 1.5% / 3% / 5%."),
    ("alice", "OK so tiered 1.5 / 3 / 5. Keeping the 7-day grace?"),
    ("dave", "7 days is generous and doesn't match our dunning emails (those fire at day 5). Support wants grace = 5 days."),
    ("carol", "Good point — let's make grace 5 days to line up with dunning. So no fee through day 5."),
    ("erin", "Should there be a minimum fee? At 1.5% a tiny balance generates like $0.20, not worth the ledger entry."),
    ("bob", "+1 minimum fee. $10?"),
    ("carol", "$10 min is harsh on small balances and support will get complaints. Let's do a $5.00 minimum once any fee applies."),
    ("dave", "We also need a ceiling so a huge account doesn't get a five-figure fee — legal asked for a hard cap. $250?"),
    ("carol", "Yes, hard cap of $250.00. And round to the nearest cent, half up. Zero/negative balance or non-positive days = no fee, obviously."),
    ("alice", "Locking this in so eng can implement (tracking as BILL-412). overdue_fee = nothing through day 5; then 1.5% of balance for days 6-30, 3% for 31-60, 5% for 61+; floor the fee at $5.00 once it applies; ceiling $250.00; round half-up to the cent; balance <= 0 or days <= 0 returns $0. Closing the thread, thanks all."),
    ("bob", "🎉 thanks, picking up BILL-412 now."),
]
# tier boundaries phrased as 6-30/31-60/61+ in the final, vs 0-30/30-60/60+ in the superseded
# v0 — another reason a careful read of the FINAL message matters.


def iso(dt):
    return dt.isoformat()


def main():
    msgs = []

    def add(channel, author, content, dt):
        msgs.append({"channel": channel, "author": author, "content": content, "timestamp": iso(dt)})

    # Heavy filler spread across ~12 business days.
    t = START
    for day in range(12):
        day_start = START + timedelta(days=day)
        n = rng.randint(35, 55)  # messages this day
        for _ in range(n):
            ch = rng.choice(CHANNELS)
            author = rng.choice(USERS + BOTS) if ch in ("incidents",) else rng.choice(USERS)
            text = rng.choice(FILLER[ch])
            mins = rng.randint(0, 9 * 60)  # within the workday
            add(ch, author, text, day_start + timedelta(minutes=mins))

    # Drop the traps in on days 1-3.
    for i, (ch, author, text) in enumerate(TRAPS):
        add(ch, author, text, START + timedelta(days=1 + i % 3, hours=2, minutes=11 * i))

    # The real thread runs across days 3-6, interleaved (timestamps strictly increasing).
    base = START + timedelta(days=3, hours=1)
    for i, (author, text) in enumerate(THREAD):
        # spread the 13 messages over ~3 days so they're not contiguous in the dump
        dt = base + timedelta(hours=i * 5 + rng.randint(0, 3), minutes=rng.randint(0, 59))
        add("billing-policy", author, text, dt)

    # Sort by timestamp so history reads chronologically.
    msgs.sort(key=lambda m: m["timestamp"])

    out = os.path.join(os.path.dirname(__file__), "scraped.json")
    with open(out, "w") as f:
        json.dump({"messages": msgs}, f, indent=1)
    print(f"wrote {len(msgs)} messages to {out}")
    # quick stats
    from collections import Counter
    c = Counter(m["channel"] for m in msgs)
    print("per-channel:", dict(c))


if __name__ == "__main__":
    main()
