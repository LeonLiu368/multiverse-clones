"""Point-in-time reconstruction of issue/PR state from GitHub timeline events.

Given an item + its timeline + a cutoff T, compute the state as it was AT T:
state (open/closed/merged), labels, title. Used by `hydrate apply --as-of`.

Fidelity note: GitHub's API doesn't expose comment-body edit history, so comment
*text* is always the latest version even when placed at T. State, labels, and
title ARE reconstructable from timeline events and are handled here.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def parse_cutoff(value: str) -> datetime:
    """Accept an ISO-8601 timestamp. (Commit->timestamp resolution lives in apply.)"""
    dt = _ts(value)
    if dt is None:
        raise ValueError(f"bad timestamp: {value}")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def included_at(item: dict, cutoff: datetime) -> bool:
    """True if the issue/PR existed at T (created on or before the cutoff)."""
    created = _ts(item.get("created_at"))
    return created is not None and created <= cutoff


def state_at(item: dict, timeline: list[dict], cutoff: datetime, *, is_pr: bool = False) -> dict:
    """Reconstruct {state, labels, title, merged} as of `cutoff`.

    Replays timeline events with created_at <= cutoff:
      - closed/reopened  -> state
      - merged           -> merged (PRs)
      - labeled/unlabeled-> label set (replayed from empty)
      - renamed          -> title (walked back from current for events AFTER T)
    """
    events = sorted(
        [e for e in (timeline or []) if _ts(e.get("created_at"))],
        key=lambda e: _ts(e["created_at"]),
    )

    state = "open"
    merged = False
    labels: set[str] = set()
    # labels present at creation: GitHub emits a 'labeled' event at create time,
    # so replaying from empty is faithful for the common case.
    for e in events:
        when = _ts(e["created_at"])
        if when > cutoff:
            continue
        ev = e.get("event")
        if ev == "closed":
            state = "closed"
        elif ev == "reopened":
            state = "open"
        elif ev == "merged":
            merged = True
            state = "closed"
        elif ev == "labeled":
            name = (e.get("label") or {}).get("name")
            if name:
                labels.add(name)
        elif ev == "unlabeled":
            name = (e.get("label") or {}).get("name")
            labels.discard(name)

    # Title at T: start from current, walk back through renames that happened AFTER T.
    title = item.get("title")
    for e in sorted(events, key=lambda e: _ts(e["created_at"]), reverse=True):
        if e.get("event") == "renamed" and _ts(e["created_at"]) > cutoff:
            frm = (e.get("rename") or {}).get("from")
            if frm is not None:
                title = frm

    return {"state": state, "merged": merged, "labels": sorted(labels), "title": title}
