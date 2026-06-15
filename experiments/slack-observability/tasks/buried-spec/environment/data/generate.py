"""
Generate realistic Mattermost seed data for the buried-spec token-bucket task.

Story: team did a load-test, found the rate limiter constants were too conservative,
debated new values in #platform-infra, went through several proposals/revisions,
and landed on CAPACITY=100, REFILL_RATE=10.0, INITIAL_TOKENS=100, OVERDRAFT_ALLOWANCE=0.

Key traps for the agent:
  - CAPACITY=200 was proposed and REJECTED
  - REFILL_RATE=15.0 was proposed, then CORRECTED to 10.0
  - OVERDRAFT_ALLOWANCE=10 was proposed and REJECTED (0 won)
  - #incidents mentions old values (50, 5.0) as context for what broke
  - Final agreed values only summarized once in #platform-infra

SEED=1337 for determinism.
Output: scraped.json in same directory.
"""
import json
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import Counter

SEED = 1337
rng = random.Random(SEED)

# ── usernames ──────────────────────────────────────────────────────────────────
USERS = [
    "alice",    # team lead / platform
    "bob",      # senior backend
    "carol",    # SRE
    "dave",     # backend engineer
    "frank",    # backend engineer (originally proposed wrong values)
    "grace",    # frontend
    "henry",    # product manager
    "iris",     # QA
    "jack",     # devops
    "kate",     # backend
    "liam",     # junior backend
    "mia",      # data eng
    "noah",     # security
    "olivia",   # infra
    "peter",    # CTO
    "quinn",    # engineering manager
]

# ── time helpers ───────────────────────────────────────────────────────────────
BASE_TS = datetime(2025, 5, 19, 9, 0, 0, tzinfo=timezone.utc)

def ts(days_offset: float, hour: int = 9, minute: int = 0, jitter_mins: int = 30) -> str:
    """Return an ISO timestamp string."""
    t = BASE_TS + timedelta(days=days_offset, hours=hour - 9, minutes=minute)
    t += timedelta(minutes=rng.randint(0, jitter_mins))
    return t.isoformat()

# ── message builder ────────────────────────────────────────────────────────────
messages: list[dict] = []

def msg(channel: str, author: str, content: str, day: float, hour: int = 10, minute: int = 0, jitter: int = 20):
    messages.append({
        "channel": channel,
        "author": author,
        "content": content,
        "timestamp": ts(day, hour, minute, jitter),
    })


# ══════════════════════════════════════════════════════════════════════════════
# #general  — everyday noise
# ══════════════════════════════════════════════════════════════════════════════
msg("general", "alice",   "good morning everyone", 0, 9, 0)
msg("general", "bob",     "morning! coffee machine is broken again btw", 0, 9, 5)
msg("general", "carol",   "lol not again. did anyone restart it?", 0, 9, 7)
msg("general", "grace",   "deployed the new dashboard to staging, let me know if you see anything weird", 0, 10, 0)
msg("general", "henry",   "nice! will check it after standup", 0, 10, 3)
msg("general", "iris",    "standup in 5?", 0, 9, 55)
msg("general", "alice",   "yep, joining now", 0, 9, 57)
msg("general", "dave",    "ping me when the dashboard is prod-ready @grace", 1, 10, 0)
msg("general", "grace",   "should be ready by Thursday, finishing the chart drilldowns", 1, 10, 5)
msg("general", "quinn",   "reminder: sprint retro Friday 3pm", 1, 14, 0)
msg("general", "bob",     "thumbsup", 1, 14, 2)
msg("general", "liam",    "is the wiki down? getting 504", 2, 11, 0)
msg("general", "jack",    "yeah restarting the wiki pod, 2min", 2, 11, 2)
msg("general", "jack",    "wiki is back up", 2, 11, 6)
msg("general", "liam",    "ty!", 2, 11, 7)
msg("general", "mia",     "anyone have context on why the nightly ETL keeps OOMing?", 3, 9, 15)
msg("general", "bob",     "yeah the new aggregation query is rough, I'll open a ticket", 3, 9, 20)
msg("general", "mia",     "appreciate it", 3, 9, 22)
msg("general", "henry",   "heads up: product demo with investors tomorrow 2pm. please no deploys during the window", 4, 9, 0)
msg("general", "alice",   "noted, freezing deploys 1:30-4pm tomorrow", 4, 9, 5)
msg("general", "carol",   "ack", 4, 9, 10)
msg("general", "olivia",  "ack", 4, 9, 11)
msg("general", "peter",   "thanks everyone, big one tomorrow", 4, 17, 0)
msg("general", "quinn",   "demo went great! investors loved the new UI. good job team", 5, 16, 0)
msg("general", "grace",   "congrats everyone", 5, 16, 3)
msg("general", "bob",     "nice work henry!", 5, 16, 5)
msg("general", "noah",    "quick reminder to rotate your API keys — security audit is next week", 6, 10, 0)
msg("general", "alice",   "will do", 6, 10, 5)
msg("general", "dave",    "on it", 6, 10, 7)
msg("general", "iris",    "QA env is fully upgraded to Python 3.12 now, let me know if anything breaks", 7, 11, 0)
msg("general", "liam",    "awesome, we were waiting on that", 7, 11, 5)
msg("general", "kate",    "merged! finally", 7, 11, 10)
msg("general", "quinn",   "happy Friday all, great sprint", 9, 17, 0)
msg("general", "alice",   "cheers", 9, 17, 2)
msg("general", "bob",     "cheers", 9, 17, 3)
msg("general", "mia",     "have a good weekend", 9, 17, 5)
msg("general", "jack",    "pagerduty is quiet, that's a win", 9, 17, 10)
msg("general", "carol",   "fingers crossed", 9, 17, 12)


