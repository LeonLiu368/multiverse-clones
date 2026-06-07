#!/usr/bin/env python3
"""Deterministic generator for the Slack ``scraped.json`` seed (PR #12856).

The #paperless-oncall thread is the ONLY place the agreed fix for incident PNGX-531
is fully specified: index writes acquire the Tantivy file lock with a single attempt
and swallow the failure on contention, so docs are silently dropped. The team rules
out raising the timeout (PNGX-529) and serializing all indexing, and agrees on a
bounded retry loop with exponential backoff + full jitter in WriteBatch.__enter__
(src/documents/search/_backend.py), plus a deferred self-heal Celery task on lock
exhaustion (src/documents/tasks.py) so writes are never silently lost.

Heavy unrelated chatter (some mentioning lock/index/retry in innocuous contexts) makes
search.messages noisy. Run: python3 generate.py -> writes scraped.json next to this file.
"""
from __future__ import annotations

import json
import pathlib
import random
from datetime import datetime, timedelta, timezone

SEED = 20260612
BASE = datetime(2026, 6, 5, 9, 0, 0, tzinfo=timezone.utc)
rng = random.Random(SEED)
messages: list[dict] = []


def ts(day: int, hour: int, minute: int) -> str:
    return (BASE + timedelta(days=day, hours=hour - 9, minutes=minute)).isoformat()


def msg(channel: str, author: str, content: str, day: int, hour: int, minute: int) -> None:
    messages.append({"channel": channel, "author": author, "content": content,
                     "timestamp": ts(day, hour, minute)})


ONCALL = "paperless-oncall"
INCIDENT = [
    ("dana", "PNGX-531: under parallel consumption a chunk of docs never land in search. Logs are "
             "bursts of `SearchIndexLockError: Could not acquire index lock within 5s`. Error rate "
             "scales with the number of concurrent consumers.", 1, 9, 20),
    ("theo", "Quick fix: bump the lock timeout from 5s to 30s? (there's PNGX-529 for it)", 1, 9, 26),
    ("ravi", "Won't help under sustained contention — a single longer wait just blocks the consumer "
             "and still fails when the lock is genuinely held the whole window. And right now the "
             "failure is *swallowed*, so the write is dropped instead of retried.", 1, 9, 33),
    ("nina", "Could we serialize all indexing through one worker so there's never contention?", 1, 9, 40),
    ("ravi", "That kills consumption throughput — we WANT parallel consumers. The fix is to make the "
             "lock acquisition resilient, not to remove concurrency.", 1, 9, 46),
    ("ravi", "Located it: in `src/documents/search/_backend.py`, `WriteBatch.__enter__` does a single "
             "`self._lock.acquire(timeout=...)` and raises `SearchIndexLockError` on the first "
             "timeout. And `add_or_update()` / `remove()` let that error propagate, so under "
             "contention the document is just not indexed — silently.", 1, 10, 2),
    ("dana", "So two problems: no retry on the acquire, and no fallback when we do give up.", 1, 10, 6),
    ("ravi", "Right. Agreed fix, two parts:\n"
             "1) Retry the acquire with a bounded loop + exponential backoff and FULL jitter. "
             "Module constants in _backend.py: `_LOCK_TIMEOUT_SECONDS=10.0` (per-attempt), "
             "`_LOCK_RETRY_ATTEMPTS=4` (1 initial + 3 retries), `_LOCK_BACKOFF_BASE=1.0`, "
             "`_LOCK_BACKOFF_CAP=10.0`. Sleep = random.uniform(0, min(cap, base*2**attempt)) "
             "between attempts; raise SearchIndexLockError only after the last attempt.", 1, 10, 12),
    ("ravi", "2) Self-heal: if the retries are still exhausted, don't drop the write. In "
             "`add_or_update()` / `remove()`, catch SearchIndexLockError and schedule a deferred "
             "Celery task (`index_document` / `remove_document_from_index` in "
             "src/documents/tasks.py, countdown ~60s, autoretry_for=(SearchIndexLockError,)) and "
             "return normally. The deferred task re-does the write via batch_update() directly.", 1, 10, 18),
    ("theo", "Full jitter (uniform 0..backoff), not equal jitter — so parallel consumers don't "
             "re-collide in lockstep. 👍", 1, 10, 22),
    ("dana", "+1. Keep the per-attempt timeout at 10s and 4 total attempts. I'll link the PR on "
             "PNGX-531. Add tests that force the first few acquires to time out then succeed, and "
             "that lock exhaustion schedules the deferred task instead of raising to the caller.", 1, 10, 27),
    ("ravi", "On it — retry loop in __enter__, deferred tasks in tasks.py, and the constants so the "
             "behavior is tunable.", 1, 10, 33),
]
for author, content, d, h, m in INCIDENT:
    msg(ONCALL, author, content, d, h, m)

SEARCH_NOISE = [
    ("ravi", "reminder: the tantivy file lock is `.tantivy.lock` under the index dir.", 0, 10, 5),
    ("nina", "why do parallel re-OCR sweeps slow indexing so much?", 0, 11, 20),
    ("theo", "lock contention probably. we run 4 consumers at night.", 0, 11, 25),
    ("dana", "we should add a panel for index lock acquire failures.", 0, 15, 40),
]
for author, content, d, h, m in SEARCH_NOISE:
    msg("search", author, content, d, h, m)

CHANNELS = ["general", "random", "support", "ingestion", "search", "paperless-oncall"]
PEOPLE = ["dana", "ravi", "theo", "mia", "nina", "leo", "sam", "priya"]
FILLER = [
    "morning all ☕", "standup in 10", "who's reviewing the OCR backlog ticket?",
    "deploy window tonight 22:00 UTC, heads up", "lol the printer is down again",
    "can someone approve my PR when you get a sec", "lunch?", "the staging box is slow today",
    "anyone else seeing flaky CI on test_search_highlight?", "thumbnails for TIFF still missing, PNGX-425",
    "pagination bug on /api/documents/ is annoying, PNGX-409", "redis pool got tight during last night's import",
    "remember to rotate the consume-folder logs", "great work on the dark mode fix 🎉", "I'll be OOO friday",
    "docs site needs an update for the new API", "coffee machine on 3rd floor is fixed",
    "who owns the grafana dashboards now?", "celery beat schedule changed, FYI",
    "the index reindex job finished, all green", "should we stagger the nightly import and re-OCR sweep?",
    "support volume is high this morning", "merged the symlink consume fix branch to staging",
    "reminder: freeze starts thursday",
]


def filler_round(day: int, n: int) -> None:
    for _ in range(n):
        msg(rng.choice(CHANNELS), rng.choice(PEOPLE), rng.choice(FILLER),
            day, rng.randint(9, 18), rng.randint(0, 59))


filler_round(0, 140)
filler_round(1, 130)


def main() -> None:
    messages.sort(key=lambda m: m["timestamp"])
    out = pathlib.Path(__file__).with_name("scraped.json")
    out.write_text(json.dumps({"messages": messages}, indent=2) + "\n", encoding="utf-8")
    n_oncall = sum(1 for m in messages if m["channel"] == ONCALL)
    print(f"wrote {out} ({len(messages)} messages, {n_oncall} in #{ONCALL})")


if __name__ == "__main__":
    main()
