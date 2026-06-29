#!/usr/bin/env python3
"""Deterministically generate a HEAVY synthetic workspace for the incident-fix-report task.

Output: scraped.json. ~500 messages across channels. The #sre-oncall channel contains a
detailed SLO threshold review discussion with the agreed thresholds. Red herrings (old
values, wrong proposals) appear and are explicitly rejected. The final agreed spec is only
clearly stated in #sre-oncall.

Run:  python3 generate.py
"""
import json
import os
import random
from datetime import datetime, timedelta, timezone

SEED = 1337
rng = random.Random(SEED)

USERS = ["alice", "bob", "carol", "dave", "erin", "frank", "grace", "heidi", "ivan",
         "judy", "mallory", "niaj", "olivia", "peggy", "trent", "victor"]
BOTS = ["deploybot", "ci-bot", "grafana", "alertmanager"]
START = datetime(2024, 11, 1, 9, 0, 0, tzinfo=timezone.utc)

FILLER = {
    "general": [
        "morning all, coffee machine is fixed",
        "all-hands Thursday at 4pm",
        "welcome new folks joining this week",
        "wifi is flaky in the east wing again",
        "lunch by noon?",
        "reminder: rotate your tokens before EOW",
        "kudos to the support team this week",
        "happy Friday everyone",
        "PSA: expense reports due by end of month",
        "anyone up for a team lunch today?",
        "heads up: office closed Monday for the holiday",
        "new hire orientation deck is in the drive",
        "great job on the release everyone",
        "shoutout to dave for the quick infra fix",
        "does anyone have the dashboard link?",
    ],
    "engineering": [
        "PR #903 up for review",
        "rebased the auth PR, CI is green",
        "flaky test in the payment suite again",
        "bumped grafana agent to latest",
        "is staging stuck? getting 502s",
        "merged #910, deploying now",
        "added distributed tracing to the gateway",
        "dependency audit done, 3 vulns patched",
        "the lint check is now enforced in CI",
        "anyone seen the load balancer restart?",
        "RFC: moving to gRPC for internal comms",
        "API deprecation schedule posted in wiki",
        "updated the runbook for database failover",
        "feature flags doc updated",
        "code freeze starts Friday noon",
    ],
    "product": [
        "roadmap review at 2pm",
        "user research results are in the drive",
        "new feature spec posted for review",
        "A/B test results look promising",
        "quarterly planning starts Monday",
        "design review feedback incorporated",
        "customer feedback digest for the week",
        "shipping the dashboard redesign next sprint",
        "metrics for last launch look good",
        "stakeholder demo prep Thursday",
    ],
    "random": [
        "dog of the day: golden retriever edition",
        "coffee machine broken again, someone help",
        "who took my mug from the kitchen",
        "free snacks in the break room",
        "work anniversary shoutout",
        "TIL you can pin messages in Mattermost",
        "weekend plans? I'm going hiking",
        "anyone know a good lunch spot near the office?",
        "trivia night at the pub tonight",
        "best programming language debate: GO",
    ],
    "incidents": [
        "[resolved] elevated 5xx 14:02-14:18 UTC",
        "checkout latency back to normal",
        "db failover completed successfully",
        "[resolved] email provider degraded 2h window",
        "cdn cache purge completed",
        "upstream payment gateway timeout resolved",
        "memory leak patched and deployed",
        "[auto] heartbeat check passed",
        "load balancer config rolled back",
        "disk alert resolved: expanded volume",
    ],
    "alerts-dev": [
        "testing the new prometheus alert rules",
        "false positive rate too high on disk alerts",
        "alert for p99 latency needs tuning",
        "testing notification routing to #sre-oncall",
        "webhook integration working",
        "silenced noisy disk alert for now",
        "working on deduplication logic",
        "alert batching implementation in progress",
        "testing the error rate calculator",
    ],
    "error-budget-reports": [
        "weekly error budget report: all services within SLO",
        "monthly SLO review scheduled for next Friday",
        "Q3 error budget summary posted in wiki",
        "note: error budget monitor update pending",
        "SLO compliance: 99.94% availability last week",
    ],
}