# ══════════════════════════════════════════════════════════════════════════════
# #engineering — technical discussion noise
# ══════════════════════════════════════════════════════════════════════════════
msg("engineering", "dave",   "anyone else think we should move the config store off redis? latency spikes every GC", 0, 11, 0)
msg("engineering", "bob",    "we looked at this last quarter, the issue was write amplification not latency", 0, 11, 10)
msg("engineering", "kate",   "what about tiered storage? hot path stays redis, cold moves to postgres", 0, 11, 15)
msg("engineering", "alice",  "let's not over-engineer this yet. profile first", 0, 11, 20)
msg("engineering", "dave",   "fair point, will open a perf tracking issue", 0, 11, 22)
msg("engineering", "liam",   "PR open for the new healthcheck endpoint: /pull/418", 1, 9, 30)
msg("engineering", "kate",   "left some comments, mostly nits", 1, 10, 0)
msg("engineering", "liam",   "fixed, rebased", 1, 10, 30)
msg("engineering", "bob",    "LGTM, merging", 1, 11, 0)
msg("engineering", "alice",  "nice, that was a long time coming", 1, 11, 5)
msg("engineering", "frank",  "heads up: I'm touching the auth middleware this week, might have a short outage window fri night", 2, 9, 0)
msg("engineering", "carol",  "please post in #incidents if anything goes sideways", 2, 9, 5)
msg("engineering", "frank",  "will do", 2, 9, 6)
msg("engineering", "noah",   "reminder: no hardcoded secrets in PRs. use vault. found one in a draft PR today", 2, 14, 0)
msg("engineering", "liam",   "oops, was that mine? sorry", 2, 14, 3)
msg("engineering", "noah",   "no worries, already scrubbed. just a reminder for everyone", 2, 14, 5)
msg("engineering", "olivia", "infra note: we're migrating k8s node pools next Thursday, expect a rolling restart window 11pm-1am", 3, 10, 0)
msg("engineering", "carol",  "will this affect the rate limiter service?", 3, 10, 5)
msg("engineering", "olivia", "yes briefly, token buckets will reset on restart — that's expected", 3, 10, 8)
msg("engineering", "dave",   "we should document that in the runbook", 3, 10, 12)
msg("engineering", "olivia", "agreed, I'll add it", 3, 10, 15)
msg("engineering", "iris",   "regression suite green on staging after the auth middleware update", 6, 9, 0)
msg("engineering", "frank",  "great! moving to prod tonight", 6, 9, 5)
msg("engineering", "alice",  "ack, post in #general when it's done", 6, 9, 7)
msg("engineering", "quinn",  "velocity metrics for this sprint look really good, team", 8, 17, 0)
msg("engineering", "bob",    "carrying over only 2 tickets which is a record", 8, 17, 5)
msg("engineering", "kate",   "that rate limiter work took forever but it's finally done", 8, 17, 8)
msg("engineering", "alice",  "yes! shoutout to everyone who debugged the load test", 8, 17, 10)


