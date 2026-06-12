#!/usr/bin/env python3
"""Import a real Slack workspace export into the gateway's SQLite store.

Handles the standard Slack export directory shape:

    export/
      channels.json          # [{id,name,created,creator,is_archived,is_general,topic,purpose,members}]
      users.json             # [{id,name,real_name,deleted,is_bot,tz,profile:{display_name,email,...}}]
      <channel-name>/
        YYYY-MM-DD.json      # array of message objects (ts, user, text, thread_ts, reactions, ...)

Robust to BOTH variants seen in the wild:
  - a COMPLETE export (channels.json + users.json present), and
  - an ANONYMIZED export with those top-level files stripped — channels are then derived from the
    subdirectory names and users from the messages' `user` + embedded `user_profile`.

Fidelity preserved: timestamps (Slack `ts` strings kept as-is), thread_ts, reply_count, reactions,
subtypes, display names. Non-Slack-shaped ids (`PERSON_*`, `UANON*`, raw `U9N4V476D`) are normalized
to deterministic `U…`/`C…` ids via a stable map so off-the-shelf Slack tooling doesn't choke.

Also accepts our legacy `scraped.json` ({"messages":[{channel,author,content,timestamp}]}) so older
tasks keep working.

Usage:
    python3 import_export.py --export-dir <dir> [--channels a,b,c] [--start YYYY-MM-DD] [--end ...]
    python3 import_export.py --scraped <scraped.json>          # legacy
Env: SLACK_DB (default /tmp/slack.db).
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from slackgw.store import Store  # noqa: E402

SKIP_SUBTYPES = {
    "channel_join", "channel_leave", "channel_purpose", "channel_name", "channel_topic",
    "channel_archive", "channel_unarchive", "channel_convert_to_private", "pinned_item",
    "bot_add", "bot_remove",
}
SLACK_CID = re.compile(r"^C[A-Z0-9]{6,}$")
SLACK_UID = re.compile(r"^[UWB][A-Z0-9]{6,}$")
DAY_FILE = re.compile(r"\d{4}-\d{2}-\d{2}\.json$")


class IdMap:
    """Deterministic, stable normalization of arbitrary source ids to Slack-shaped ids."""

    def __init__(self) -> None:
        self.chan: dict[str, str] = {}
        self.user: dict[str, str] = {}

    def _norm(self, raw: str, prefix: str, table: dict[str, str], valid: re.Pattern) -> str:
        raw = (raw or "").strip()
        if not raw:
            raw = f"{prefix}_unknown"
        if raw in table:
            return table[raw]
        if valid.match(raw):
            table[raw] = raw
            return raw
        h = hashlib.sha1(raw.encode()).hexdigest()[:9].upper()
        sid = f"{prefix}{h}"
        table[raw] = sid
        return sid

    def cid(self, raw: str) -> str:
        return self._norm(raw, "C", self.chan, SLACK_CID)

    def uid(self, raw: str) -> str:
        return self._norm(raw, "U", self.user, SLACK_UID)


def _ts_to_epoch(ts: str) -> float:
    try:
        return float(ts)
    except (TypeError, ValueError):
        return 0.0


def _date_in_range(fname: str, start: str | None, end: str | None) -> bool:
    base = os.path.basename(fname)[:-5]  # strip .json -> YYYY-MM-DD
    if start and base < start:
        return False
    if end and base > end:
        return False
    return True


def _load_json(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def import_export(store: Store, export_dir: str, channels: list[str] | None,
                  start: str | None, end: str | None) -> dict:
    ids = IdMap()
    team_id = ""

    # --- channels (authoritative file if present) ------------------------------------------
    chan_meta: dict[str, dict] = {}  # channel name -> metadata
    cj = os.path.join(export_dir, "channels.json")
    if os.path.isfile(cj):
        for c in _load_json(cj):
            chan_meta[c["name"]] = c

    # --- users (authoritative file if present) ---------------------------------------------
    user_seen: set[str] = set()
    uj = os.path.join(export_dir, "users.json")
    if os.path.isfile(uj):
        for u in _load_json(uj):
            prof = u.get("profile") or {}
            team_id = team_id or u.get("team_id", "")
            store.upsert_user(
                id=ids.uid(u["id"]), name=u.get("name") or "",
                real_name=u.get("real_name") or prof.get("real_name") or "",
                display_name=prof.get("display_name") or u.get("name") or "",
                email=prof.get("email") or "", is_bot=int(bool(u.get("is_bot"))),
                deleted=int(bool(u.get("deleted"))), tz=u.get("tz") or "",
            )
            user_seen.add(u["id"])

    # --- discover channel directories ------------------------------------------------------
    wanted = set(channels) if channels else None
    dirs = [d for d in sorted(os.listdir(export_dir))
            if os.path.isdir(os.path.join(export_dir, d)) and (wanted is None or d in wanted)]

    n_msgs = 0
    for cname in dirs:
        cdir = os.path.join(export_dir, cname)
        meta = chan_meta.get(cname, {})
        cid = ids.cid(meta.get("id") or cname)
        topic = (meta.get("topic") or {}).get("value", "") if isinstance(meta.get("topic"), dict) else ""
        purpose = (meta.get("purpose") or {}).get("value", "") if isinstance(meta.get("purpose"), dict) else ""
        store.upsert_channel(
            id=cid, name=cname, created=int(meta.get("created") or 0),
            creator=ids.uid(meta["creator"]) if meta.get("creator") else "",
            is_archived=int(bool(meta.get("is_archived"))),
            is_general=int(bool(meta.get("is_general"))), topic=topic, purpose=purpose,
        )

        for fpath in sorted(glob.glob(os.path.join(cdir, "*.json"))):
            if not DAY_FILE.search(os.path.basename(fpath)):
                continue  # only YYYY-MM-DD.json are day files (skip stray json)
            if not _date_in_range(fpath, start, end):
                continue
            try:
                day = _load_json(fpath)
            except Exception:
                continue
            if not isinstance(day, list):
                continue
            for m in day:
                if m.get("type") not in (None, "message"):
                    continue
                if m.get("subtype") in SKIP_SUBTYPES:
                    continue
                text = (m.get("text") or "").strip()
                if not text and not m.get("subtype"):
                    continue
                raw_user = m.get("user") or m.get("bot_id") or "unknown"
                uid = ids.uid(raw_user)
                # derive a user record from embedded profile if not in users.json
                if raw_user not in user_seen:
                    prof = m.get("user_profile") or {}
                    store.upsert_user(
                        id=uid, name=prof.get("name") or m.get("username") or uid,
                        real_name=prof.get("real_name") or "",
                        display_name=prof.get("display_name") or prof.get("name") or "",
                        email="", is_bot=int(bool(m.get("bot_id"))), deleted=0, tz="",
                    )
                    user_seen.add(raw_user)
                thread_ts = m.get("thread_ts") or ""
                store.insert_message(
                    ts=m["ts"], channel_id=cid, user=uid, text=text,
                    subtype=m.get("subtype") or "", thread_ts=thread_ts,
                    reply_count=int(m.get("reply_count") or 0),
                    edited_ts=(m.get("edited") or {}).get("ts", "") if isinstance(m.get("edited"), dict) else "",
                    reactions=json.dumps(m.get("reactions"), ensure_ascii=False) if m.get("reactions") else "",
                )
                n_msgs += 1

    store.set_meta("team_id", team_id or "T0000000000")
    store.set_meta("team_name", os.environ.get("SLACK_TEAM", "workspace"))
    store.commit()
    return {"channels": len(dirs), "messages": n_msgs, "users": len(user_seen)}


def import_scraped(store: Store, path: str) -> dict:
    """Legacy: our {channel,author,content,timestamp} format."""
    ids = IdMap()
    data = _load_json(path)
    messages = data["messages"] if isinstance(data, dict) else data
    chans: dict[str, str] = {}
    n = 0
    for m in messages:
        content = (m.get("content") or m.get("text") or "").strip()
        if not content:
            continue
        cname = (m.get("channel") or "general").strip().lstrip("#")
        cid = chans.get(cname)
        if cid is None:
            cid = ids.cid(cname)
            chans[cname] = cid
            store.upsert_channel(id=cid, name=cname)
        author = (m.get("author") or (m.get("user_profile") or {}).get("display_name")
                  or m.get("user") or "anonymous")
        uid = ids.uid(author)
        store.upsert_user(id=uid, name=re.sub(r"\W+", "", author.lower())[:20] or "anon",
                          display_name=author, real_name=author)
        raw = m.get("timestamp") or m.get("ts")
        ts = _normalize_ts_to_slack(raw)
        store.insert_message(ts=ts, channel_id=cid, user=uid, text=content)
        n += 1
    store.set_meta("team_id", "T0000000000")
    store.set_meta("team_name", os.environ.get("SLACK_TEAM", "workspace"))
    store.commit()
    return {"channels": len(chans), "messages": n, "users": 0}


def _normalize_ts_to_slack(raw) -> str:
    """Accept a Slack ts string, a Unix float, or ISO 8601; return a Slack `ts` string.
    Falls back to 'now' on anything unparseable rather than crashing the whole import."""
    if raw is None:
        return f"{datetime.now(timezone.utc).timestamp():.6f}"
    s = str(raw)
    try:
        return f"{float(s):.6f}"
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return f"{dt.timestamp():.6f}"
    except ValueError:
        return f"{datetime.now(timezone.utc).timestamp():.6f}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Import a Slack export (or legacy scraped.json) into SQLite.")
    ap.add_argument("--export-dir", help="path to a Slack export directory")
    ap.add_argument("--scraped", help="path to a legacy scraped.json")
    ap.add_argument("--channels", help="comma-separated channel names to include")
    ap.add_argument("--start", help="earliest day YYYY-MM-DD (inclusive)")
    ap.add_argument("--end", help="latest day YYYY-MM-DD (inclusive)")
    ap.add_argument("--db", help="SQLite path (default $SLACK_DB or /tmp/slack.db)")
    args = ap.parse_args()

    store = Store(args.db)
    if args.export_dir:
        chans = [c.strip() for c in args.channels.split(",")] if args.channels else None
        stats = import_export(store, args.export_dir, chans, args.start, args.end)
    elif args.scraped:
        stats = import_scraped(store, args.scraped)
    else:
        ap.error("one of --export-dir or --scraped is required")
        return
    print(f"IMPORT_OK channels={stats['channels']} messages={stats['messages']} users={stats['users']}")


if __name__ == "__main__":
    main()