# The main SLO review thread in #sre-oncall (~150 messages)
# Story arc with traps, debates, and final agreement
SRE_ONCALL_THREAD = [
    # Kickoff
    ("alice", "hey team, we need to do the SLO threshold review I mentioned. we've been getting false-positive pages and the current thresholds are wrong"),
    ("alice", "current code has: critical if error_rate > 0.10 or budget > 95%. this missed real incidents last month"),
    ("bob", "yeah I got paged 3 times last week and each time the service was actually fine. the 0.10 threshold is too high"),
    ("carol", "agreed. we had a real incident where error rate was 0.07 and we didn't get paged in time because threshold was 0.10"),
    ("dave", "also the budget threshold at 95% is way too late - by the time we're at 95% consumed we're already in trouble"),
    ("frank", "I think we should keep 0.10 as the threshold to avoid alert fatigue. lowering it will just mean more false positives"),
    ("alice", "frank - actually the opposite is happening. 0.10 is causing us to MISS incidents, not over-page. we need to go lower"),
    ("frank", "fair point, but what about the noise? we'll get paged for every little blip"),
    ("alice", "that's what the warning level is for. we're not removing thresholds, we're adding nuance"),
    ("carol", "so we need: critical threshold, warning threshold, and a paging condition that considers latency"),
    ("erin", "what's the proposal for critical error rate threshold?"),
    ("dave", "I propose 0.05 - that way we catch the incidents we were missing but still filter out genuine noise below 5%"),
    ("bob", "0.05 sounds right to me. that's the industry standard for SLO alerting"),
    ("carol", "agreed on 0.05 for critical error rate"),
    ("alice", "quick note: we should use >= 0.05, not > 0.05 — we want to catch exactly-at-threshold too"),
    ("frank", "why does the >= vs > distinction matter here?"),
    ("alice", "because > 0.05 would miss a service running at exactly 5.0% error rate. >= catches it. this is important for the boundary cases in our SLO contract"),
    ("dave", "good call. so: status = critical if error_rate >= 0.05"),
    ("bob", "now for budget threshold - what percentage budget consumed should trigger critical?"),
    ("carol", "I was going to propose 95% but thinking about it more, that's too late. by 95% we've almost no budget left"),
    ("alice", "exactly. 90% is the right threshold for critical budget. gives us time to react before we're completely burned out"),
    ("carol", "right, 95% is too late. I'm changing my proposal to 90%"),
    ("dave", "90% makes sense. critical if budget_consumed_pct > 90"),
    ("alice", "agreed. critical: error_rate >= 0.05 OR budget_consumed_pct > 90"),
    ("frank", "what about warning? we should have a lower threshold to catch degrading services before they hit critical"),
    ("erin", "what error rate for warning?"),
    ("bob", "I propose 0.02 - anything above 2% is worth watching"),
    ("niaj", "2% seems too aggressive, we'll get warning spam"),
    ("carol", "yeah I think 0.02 might be a bit tight. what about splitting the difference?"),
    ("alice", "let's look at our historical data... checking grafana"),
    ("alice", "ok so we have services that routinely hit 1.5% during normal load. we don't want to warn on those"),
    ("bob", "so what threshold won't catch normal noise?"),
    ("dave", "what if we go with 0.01? that's 1% error rate. our normal range is 0.1-0.8%, so 1% would catch real degradation"),
    ("alice", "0.01 looks right from the grafana data. our p99 of normal error rate is about 0.8%"),
    ("carol", "agreed: warning if error_rate >= 0.01"),
    ("bob", "so we dropped 0.02 in favor of 0.01 for warning? just confirming"),
    ("alice", "yes, settled on >= 0.01 for warning threshold after looking at the histogram"),
    ("erin", "and budget warning threshold?"),
    ("carol", "I'd say 80% - when we're 80% through the budget, we should be aware"),
    ("dave", "80% is a common industry standard"),
    ("alice", "hmm, but 80% might not give us enough warning time for some of our longer SLO windows"),
    ("niaj", "what about 75%? that's a quarter of budget remaining, gives more runway"),
    ("frank", "75% seems overly conservative. we'll warn too often"),
    ("alice", "I think 75% is right actually. it's a clear three-quarter mark and gives us real warning time"),
    ("bob", "the debate is 75 vs 80. I'll go with whatever alice decides"),
    ("alice", "75%. final answer. warning if budget_consumed_pct > 75"),
    ("carol", "so warning: error_rate >= 0.01 OR budget_consumed_pct > 75. confirmed"),
    ("dave", "now the paging condition. this is the key piece"),
    ("frank", "simple: page on all warnings. if it's worth calling warning it's worth paging"),
    ("alice", "no, that defeats the purpose. warning means 'watch this', not 'wake someone up at 3am'"),
    ("carol", "frank's suggestion would bring back the alert fatigue we're trying to fix"),
    ("frank", "ok ok, fair enough. not all warnings"),
    ("bob", "so when do we page on warning? we need some condition"),
    ("dave", "what if we page on warning only when latency is also elevated? that usually indicates a real user impact"),
    ("carol", "love that idea. latency threshold?"),
    ("alice", "p99 latency > 1000ms is our SLO boundary. if we're in warning AND p99 > 1000ms, that's a real problem"),
    ("erin", "makes sense. degraded error rate AND slow latency together = real incident"),
    ("dave", "so: should_page = True if critical, OR if warning AND latency_p99_ms > 1000"),
    ("alice", "exactly. note: > 1000, not >= 1000. latency at exactly 1000ms is within SLO"),
    ("bob", "that distinction matters for the 1001ms case"),
    ("carol", "so: latency_p99_ms > 1000 triggers page when in warning"),
    ("alice", "correct. paging on warning only if latency_p99_ms > 1000"),
    ("niaj", "let me make sure I have this right: critical pages always. warning only pages if latency > 1000ms"),
    ("alice", "yes exactly"),
    ("dave", "and ok status never pages"),
    ("alice", "correct"),
    ("frank", "what about the >= vs > on the error rate thresholds?"),
    ("alice", "both critical and warning use >= for error_rate. so: >= 0.05 for critical, >= 0.01 for warning"),
    ("carol", "budget thresholds use >: > 90% for critical, > 75% for warning"),
    ("alice", "right - for budget_consumed_pct we use > because the percentage is continuous and we want to trigger above those levels"),
    ("bob", "got it: error_rate uses >=, budget_consumed_pct uses >"),
    ("alice", "one more time to confirm the full policy:"),
    ("alice", "CRITICAL: error_rate >= 0.05 OR budget_consumed_pct > 90"),
    ("alice", "WARNING: error_rate >= 0.01 OR budget_consumed_pct > 75"),
    ("alice", "OK: everything else"),
    ("alice", "PAGE: always on critical; on warning only if latency_p99_ms > 1000"),
    ("dave", "that's the full agreed spec. captured it in the wiki too"),
    ("carol", "thumbsup from me"),
    ("bob", "approved"),
    ("erin", "approved"),
    ("niaj", "makes sense to me"),
    ("frank", "ok I was wrong about 0.10, this is better"),
    ("alice", "great. Agreed: critical if error_rate >= 0.05 or budget > 90%. Warning if error_rate >= 0.01 or budget > 75%. Page on critical always. Page on warning only if latency_p99 > 1000ms."),
    ("alice", "someone needs to update budget/monitor.py with these thresholds"),
    ("dave", "on it. will submit PR today"),
    ("bob", "I'll review the PR when it's up"),
    # Follow-up messages a day later
    ("dave", "PR up: github.com/acme/sre-tools/pull/47"),
    ("carol", "reviewing now"),
    ("alice", "deployment plan: merge after review, deploy Tuesday"),
    ("erin", "runbook updated to reference the new thresholds"),
    ("dave", "note: the old wrong thresholds (0.10 critical, 0.05 warning) are in git history - ignore those"),
    ("alice", "correct. the canonical thresholds are the ones we agreed here: 0.05 critical, 0.01 warning"),
    ("bob", "PR approved, merging"),
    ("alice", "deployed to staging, passing tests"),
    ("carol", "great. let's monitor for a week before prod"),
    ("niaj", "SLO review complete. closing the ticket"),
]