# ══════════════════════════════════════════════════════════════════════════════
# #product — PM/roadmap noise
# ══════════════════════════════════════════════════════════════════════════════
msg("product", "henry",  "Q3 roadmap draft is up in Notion, please comment by EOD Friday", 0, 9, 0)
msg("product", "grace",  "left some comments on the analytics section", 0, 11, 0)
msg("product", "henry",  "thanks, will review", 0, 11, 10)
msg("product", "alice",  "the API rate limiting story is marked as M1 — it's a dependency for the partner integrations", 0, 14, 0)
msg("product", "henry",  "yes, it's blocking partner onboarding. that's why it's high prio", 0, 14, 5)
msg("product", "quinn",  "partner A goes live in 3 weeks, we need the limiter sorted", 1, 9, 0)
msg("product", "alice",  "we're on it, running load tests this week", 1, 9, 5)
msg("product", "henry",  "what's the expected throughput for partner A?", 1, 9, 10)
msg("product", "alice",  "about 80-100 req/s at peak. current limiter caps at 50 which will cause issues", 1, 9, 15)
msg("product", "henry",  "we definitely need to fix that before launch", 1, 9, 20)
msg("product", "grace",  "design mocks for the new settings page are in Figma", 2, 10, 0)
msg("product", "henry",  "looks nice! a few feedback comments in Figma", 2, 14, 0)
msg("product", "grace",  "will revise this afternoon", 2, 14, 5)
msg("product", "henry",  "anyone have an ETA on the rate limiter config fix?", 5, 9, 0)
msg("product", "alice",  "we finalized the config last night, deploying tonight or tomorrow", 5, 9, 5)
msg("product", "henry",  "perfect. I'll update the partner timeline", 5, 9, 10)
msg("product", "quinn",  "great coordination everyone, partner launch is back on track", 5, 17, 0)
msg("product", "henry",  "thumbsup", 5, 17, 2)
msg("product", "alice",  "congrats team", 5, 17, 3)


# ══════════════════════════════════════════════════════════════════════════════
# #random — off-topic
# ══════════════════════════════════════════════════════════════════════════════
msg("random", "grace",  "anyone have a good Python book recommendation? trying to level up on async", 0, 12, 0)
msg("random", "bob",    "Fluent Python is solid. also the asyncio docs are actually pretty good these days", 0, 12, 5)
msg("random", "liam",   "+1 Fluent Python", 0, 12, 10)
msg("random", "kate",   "also check out Python Concurrency with asyncio by Matthew Fowler", 0, 12, 15)
msg("random", "grace",  "thanks all!", 0, 12, 20)
msg("random", "jack",   "anyone watching the match tonight?", 3, 17, 0)
msg("random", "mia",    "yes! can't wait", 3, 17, 5)
msg("random", "noah",   "not a sports person but let me know who wins lol", 3, 17, 10)
msg("random", "jack",   "haha", 3, 17, 12)
msg("random", "quinn",  "company offsite is booked for August. more details soon", 5, 10, 0)
msg("random", "alice",  "exciting!!", 5, 10, 5)
msg("random", "bob",    "please not another escape room", 5, 10, 8)
msg("random", "quinn",  "lol no promises", 5, 10, 10)
msg("random", "iris",   "anyone need pet sitting the week of the offsite? I have two cats", 7, 9, 0)
msg("random", "grace",  "I can help! DM me", 7, 9, 5)
msg("random", "peter",  "excited for the offsite, it's been too long since we've all been in one room", 8, 9, 0)
msg("random", "alice",  "agreed! it's going to be great", 8, 9, 5)


# ══════════════════════════════════════════════════════════════════════════════
# #backend — backend team chatter
# ══════════════════════════════════════════════════════════════════════════════
msg("backend", "dave",   "token bucket PR is up for review: /pull/421", 0, 9, 30)
msg("backend", "frank",  "will look today", 0, 9, 35)
msg("backend", "bob",    "left comments on the _refill method", 0, 11, 0)
msg("backend", "dave",   "good catches, updated", 0, 11, 30)
msg("backend", "kate",   "the consume method signature looks clean. what's the plan for the constants?", 0, 14, 0)
msg("backend", "dave",   "that's the open question, we're doing load tests to figure out the right values", 0, 14, 5)
msg("backend", "kate",   "makes sense. LGTM on the logic itself", 0, 14, 10)
msg("backend", "frank",  "LGTM too, merging after alice approves", 0, 15, 0)
msg("backend", "alice",  "approved! nice clean implementation", 0, 15, 30)
msg("backend", "frank",  "merged", 0, 16, 0)
msg("backend", "liam",   "question: should TokenBucket be a singleton or instantiated per client?", 1, 10, 0)
msg("backend", "bob",    "per-client for now. global singleton gets complicated with multi-tenant", 1, 10, 5)
msg("backend", "liam",   "makes sense, thanks", 1, 10, 8)
msg("backend", "carol",  "load test harness is set up in /tests/load. run with locust -f locustfile.py", 2, 9, 0)
msg("backend", "frank",  "nice, running it now", 2, 9, 5)
msg("backend", "frank",  "first run results in #platform-infra", 2, 11, 0)
msg("backend", "dave",   "ooh exciting, heading over there", 2, 11, 2)
msg("backend", "bob",    "same, this has been blocking us for too long", 2, 11, 5)
msg("backend", "kate",   "after the constants are settled, we should add proper integration tests", 4, 10, 0)
msg("backend", "alice",  "agreed, want to take that on?", 4, 10, 5)
msg("backend", "kate",   "sure, will start after the config ships", 4, 10, 8)
msg("backend", "liam",   "should middleware.py have its own config override or always use bucket defaults?", 5, 9, 0)
msg("backend", "alice",  "always bucket defaults for now. keep it simple", 5, 9, 5)
msg("backend", "liam",   "ack", 5, 9, 7)


