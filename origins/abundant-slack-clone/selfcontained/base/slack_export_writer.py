"""Author-time helper: turn a flat message list into a real Slack-export directory.

Task `generate.py` scripts build a deterministic list of
``{channel, author, content, timestamp}`` dicts (the story arc + distractors + the planted fact).
This helper writes that list out in the **real Slack export format** — the same shape a genuine
workspace export produces — so the task seeds are authored and committed as real export data and
ingested by `import_export.py` at container boot:

    <out_dir>/
      channels.json
      users.json
      <channel-name>/<YYYY-MM-DD>.json   # array of Slack message objects

Deterministic: stable `C…`/`U…` ids (hashed from name), Slack `ts` strings derived from the
timestamps (collisions nudged by a microsecond), embedded `user_profile`, optional threads.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone


def _sid(prefix: str, name: str) -> str:
    return prefix + hashlib.sha1(name.encode()).hexdigest()[:10].upper()


def _epoch(ts) -> float:
    s = str(ts)
    try:
        return float(s)
    except ValueError:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def write_export(messages, out_dir, *, team_id="T0EXACME01", workspace="acme",
                 channel_purposes=None, bots=()):
    """Write `messages` as a real Slack export under `out_dir`. Returns a small stats dict.

    messages: list of {channel, author, content, timestamp[, thread_key]}. `thread_key` (optional)
              groups messages into a thread — the earliest message with a given key is the parent.
    channel_purposes: optional {channel_name: purpose_string}.
    bots: iterable of author names to mark as bot users.
    """
    channel_purposes = channel_purposes or {}
    bots = set(bots)

    authors = sorted({m["author"] for m in messages})
    channels = sorted({m["channel"] for m in messages})
    uid = {a: _sid("U", a) for a in authors}
    cid = {c: _sid("C", c) for c in channels}

    # Assign unique, ordered Slack ts strings.
    ordered = sorted(messages, key=lambda m: (_epoch(m["timestamp"]), m["channel"]))
    used: set[str] = set()
    for m in ordered:
        e = _epoch(m["timestamp"])
        ts = f"{e:.6f}"
        while ts in used:
            e += 0.000001
            ts = f"{e:.6f}"
        used.add(ts)
        m["_ts"] = ts

    # Resolve thread parents (earliest ts per thread_key).
    thread_parent: dict[str, str] = {}
    for m in sorted(ordered, key=lambda m: m["_ts"]):
        k = m.get("thread_key")
        if k and k not in thread_parent:
            thread_parent[k] = m["_ts"]

    os.makedirs(out_dir, exist_ok=True)

    # users.json
    users = []
    for a in authors:
        users.append({
            "id": uid[a], "team_id": team_id, "name": a, "real_name": a.capitalize(),
            "deleted": False, "is_bot": a in bots, "is_app_user": False,
            "profile": {"real_name": a.capitalize(), "display_name": a, "real_name_normalized": a.capitalize(),
                        "display_name_normalized": a, "email": f"{a}@{workspace}.example", "team": team_id},
        })
    with open(os.path.join(out_dir, "users.json"), "w", encoding="utf-8") as fh:
        json.dump(users, fh, indent=2)

    # channels.json
    chan_created = {c: int(min(_epoch(m["timestamp"]) for m in messages if m["channel"] == c))
                    for c in channels}
    chans = []
    for c in channels:
        chans.append({
            "id": cid[c], "name": c, "created": chan_created[c], "creator": uid[authors[0]],
            "is_archived": False, "is_general": c == "general",
            "members": [uid[a] for a in authors],
            "topic": {"value": "", "creator": "", "last_set": 0},
            "purpose": {"value": channel_purposes.get(c, f"#{c}"), "creator": uid[authors[0]],
                        "last_set": chan_created[c]},
        })
    with open(os.path.join(out_dir, "channels.json"), "w", encoding="utf-8") as fh:
        json.dump(chans, fh, indent=2)

    # per-channel/per-day message files
    by_chan_day: dict[tuple[str, str], list] = {}
    for m in ordered:
        day = datetime.fromtimestamp(float(m["_ts"]), tz=timezone.utc).strftime("%Y-%m-%d")
        obj = {
            "user": uid[m["author"]], "type": "message", "ts": m["_ts"],
            "client_msg_id": hashlib.sha1((m["author"] + m["_ts"]).encode()).hexdigest()[:18],
            "text": m["content"], "team": team_id,
            "user_profile": {"name": m["author"], "real_name": m["author"].capitalize(),
                             "display_name": m["author"], "team": team_id,
                             "is_restricted": False, "is_ultra_restricted": False},
        }
        if m.get("thread_key"):
            obj["thread_ts"] = thread_parent[m["thread_key"]]
        by_chan_day.setdefault((m["channel"], day), []).append(obj)

    for (c, day), objs in by_chan_day.items():
        cdir = os.path.join(out_dir, c)
        os.makedirs(cdir, exist_ok=True)
        objs.sort(key=lambda o: o["ts"])
        with open(os.path.join(cdir, f"{day}.json"), "w", encoding="utf-8") as fh:
            json.dump(objs, fh, indent=2)

    return {"channels": len(channels), "users": len(authors), "messages": len(ordered),
            "days": len({d for _, d in by_chan_day})}