# #incidents channel - old postmortem with wrong threshold as a TRAP
INCIDENTS_THREAD = [
    ("alice", "[incident-2024-10-15] elevated error rates triggered page at 03:14 UTC"),
    ("alice", "at the time of the incident, the threshold was error_rate > 0.10 which triggered the alert"),
    ("bob", "the 0.10 threshold was too high - we didn't catch the degradation until it was severe"),
    ("carol", "investigation: error rate hit 0.10 at 03:14, paged on-call, resolved by 04:30"),
    ("dave", "postmortem action: review SLO thresholds (tracked in sre-oncall channel)"),
    ("alice", "note: do not use the 0.10 threshold from this incident as reference - it's the OLD wrong threshold"),
    ("frank", "right, the new thresholds are being decided in #sre-oncall"),
    ("bob", "this incident is what prompted the SLO review"),
]

# #alerts-dev - implementation discussion with partial/wrong code examples (TRAP)
ALERTS_DEV_THREAD = [
    ("victor", "starting implementation of the new check_budget function"),
    ("mallory", "quick question - for the error_rate threshold, is it > 0.05 or >= 0.05?"),
    ("victor", "I initially wrote > 0.05 but alice mentioned in sre-oncall it should be >= 0.05"),
    ("mallory", "ok got it. so error_rate >= 0.05 for critical"),
    ("victor", "and what's the warning threshold? I wrote 0.02 first"),
    ("mallory", "check #sre-oncall - they settled on 0.01 not 0.02 after looking at the histogram"),
    ("victor", "oh right, 0.01. I had the wrong number initially"),
    ("heidi", "heads up: don't use my earlier draft in the PR comments - I had the budget threshold at 95% which was wrong"),
    ("victor", "yeah carol corrected that - it's 90% not 95%"),
    ("mallory", "what about warning budget? I thought it was 80%"),
    ("victor", "alice changed it to 75% - again check #sre-oncall for the final answer"),
    ("heidi", "so many numbers floating around. the ONLY correct source is the final summary in #sre-oncall"),
    ("victor", "agreed. implementation note: use the final agreed spec from alice's summary in #sre-oncall"),
    ("mallory", "tests should be based on the agreed thresholds, not any of the proposed ones"),
    ("heidi", "correct. wrong proposals: 0.10, 0.02, 95%, 80%. agreed: 0.05, 0.01, 90%, 75%"),
]