# ══════════════════════════════════════════════════════════════════════════════
# #incidents — TRAP: mentions old values as context, NOT the agreed new values
# ══════════════════════════════════════════════════════════════════════════════
msg("incidents", "carol",  "P2 — elevated 429s on the API gateway. rate limiter rejecting legitimate traffic", 2, 11, 30)
msg("incidents", "carol",  "current config: CAPACITY=50, REFILL_RATE=5.0. partners hitting the ceiling", 2, 11, 32)
msg("incidents", "alice",  "on it, looking at the metrics now", 2, 11, 33)
msg("incidents", "frank",  "yeah we're seeing 40% of partner A's requests getting rejected", 2, 11, 35)
msg("incidents", "olivia", "grafana: token exhaustion graph shows the bucket draining in under 2s", 2, 11, 37)
msg("incidents", "alice",  "CAPACITY=50 is way too low for partner A's traffic pattern. they burst to 80 req/s on job start", 2, 11, 40)
msg("incidents", "bob",    "so every job start triggers a 429 storm. that's the pattern", 2, 11, 42)
msg("incidents", "carol",  "mitigation: temporarily raising CAPACITY to 80 via feature flag to stop the bleeding", 2, 11, 44)
msg("incidents", "alice",  "ack, do it. this is an emergency patch, not the final config", 2, 11, 45)
msg("incidents", "carol",  "done. 429 rate dropping. still elevated but manageable", 2, 11, 50)
msg("incidents", "frank",  "partner A's success rate back to 95%, they're happy for now", 2, 11, 55)
msg("incidents", "alice",  "good. we need a proper fix though. REFILL_RATE=5.0 is also too slow", 2, 12, 0)
msg("incidents", "olivia", "REFILL_RATE=5.0 means full recovery from empty bucket takes 10 seconds. that's brutal", 2, 12, 2)
msg("incidents", "carol",  "incident resolved. root cause: CAPACITY=50, REFILL_RATE=5.0 are holdovers from the initial stub values", 2, 12, 10)
msg("incidents", "carol",  "action item: team to agree proper production config via load test. tracking in #platform-infra", 2, 12, 12)
msg("incidents", "alice",  "postmortem draft: docs/postmortem-2025-05-21.md — review before EOD", 2, 17, 0)
msg("incidents", "frank",  "reviewed, added my section", 2, 17, 30)
msg("incidents", "bob",    "LGTM on the postmortem", 2, 18, 0)
msg("incidents", "carol",  "postmortem published", 3, 9, 0)
msg("incidents", "quinn",  "thanks for the fast response everyone. reminder that incident response runbook is at /wiki/incidents", 3, 9, 30)
msg("incidents", "noah",   "side note: should we add rate limiter config to our security hardening checklist?", 3, 10, 0)
msg("incidents", "alice",  "yes, I'll add it after we finalize the config", 3, 10, 5)
msg("incidents", "carol",  "P3 — slight uptick in latency on /api/v2/events. investigating", 5, 14, 0)
msg("incidents", "olivia", "looks like a noisy neighbor in the k8s namespace, not rate limiting", 5, 14, 10)
msg("incidents", "carol",  "confirmed, throttling the noisy workload now", 5, 14, 15)
msg("incidents", "carol",  "resolved. unrelated to rate limiter", 5, 14, 30)
msg("incidents", "carol",  "all systems nominal for the week. monitoring looks healthy after the config deploy", 8, 9, 0)
msg("incidents", "alice",  "thumbsup great. new config seems stable", 8, 9, 5)
msg("incidents", "olivia", "grafana shows token exhaustion is gone. CAPACITY=100 and the new REFILL_RATE doing their job", 8, 9, 10)
msg("incidents", "frank",  "nice to see the incident count drop", 8, 9, 15)
msg("incidents", "carol",  "yep. reminder: the OLD values (CAPACITY=50, REFILL_RATE=5.0) are what caused the P2 last week", 8, 10, 0)
msg("incidents", "carol",  "anyone asks why we changed them — see the postmortem and #platform-infra discussion", 8, 10, 2)
msg("incidents", "iris",   "test traffic from staging is properly isolated now, won't affect prod rate limiter", 6, 11, 0)
msg("incidents", "jack",   "good, staging was bleeding into prod metrics last week", 6, 11, 5)
msg("incidents", "carol",  "that's been fixed in the ingress rules", 6, 11, 10)
msg("incidents", "noah",   "also updated the on-call runbook with the new rate limiter config values for reference", 7, 10, 0)
msg("incidents", "alice",  "perfect, thanks noah", 7, 10, 5)
msg("incidents", "carol",  "PagerDuty quiet for 48h", 9, 9, 0)
msg("incidents", "jack",   "fingers crossed", 9, 9, 2)
msg("incidents", "olivia", "let's keep it that way", 9, 9, 5)


