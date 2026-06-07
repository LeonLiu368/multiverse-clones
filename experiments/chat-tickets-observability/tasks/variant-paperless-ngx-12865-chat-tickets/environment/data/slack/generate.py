#!/usr/bin/env python3
"""Deterministic generator for the Slack ``scraped.json`` seed.

The slack-service sidecar seeds its Mattermost backend from this file
(``{"messages":[{channel,author,content,timestamp}, ...]}``) and serves it to the
agent through the Slack Web API (`slack` CLI / `slack-mcp`).

This is the ONLY place the root cause of incident PNGX-417 is fully localized. The
#paperless-oncall thread works past several wrong theories — a Redis lock, bumping
the Tantivy writer heap (PNGX-419), raising the lock timeout — before landing on the
real bug: ``WriteBatch.__exit__`` in ``src/documents/search/_backend.py`` disposes
the index writer only on the success path, so when ``commit()`` raises the writer
(and Tantivy's internal write lock) leaks and the next batch fails with ``LockBusy``.
The agreed fix is to move the writer disposal into a ``finally`` block.

Heavy unrelated chatter across other channels (some of it deliberately mentioning
"lock", "index", "writer", "commit" in innocuous contexts) makes ``search.messages``
return misleading hits, so the agent must READ the thread, not grep one keyword.

Run:  python3 generate.py   ->  writes scraped.json next to this file.
Deterministic: fixed SEED, fixed base timestamps. No third-party deps.
"""
from __future__ import annotations

import json
import pathlib
import random
from datetime import datetime, timedelta, timezone

SEED = 20260606
BASE = datetime(2026, 6, 5, 9, 0, 0, tzinfo=timezone.utc)  # day before + incident day

rng = random.Random(SEED)


def ts(day: int, hour: int, minute: int) -> str:
    return (BASE + timedelta(days=day, hours=hour - 9, minutes=minute)).isoformat()


messages: list[dict] = []


def msg(channel: str, author: str, content: str, day: int, hour: int, minute: int) -> None:
    messages.append({
        "channel": channel,
        "author": author,
        "content": content,
        "timestamp": ts(day, hour, minute),
    })


# ---------------------------------------------------------------------------
# 1) The load-bearing incident thread in #paperless-oncall (day 1 = incident day)
#    Read in order: symptom -> wrong theories -> the real root cause + agreed fix.
# ---------------------------------------------------------------------------
ONCALL = "paperless-oncall"
INCIDENT = [
    ("dana", "Paging on PNGX-417: documents ingested after ~02:08 aren't searchable. Indexer "
             "throughput flatlined. Worker log is a wall of `LockBusy: failed to acquire index "
             "writer lock`.", 1, 2, 12),
    ("theo", "Smells like a stuck Redis lock to me — celery beat was retrying a bulk import right "
             "before it started. Want me to flush the redis lock keys?", 1, 2, 18),
    ("ravi", "Checked — it's not Redis. The LockBusy is Tantivy's *index writer* lock, not a "
             "celery/redis lock. It only appears after a batch raises during commit.", 1, 2, 25),
    ("mia", "Confirming from support side: 3 customers, all uploads after ~02:10 invisible in "
            "search. Re-upload doesn't help.", 1, 2, 31),
    ("nina", "Could we just bump the writer heap? There's a ticket to raise it to 512MB "
             "(PNGX-419). Maybe the commit is OOM-ing and wedging the lock?", 1, 2, 40),
    ("ravi", "Heap isn't it — I reproduced locally with a tiny doc by forcing commit() to raise. "
             "The writer leaks regardless of heap. PNGX-419 is a separate optimisation; let's not "
             "conflate them.", 1, 2, 47),
    ("theo", "What about raising the writer lock acquisition timeout so the next batch waits it "
             "out?", 1, 2, 52),
    ("ravi", "That would just hang instead of erroring — the lock is never released, so a longer "
             "timeout still fails. We need to actually release the writer on the error path.", 1, 2, 58),
    ("ravi", "Found it. In `src/documents/search/_backend.py`, `WriteBatch.__exit__` only disposes "
             "the writer on the SUCCESS path: it commits, waits on merges, reloads, then deletes "
             "`self._raw_writer`. When `commit()` (or the merge/reload) raises, that delete is "
             "skipped, so the IndexWriter — and Tantivy's internal write lock — is never released. "
             "The very next batch then hits LockBusy.", 1, 3, 9),
    ("dana", "So the lock release is outside the finally. That's why a worker restart 'fixes' it "
             "until the next failing batch.", 1, 3, 12),
    ("ravi", "Exactly. Fix: move the writer disposal (`del self._raw_writer; self._raw_writer = "
             "None`) into a `finally` so it ALWAYS runs — on success and on exception — alongside "
             "releasing `self._lock`. An uncommitted writer is just discarded. Then a failed batch "
             "no longer wedges the index.", 1, 3, 17),
    ("theo", "Makes sense. The lock release for `self._lock` was already in a finally; the raw "
             "writer disposal just needs to join it.", 1, 3, 21),
    ("dana", "+1. Please keep the merge/commit logic in the try and only move the writer disposal "
             "into finally. I'll link the PR on PNGX-417.", 1, 3, 24),
    ("ravi", "On it. Will add a regression test that forces commit() to raise and asserts the next "
             "batch can still acquire a writer.", 1, 3, 30),
]
for author, content, d, h, m in INCIDENT:
    msg(ONCALL, author, content, d, h, m)