def iso(dt):
    return dt.isoformat()


def main():
    msgs = []

    def add(ch, author, content, dt):
        msgs.append({"channel": ch, "author": author, "content": content, "timestamp": iso(dt)})

    # General noise across channels over 2 weeks
    t0 = START
    for day in range(14):
        ds = t0 + timedelta(days=day)
        for ch in ["general", "engineering", "product", "random"]:
            count = rng.randint(8, 15)
            for _ in range(count):
                author = rng.choice(USERS)
                content = rng.choice(FILLER[ch])
                add(ch, author, content, ds + timedelta(minutes=rng.randint(0, 9 * 60)))

    # incidents channel - old incident noise + trap thread
    for day in range(14):
        ds = t0 + timedelta(days=day)
        for _ in range(rng.randint(3, 7)):
            author = rng.choice(USERS + BOTS)
            content = rng.choice(FILLER["incidents"])
            add("incidents", author, content, ds + timedelta(minutes=rng.randint(0, 9 * 60)))

    # The old incident postmortem (trap - has old threshold values)
    incidents_base = START + timedelta(days=3, hours=10)
    for i, (author, content) in enumerate(INCIDENTS_THREAD):
        dt = incidents_base + timedelta(minutes=i * 12 + rng.randint(0, 5))
        add("incidents", author, content, dt)

    # alerts-dev noise + trap discussion
    for day in range(14):
        ds = t0 + timedelta(days=day)
        for _ in range(rng.randint(2, 5)):
            author = rng.choice(USERS)
            content = rng.choice(FILLER["alerts-dev"])
            add("alerts-dev", author, content, ds + timedelta(minutes=rng.randint(0, 9 * 60)))

    alerts_dev_base = START + timedelta(days=9, hours=14)
    for i, (author, content) in enumerate(ALERTS_DEV_THREAD):
        dt = alerts_dev_base + timedelta(minutes=i * 8 + rng.randint(0, 4))
        add("alerts-dev", author, content, dt)

    # The main SLO review in #sre-oncall - starts day 5
    sre_base = START + timedelta(days=5, hours=10)
    for i, (author, content) in enumerate(SRE_ONCALL_THREAD):
        # Space messages out realistically - some quick back-and-forth, some gaps
        gap = rng.randint(2, 20)
        if i > 0 and i % 10 == 0:
            gap = rng.randint(30, 90)  # occasional longer pauses
        sre_base = sre_base + timedelta(minutes=gap)
        add("sre-oncall", author, content, sre_base)

    # Additional #sre-oncall noise around the review (before and after)
    sre_noise = [
        ("alice", "reminder: weekly oncall sync at 3pm"),
        ("bob", "handoff notes: nothing active, staging is clean"),
        ("carol", "updated the deployment runbook"),
        ("dave", "silenced the noisy disk alert on prod-03 for 24h"),
        ("erin", "secondary oncall this week: erin"),
        ("frank", "oncall rotation updated for December"),
        ("alice", "escalation policy updated in pagerduty"),
        ("bob", "testing alert routing, ignore any test pages"),
        ("carol", "all services green on the dashboard"),
        ("dave", "capacity planning doc updated"),
        ("niaj", "grafana dashboard bookmark: internal.acme.io/grafana"),
        ("alice", "incident retrospective meeting Thursday 2pm"),
    ]
    for i, (author, content) in enumerate(sre_noise[:6]):
        dt = START + timedelta(days=2, hours=9) + timedelta(hours=i * 4)
        add("sre-oncall", author, content, dt)
    for i, (author, content) in enumerate(sre_noise[6:]):
        dt = START + timedelta(days=11, hours=9) + timedelta(hours=i * 3)
        add("sre-oncall", author, content, dt)

    # error-budget-reports channel (needs to exist for agent to post to it)
    ebr_base = START + timedelta(days=1, hours=9)
    for i, content in enumerate(FILLER["error-budget-reports"]):
        dt = ebr_base + timedelta(days=i * 2, hours=rng.randint(0, 4))
        add("error-budget-reports", "alice", content, dt)

    msgs.sort(key=lambda m: m["timestamp"])

    # Write as a real Slack export directory (data/slack-export/), ingested at container boot.
    # #error-budget-reports is seeded above so it exists for the agent's notification post.
    import sys, pathlib
    _here = pathlib.Path(__file__).resolve()
    for _anc in _here.parents:
        if (_anc / "selfcontained" / "base" / "slack_export_writer.py").exists():
            sys.path.insert(0, str(_anc / "selfcontained" / "base")); break
    from slack_export_writer import write_export
    out_dir = str(_here.parent / "slack-export")
    stats = write_export(msgs, out_dir, workspace="acme")
    print(f"wrote real Slack export to {out_dir} ({stats})")
    from collections import Counter
    print("per-channel:", dict(Counter(m["channel"] for m in msgs)))


if __name__ == "__main__":
    main()