# ══════════════════════════════════════════════════════════════════════════════
# #platform-infra — THE authoritative channel (~150 messages)
# Story arc: load test report -> proposals -> debate -> corrections -> final decision
# ══════════════════════════════════════════════════════════════════════════════

# --- Phase 1: Load test report (day 2) ---
msg("platform-infra", "frank",  "load test results are in. sharing the key findings here", 2, 11, 5)
msg("platform-infra", "frank",  "setup: locust, 50 workers, ramp from 10 to 200 req/s over 5 min, then sustained 100 req/s for 10 min", 2, 11, 6)
msg("platform-infra", "frank",  "current config: CAPACITY=50, REFILL_RATE=5.0 — this is what's in bucket.py right now", 2, 11, 7)
msg("platform-infra", "frank",  "results: at sustained 100 req/s, rejection rate hits 62%. way too high", 2, 11, 8)
msg("platform-infra", "frank",  "bucket drains in under 0.5s at peak. refill at 5 tokens/s means clients wait ~9s for recovery", 2, 11, 9)
msg("platform-infra", "alice",  "that explains the partner A incident. those values are placeholder dev defaults, not prod-ready", 2, 11, 15)
msg("platform-infra", "bob",    "yeah whoever set 50/5.0 must have just put in round numbers. not based on any real traffic data", 2, 11, 20)
msg("platform-infra", "dave",   "so what do we actually need? partner A is ~80-100 req/s peak. partner B is lower, ~40 req/s", 2, 11, 25)
msg("platform-infra", "carol",  "we want the limiter to handle normal partner traffic without any rejections under steady load", 2, 11, 30)
msg("platform-infra", "alice",  "and we want burst tolerance — partners send a batch at job start then steady-state", 2, 11, 35)
msg("platform-infra", "olivia", "so CAPACITY needs to absorb a burst and REFILL_RATE needs to be high enough to recover quickly", 2, 11, 40)

# --- Phase 2: Frank's initial (wrong) proposal (day 3) ---
msg("platform-infra", "frank",  "ok I ran some numbers. my proposal: CAPACITY=200, REFILL_RATE=15.0", 3, 9, 0)
msg("platform-infra", "frank",  "CAPACITY=200 gives a big burst buffer. REFILL_RATE=15.0 means recovery from empty in ~13s", 3, 9, 2)
msg("platform-infra", "frank",  "this should handle even the most aggressive partner traffic patterns", 3, 9, 5)
msg("platform-infra", "alice",  "hmm, CAPACITY=200 seems too high to me. that's 4x the current value", 3, 9, 15)
msg("platform-infra", "bob",    "agreed, CAPACITY=200 will let a misbehaving client hammer our downstream services", 3, 9, 20)
msg("platform-infra", "alice",  "downstream services are sized for ~120 req/s. if we allow 200-token bursts we could overwhelm them", 3, 9, 25)
msg("platform-infra", "dave",   "CAPACITY=200 is definitely too permissive. we need headroom above partner peaks but not 2x", 3, 9, 30)
msg("platform-infra", "kate",   "what about CAPACITY=120? covers partner A at peak with 20% headroom", 3, 9, 35)
msg("platform-infra", "frank",  "120 feels tight. what if we get a new partner with higher traffic?", 3, 9, 40)
msg("platform-infra", "alice",  "we'd update the config then. we shouldn't set it speculatively high now", 3, 9, 45)
msg("platform-infra", "dave",   "I'd say CAPACITY=100 is the right compromise. round number, covers partner A, keeps downstream safe", 3, 10, 0)
msg("platform-infra", "bob",    "100 makes sense to me. 2x the current value, covers real traffic, doesn't risk downstream", 3, 10, 5)
msg("platform-infra", "carol",  "yeah, 100 feels right. the incident showed 50 is too low, 200 is too high, 100 is the sweet spot", 3, 10, 10)
msg("platform-infra", "alice",  "ok, CAPACITY=200 is off the table. let's go with 100. any objections?", 3, 10, 15)
msg("platform-infra", "frank",  "fine with 100 if everyone agrees", 3, 10, 18)
msg("platform-infra", "olivia", "100 works for me", 3, 10, 20)
msg("platform-infra", "kate",   "thumbsup", 3, 10, 22)
msg("platform-infra", "liam",   "thumbsup", 3, 10, 23)
msg("platform-infra", "alice",  "CAPACITY=100 agreed.", 3, 10, 25)