# A little earlier, benign #search chatter that mentions the same words (search noise)
SEARCH_NOISE = [
    ("ravi", "reminder: the search index lives under data/index; don't hand-edit the writer lock "
             "file.", 0, 10, 5),
    ("nina", "anyone know why a full reindex takes ~6 min now? commit step seems slower.", 0, 11, 20),
    ("ravi", "merge threads. it's fine. the writer commits then waits_merging_threads().", 0, 11, 25),
    ("theo", "TIL Tantivy keeps an internal lock per IndexWriter. neat.", 0, 14, 2),
    ("nina", "can we add a dashboard panel for index writer lock contention?", 0, 15, 40),
]
for author, content, d, h, m in SEARCH_NOISE:
    msg("search", author, content, d, h, m)

# ---------------------------------------------------------------------------
# 2) Deterministic filler chatter so search.messages is noisy and realistic.
# ---------------------------------------------------------------------------
CHANNELS = ["general", "random", "support", "ingestion", "search", "paperless-oncall"]
PEOPLE = ["dana", "ravi", "theo", "mia", "nina", "leo", "sam", "priya"]

FILLER = [
    "morning all ☕",
    "standup in 10",
    "who's reviewing the OCR backlog ticket?",
    "deploy window tonight 22:00 UTC, heads up",
    "lol the printer is down again",
    "can someone approve my PR when you get a sec",
    "lunch?",
    "the staging box is slow today",
    "anyone else seeing flaky CI on test_search_highlight?",
    "thumbnails for TIFF still missing, tracked in PNGX-425",
    "pagination bug on /api/documents/ is annoying, PNGX-409",
    "redis pool got tight during last night's bulk import",
    "remember to rotate the consume-folder logs",
    "great work on the dark mode fix 🎉",
    "I'll be OOO friday",
    "docs site needs an update for the new API",
    "coffee machine on 3rd floor is fixed",
    "who owns the grafana dashboards now?",
    "celery beat schedule changed, FYI",
    "the index reindex job finished, all green",
    "can we bump the writer heap next sprint? (PNGX-419)",
    "support volume is high this morning",
    "merged the symlink consume fix branch to staging",
    "reminder: freeze starts thursday",
]


def filler_round(day: int, n: int) -> None:
    for _ in range(n):
        ch = rng.choice(CHANNELS)
        who = rng.choice(PEOPLE)
        text = rng.choice(FILLER)
        h = rng.randint(9, 18)
        mn = rng.randint(0, 59)
        msg(ch, who, text, day, h, mn)


# ~270 filler messages spread across the two days
filler_round(0, 140)
filler_round(1, 130)

# ---------------------------------------------------------------------------
def main() -> None:
    messages.sort(key=lambda m: m["timestamp"])
    out = pathlib.Path(__file__).with_name("scraped.json")
    out.write_text(json.dumps({"messages": messages}, indent=2) + "\n", encoding="utf-8")
    n_oncall = sum(1 for m in messages if m["channel"] == ONCALL)
    print(f"wrote {out} ({len(messages)} messages, {n_oncall} in #{ONCALL})")


if __name__ == "__main__":
    main()