# --- Phase 3: REFILL_RATE debate (day 3-4) ---
msg("platform-infra", "frank",  "now for REFILL_RATE. I still think 15.0 is right based on my load test analysis", 3, 14, 0)
msg("platform-infra", "frank",  "at REFILL_RATE=15.0, recovery from empty takes 6.7s. that's acceptable", 3, 14, 2)
msg("platform-infra", "alice",  "wait, recovery from empty at CAPACITY=100 and REFILL_RATE=15.0 is 100/15 = 6.67s. that is fast", 3, 14, 10)
msg("platform-infra", "bob",    "actually I'm not sure 15.0 is right for our traffic patterns. let me re-read the load test data", 3, 14, 15)
msg("platform-infra", "dave",   "the load test showed steady-state at 100 req/s. to sustain that without rejections we need REFILL_RATE >= 100? no that's not right", 3, 14, 20)
msg("platform-infra", "carol",  "REFILL_RATE doesn't need to match peak req/s. it's about recovery speed after a burst", 3, 14, 25)
msg("platform-infra", "alice",  "right. partners burst then drop to ~10 req/s steady. so we need to recover 100 tokens in a reasonable window", 3, 14, 30)
msg("platform-infra", "dave",   "at REFILL_RATE=15.0 that's 6.7s. at 10.0 it's 10s. both seem ok?", 3, 14, 35)
msg("platform-infra", "frank",  "I ran the numbers with 15.0 and it looked great in the simulation", 3, 14, 40)
msg("platform-infra", "alice",  "frank can you share the simulation? I want to double-check", 3, 14, 45)
msg("platform-infra", "frank",  "yeah, sharing now: /docs/load-test-simulation.xlsx", 3, 15, 0)

# Day 4 — frank corrects himself
msg("platform-infra", "alice",  "frank I looked at the simulation. I think there's an error in the input params", 4, 9, 0)
msg("platform-infra", "alice",  "you used p99 burst of 150 req/s but our actual p99 burst is ~100 req/s per the grafana data", 4, 9, 5)
msg("platform-infra", "frank",  "oh let me check", 4, 9, 10)
msg("platform-infra", "frank",  "...you're right. I was looking at the wrong percentile row. I used 150 as the input not 100", 4, 9, 20)
msg("platform-infra", "frank",  "correction: I misread the load test data. REFILL_RATE should be 10.0, not 15.0. Apologies.", 4, 9, 25)
msg("platform-infra", "alice",  "thanks for catching that frank. so REFILL_RATE=10.0?", 4, 9, 30)
msg("platform-infra", "bob",    "with the corrected inputs, 10.0 is what the simulation says?", 4, 9, 32)
msg("platform-infra", "frank",  "yes, re-ran with p99=100 req/s. REFILL_RATE=10.0 gives the best throughput/rejection tradeoff", 4, 9, 35)
msg("platform-infra", "dave",   "10.0 it is. at CAPACITY=100 that means a drained bucket recovers in 10s which is fine", 4, 9, 40)
msg("platform-infra", "carol",  "I'm happy with 10.0. REFILL_RATE=15.0 was a bit too generous anyway", 4, 9, 45)
msg("platform-infra", "alice",  "REFILL_RATE=10.0 agreed.", 4, 9, 50)
msg("platform-infra", "olivia", "thumbsup 10.0 makes sense", 4, 9, 52)
msg("platform-infra", "kate",   "ack", 4, 9, 54)

# --- Phase 4: INITIAL_TOKENS debate (day 4 afternoon) ---
msg("platform-infra", "dave",   "what about INITIAL_TOKENS? currently set to 50 (same as the old CAPACITY)", 4, 13, 0)
msg("platform-infra", "bob",    "should it just equal CAPACITY? start the bucket full seems obvious", 4, 13, 5)
msg("platform-infra", "alice",  "yeah, starting full means the first burst works without any warmup. I'd say INITIAL_TOKENS=100", 4, 13, 10)
msg("platform-infra", "liam",   "any reason NOT to start full?", 4, 13, 15)
msg("platform-infra", "carol",  "can't think of one for our use case. we're not worried about cold-start thundering herd here", 4, 13, 20)
msg("platform-infra", "frank",  "agreed, INITIAL_TOKENS=100 (=CAPACITY) makes sense. start full, let it drain naturally", 4, 13, 25)
msg("platform-infra", "alice",  "INITIAL_TOKENS=100 agreed.", 4, 13, 30)
msg("platform-infra", "kate",   "thumbsup", 4, 13, 32)

# --- Phase 5: OVERDRAFT_ALLOWANCE debate (day 4 late afternoon) ---
msg("platform-infra", "bob",    "last one: OVERDRAFT_ALLOWANCE. currently 5. should we keep it?", 4, 15, 0)
msg("platform-infra", "bob",    "overdraft means clients can go slightly over CAPACITY before getting rejected. 5 tokens feels like a safety valve", 4, 15, 2)
msg("platform-infra", "frank",  "I was thinking OVERDRAFT=10 actually. gives more burst tolerance", 4, 15, 5)
msg("platform-infra", "alice",  "I don't like overdraft for a production rate limiter. it means we can't reason about the exact burst ceiling", 4, 15, 10)
msg("platform-infra", "carol",  "from the SRE perspective, strict limits are easier to debug. if downstream sees >CAPACITY req/s, something is wrong", 4, 15, 15)
msg("platform-infra", "dave",   "OVERDRAFT=10 on top of CAPACITY=100 means up to 110 requests can burst. that's not what we told the downstream service owners", 4, 15, 20)
msg("platform-infra", "olivia", "SLAs to downstream assume CAPACITY is the hard ceiling. overdraft breaks that contract", 4, 15, 25)
msg("platform-infra", "frank",  "ok fair point. strict limiting it is", 4, 15, 30)
msg("platform-infra", "bob",    "hmm, I still kind of like the flexibility of overdraft=5. it's only 5 extra tokens", 4, 15, 35)
msg("platform-infra", "alice",  "no, I agree with carol and olivia. overdraft=0 for production. we document the CAPACITY clearly and hold to it", 4, 15, 40)
msg("platform-infra", "carol",  "vote: 0 or non-zero overdraft?", 4, 15, 45)
msg("platform-infra", "alice",  "0", 4, 15, 46)
msg("platform-infra", "dave",   "0", 4, 15, 47)
msg("platform-infra", "carol",  "0", 4, 15, 48)
msg("platform-infra", "olivia", "0", 4, 15, 49)
msg("platform-infra", "frank",  "0 (fine, convinced)", 4, 15, 50)
msg("platform-infra", "kate",   "0", 4, 15, 51)
msg("platform-infra", "bob",    "0 (I'll come around)", 4, 15, 52)
msg("platform-infra", "liam",   "0", 4, 15, 53)
msg("platform-infra", "alice",  "OVERDRAFT_ALLOWANCE=0 agreed.", 4, 15, 55)

# --- Phase 6: Final summary from alice (day 4 end of day) ---
msg("platform-infra", "alice",  "OK locking this: CAPACITY=100, REFILL_RATE=10.0, INITIAL_TOKENS=100, OVERDRAFT_ALLOWANCE=0. deploying tonight.", 4, 17, 0)
msg("platform-infra", "frank",  "ack thumbsup", 4, 17, 2)
msg("platform-infra", "bob",    "ack thumbsup", 4, 17, 3)
msg("platform-infra", "dave",   "ack, will update the PR", 4, 17, 5)
msg("platform-infra", "carol",  "monitoring is ready, I'll watch the dashboards tonight", 4, 17, 10)
msg("platform-infra", "olivia", "infra is ready on our end. green light", 4, 17, 15)
msg("platform-infra", "quinn",  "nice work everyone. this was a thorough process", 4, 17, 20)
msg("platform-infra", "peter",  "great job team. partner A launch is depending on this", 4, 17, 25)

# --- Phase 7: Post-deploy confirmations (day 5+) ---
msg("platform-infra", "carol",  "deploy complete. new config is live: CAPACITY=100, REFILL_RATE=10.0, INITIAL_TOKENS=100, OVERDRAFT=0", 5, 0, 30)
msg("platform-infra", "carol",  "rejection rate dropped from 62% to <1%. token exhaustion gone from dashboards", 5, 0, 35)
msg("platform-infra", "alice",  "excellent! great work everyone", 5, 8, 0)
msg("platform-infra", "frank",  "glad we caught the simulation error. 15.0 would have been slightly too aggressive", 5, 8, 5)
msg("platform-infra", "bob",    "and good call on CAPACITY=100 vs 200. downstream services haven't even noticed", 5, 8, 10)
msg("platform-infra", "dave",   "the new constants feel much more principled than the old placeholder values", 5, 8, 15)
msg("platform-infra", "olivia", "I'll document the final values in the runbook", 5, 9, 0)
msg("platform-infra", "alice",  "thanks olivia. also: please remember bucket.py still has the old placeholder values in the repo — PR is pending merge", 5, 9, 5)
msg("platform-infra", "dave",   "PR #423 is up, updating the constants to the agreed values", 5, 9, 10)
msg("platform-infra", "alice",  "linking for reference: CAPACITY=100, REFILL_RATE=10.0, INITIAL_TOKENS=100, OVERDRAFT_ALLOWANCE=0", 5, 9, 15)
msg("platform-infra", "kate",   "reviewed PR #423, LGTM", 5, 10, 0)
msg("platform-infra", "frank",  "LGTM on PR #423 too", 5, 10, 5)
msg("platform-infra", "alice",  "merging PR #423 now", 5, 10, 10)
msg("platform-infra", "alice",  "...wait, CI is running. will merge when green", 5, 10, 12)
msg("platform-infra", "liam",   "CI is being slow today, probably the flaky test in test_middleware.py again", 5, 10, 15)
msg("platform-infra", "alice",  "CI green. merged", 5, 10, 45)
msg("platform-infra", "dave",   "finally the repo matches prod", 5, 10, 48)
msg("platform-infra", "carol",  "metrics look stable after 12h. no incidents, rejection rate <0.5%", 6, 9, 0)
msg("platform-infra", "alice",  "thumbsup looks good. keeping a close eye for the next few days", 6, 9, 5)
msg("platform-infra", "frank",  "partner A is happy. they reported near-zero 429s since the config change", 6, 9, 10)
msg("platform-infra", "quinn",  "great outcome. I'm updating the post-mortem with the final resolution", 6, 10, 0)
msg("platform-infra", "olivia", "also updated the runbook with: CAPACITY=100, REFILL_RATE=10.0, INITIAL_TOKENS=100 (=CAPACITY), OVERDRAFT_ALLOWANCE=0 (strict)", 7, 9, 0)
msg("platform-infra", "carol",  "48h post-deploy: all green", 7, 9, 30)
msg("platform-infra", "alice",  "marking this incident thread closed. great job everyone on the load test and config work", 8, 9, 0)
msg("platform-infra", "peter",  "solid engineering process. the right answer took a few iterations but we got there", 8, 9, 10)
msg("platform-infra", "bob",    "lesson learned: don't leave placeholder values in prod configs lol", 8, 9, 15)
msg("platform-infra", "frank",  "and double-check your load test inputs before proposing values", 8, 9, 20)
msg("platform-infra", "alice",  "yes. for future reference: the agreed production constants are CAPACITY=100, REFILL_RATE=10.0, INITIAL_TOKENS=100, OVERDRAFT_ALLOWANCE=0", 8, 9, 25)


# ══════════════════════════════════════════════════════════════════════════════
# Write the messages out as a REAL Slack export directory (data/slack-export/).
# ══════════════════════════════════════════════════════════════════════════════
import sys

# Locate the shared export writer in selfcontained/base (walk up to the repo root).
_here = Path(__file__).resolve()
for _anc in _here.parents:
    if (_anc / "selfcontained" / "base" / "slack_export_writer.py").exists():
        sys.path.insert(0, str(_anc / "selfcontained" / "base"))
        break
from slack_export_writer import write_export  # noqa: E402

messages.sort(key=lambda m: m["timestamp"])
out_dir = _here.parent / "slack-export"   # environment/data/slack-export
stats = write_export(messages, str(out_dir), workspace="acme",
                     channel_purposes={"platform-infra": "Rate limiter + platform infra decisions"})

ch_counts = Counter(m["channel"] for m in messages)
print(f"Total messages: {len(messages)}")
for ch, count in sorted(ch_counts.items()):
    print(f"  #{ch}: {count}")
print(f"\nWrote real Slack export to {out_dir}  ({stats})")
