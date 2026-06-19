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
                  start: str | None, end: str | None, overlay: bool = False) -> dict:
    # overlay=True layers this export ON TOP of an existing (prod) DB: channels/users that already
    # exist are preserved (INSERT OR IGNORE) so prod metadata isn't clobbered; only new entities and
    # all messages are added. Also leaves the prod team_id/team_name meta untouched.
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
                if_absent=overlay,
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
    imported_cids: list[str] = []
    for cname in dirs:
        cdir = os.path.join(export_dir, cname)
        meta = chan_meta.get(cname, {})
        cid = ids.cid(meta.get("id") or cname)
        imported_cids.append(cid)
        topic = (meta.get("topic") or {}).get("value", "") if isinstance(meta.get("topic"), dict) else ""
        purpose = (meta.get("purpose") or {}).get("value", "") if isinstance(meta.get("purpose"), dict) else ""
        store.upsert_channel(
            if_absent=overlay,
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
                        if_absent=overlay,
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

    if not overlay:  # full import: set workspace identity + member counts for all channels
        store.set_meta("team_id", team_id or "T0000000000")
        store.set_meta("team_name", os.environ.get("SLACK_TEAM", "workspace"))
        store.recount_members()
    else:  # overlay layers onto prod — keep prod identity; refresh counts only for touched channels
        store.recount_members(imported_cids)
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


# --------------------------------------------------------------------------- metadata materializer
def _iter_messages(export_dir: str):
    """Yield (channel_name, message) for every message file in the export."""
    for cname in sorted(os.listdir(export_dir)):
        cdir = os.path.join(export_dir, cname)
        if not os.path.isdir(cdir):
            continue
        for fpath in sorted(glob.glob(os.path.join(cdir, "*.json"))):
            if not DAY_FILE.search(os.path.basename(fpath)):
                continue
            try:
                day = _load_json(fpath)
            except Exception:
                continue
            if not isinstance(day, list):
                continue
            for m in day:
                yield cname, m


def _user_record(raw: str, prof: dict, team_id: str, is_bot: bool = False) -> dict:
    """A users.json entry keyed by the RAW source id (so it matches the message `user` field —
    a real export's users.json id == the id used in messages). Profile filled from `user_profile`
    where present; unrecoverable admin metadata (email, tz, flags) is left blank/false."""
    prof = prof or {}
    name = prof.get("name") or raw
    real = prof.get("real_name") or name
    disp = prof.get("display_name") or name
    return {
        "id": raw, "team_id": team_id, "name": name, "deleted": False, "real_name": real,
        "is_bot": is_bot, "is_app_user": False,
        "profile": {
            "real_name": real, "display_name": disp,
            "real_name_normalized": real, "display_name_normalized": disp,
            "first_name": prof.get("first_name") or "", "last_name": prof.get("last_name") or "",
            "avatar_hash": prof.get("avatar_hash") or "", "image_72": prof.get("image_72") or "",
            "email": "", "team": team_id,
        },
    }


# Deterministic synthetic-name pools — an anonymized export has no real names, so we assign stable,
# human-readable names keyed by the (content-hashed) user id. Same id -> same name across rebuilds.
FIRST_NAMES = [
    "Alex", "Jordan", "Sam", "Taylor", "Morgan", "Casey", "Riley", "Avery", "Quinn", "Reese",
    "Devon", "Harper", "Rowan", "Parker", "Emerson", "Skyler", "Cameron", "Drew", "Hayden", "Logan",
    "Maya", "Noah", "Priya", "Diego", "Wei", "Sofia", "Omar", "Hana", "Lucas", "Nadia",
    "Ivan", "Leila", "Kenji", "Amara", "Felix", "Yara", "Mateo", "Zoe", "Arjun", "Elena",
]
LAST_NAMES = [
    "Avila", "Brooks", "Chen", "Diaz", "Okafor", "Fischer", "Gupta", "Haddad", "Ibrahim", "Jensen",
    "Kowalski", "Lopez", "Martin", "Nakamura", "Owusu", "Petrov", "Quintero", "Reyes", "Singh", "Tan",
    "Ueda", "Vargas", "Walsh", "Xu", "Yousef", "Zhang", "Andersen", "Bianchi", "Costa", "Duval",
    "Eriksson", "Ferreira", "Goldberg", "Hassan", "Ivanov", "Johansson", "Kim", "Larsson", "Mensah", "Novak",
]


# Anonymizer placeholders that should be treated as "no real name" and replaced with a synthetic one:
# bracketed tokens like "[PERSON_NAME_6771]", and raw/anon id shapes (PERSON_*, UANON*, U0123ABC).
_ANON_NAME = re.compile(r"^\[.*\]$|person_name|^uanon|^person_|^[uwb][a-z0-9]{6,}$", re.I)


def _needs_synthetic(rec: dict, raw: str) -> bool:
    nm = (rec.get("real_name") or rec.get("name") or "").strip()
    return (not nm) or nm == raw or bool(_ANON_NAME.search(nm))


def _assign_synthetic_names(users: dict) -> None:
    """Give every user a stable, human-readable name derived from its id. Only synthesizes when no
    real name was recovered (missing, equal to the raw id, or an anonymizer placeholder), so genuine
    profiles are kept. Deterministic: iterate ids in sorted order and key the name pool on sha1(id)."""
    used: set[str] = set()
    for raw in sorted(users):
        rec = users[raw]
        if not _needs_synthetic(rec, raw):
            continue  # a real name was recovered — leave it
        h = int(hashlib.sha1(raw.encode()).hexdigest(), 16)
        first = FIRST_NAMES[h % len(FIRST_NAMES)]
        last = LAST_NAMES[(h // len(FIRST_NAMES)) % len(LAST_NAMES)]
        is_bot = bool(rec.get("is_bot"))
        real = f"{first} Bot" if is_bot else f"{first} {last}"
        base = f"{first.lower()}-bot" if is_bot else f"{first.lower()}.{last.lower()}"
        handle, n = base, 2
        while handle in used:
            handle, n = f"{base}{n}", n + 1
        used.add(handle)
        disp = real if is_bot else first
        rec["name"], rec["real_name"] = handle, real
        rec["profile"].update({
            "real_name": real, "display_name": disp,
            "real_name_normalized": real, "display_name_normalized": disp,
            "first_name": "" if is_bot else first, "last_name": "" if is_bot else last,
        })


def write_metadata(export_dir: str, *, force: bool = False, names: str = "raw") -> dict:
    """Materialize the two top-level files a complete Slack export has — `channels.json` and
    `users.json` — for an ANONYMIZED export that had them stripped. Everything is derived from the
    message stream (already present): users from each message's `user` + embedded `user_profile`
    (plus users seen only in reactions/replies), channels from the directory names + a scan for
    members/created/creator. Channel ids are synthesized (no channel id exists in the data); user
    ids are kept as-is so users.json stays consistent with the message `user` fields.
    """
    cj, uj = os.path.join(export_dir, "channels.json"), os.path.join(export_dir, "users.json")
    if not force:
        for p in (cj, uj):
            if os.path.exists(p):
                raise SystemExit(f"{p} already exists (use --force to overwrite)")

    users: dict[str, dict] = {}                       # raw id -> users.json record
    chans: dict[str, dict] = {}                       # name -> {created, creator, members:set}
    team_id = ""
    seen = 0
    for cname, m in _iter_messages(export_dir):
        if m.get("type") not in (None, "message"):
            continue
        team_id = team_id or m.get("team") or m.get("source_team") or ""
        ts = _ts_to_epoch(m.get("ts"))
        author = m.get("user") or m.get("bot_id")

        c = chans.setdefault(cname, {"created": None, "creator": None, "members": set()})
        if author:
            c["members"].add(author)
            if c["created"] is None or (ts and ts < c["created"]):
                c["created"], c["creator"] = ts, author
            if author not in users:
                users[author] = _user_record(author, m.get("user_profile"), team_id,
                                              is_bot=bool(m.get("bot_id")))
        # users that appear ONLY in reactions / thread replies (no message of their own)
        for r in (m.get("reactions") or []):
            for ru in (r.get("users") or []):
                users.setdefault(ru, _user_record(ru, {}, team_id))
        for ru in (m.get("reply_users") or []):
            users.setdefault(ru, _user_record(ru, {}, team_id))
        if m.get("parent_user_id"):
            users.setdefault(m["parent_user_id"], _user_record(m["parent_user_id"], {}, team_id))
        seen += 1

    team_id = team_id or "T0000000000"
    for u in users.values():                          # backfill team on records built pre-discovery
        u["team_id"] = team_id
        u["profile"]["team"] = team_id

    if names == "synthetic":
        _assign_synthetic_names(users)

    channels_out = []
    for name in sorted(chans):
        c = chans[name]
        channels_out.append({
            "id": "C" + hashlib.sha1(name.encode()).hexdigest()[:10].upper(),
            "name": name, "created": int(c["created"] or 0),
            "creator": c["creator"] or "", "is_archived": False, "is_general": name == "general",
            "members": sorted(c["members"]),
            "topic": {"value": "", "creator": "", "last_set": 0},
            "purpose": {"value": "", "creator": "", "last_set": 0},
        })

    with open(cj, "w", encoding="utf-8") as fh:
        json.dump(channels_out, fh, indent=2, ensure_ascii=False)
    with open(uj, "w", encoding="utf-8") as fh:
        json.dump(list(users.values()), fh, indent=2, ensure_ascii=False)
    return {"channels": len(channels_out), "users": len(users), "messages_scanned": seen,
            "team_id": team_id}


class PatchError(Exception):
    """A patch op could not be applied unambiguously — abort the whole patch (fail loud)."""


def _resolve_channel(store: Store, match: dict) -> dict:
    """Resolve a channel `match` to exactly one channel row, else raise PatchError.

    Accepts a human-stable `name` (the column the importer stores) or an explicit `id`. Channels
    are unique by name in a real export, so name resolves to one row; we still verify the count.
    """
    if match.get("id"):
        rows = store.conn.execute("SELECT * FROM channels WHERE id = ?", (match["id"],)).fetchall()
    elif match.get("name") is not None:
        rows = store.conn.execute(
            "SELECT * FROM channels WHERE name = ? COLLATE NOCASE", (match["name"],)).fetchall()
    else:
        raise PatchError(f"channel match needs 'name' or 'id': {match}")
    if len(rows) != 1:
        raise PatchError(f"PATCH_ERROR entity=channel match={match} matched={len(rows)}")
    return dict(rows[0])


def _resolve_user(store: Store, match: dict) -> dict:
    """Resolve a user `match` to exactly one user row, else raise PatchError. Matches the human
    `name` (handle) column or an explicit `id`."""
    if match.get("id"):
        rows = store.conn.execute("SELECT * FROM users WHERE id = ?", (match["id"],)).fetchall()
    elif match.get("name") is not None:
        rows = store.conn.execute(
            "SELECT * FROM users WHERE name = ? COLLATE NOCASE", (match["name"],)).fetchall()
    else:
        raise PatchError(f"user match needs 'name' or 'id': {match}")
    if len(rows) != 1:
        raise PatchError(f"PATCH_ERROR entity=user match={match} matched={len(rows)}")
    return dict(rows[0])


def _resolve_message(store: Store, match: dict) -> dict:
    """Resolve a message `match` to exactly one message row, else raise PatchError.

    The channel is resolved first (by name/id). Then the message is pinned by EITHER:
      - `ts` (the per-channel PK) -> exactly that row, or
      - `text_contains` -> must match EXACTLY one message in the channel.
    """
    if "channel" not in match:
        raise PatchError(f"message match needs 'channel': {match}")
    chan = _resolve_channel(store, {"name": match["channel"]} if not str(match["channel"]).startswith("C")
                            else {"id": match["channel"], "name": match["channel"]})
    cid = chan["id"]
    if match.get("ts") is not None:
        rows = store.conn.execute(
            "SELECT * FROM messages WHERE channel_id = ? AND ts = ?", (cid, match["ts"])).fetchall()
    elif match.get("text_contains") is not None:
        needle = match["text_contains"]
        esc = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = store.conn.execute(
            r"SELECT * FROM messages WHERE channel_id = ? AND text LIKE ? ESCAPE '\'",
            (cid, f"%{esc}%")).fetchall()
    else:
        raise PatchError(f"message match needs 'ts' or 'text_contains': {match}")
    if len(rows) != 1:
        raise PatchError(f"PATCH_ERROR entity=message match={match} matched={len(rows)}")
    return dict(rows[0])


def apply_patch(store: Store, path: str) -> dict:
    """Apply a per-task patch (a JSON op-list) that MUTATES the corpus: update/delete existing rows
    (and add via the overlay upsert path). Each op's `match` must resolve to EXACTLY one existing
    row for update/delete — otherwise we raise PatchError and abort the whole patch (fail loud).

    Format: {"version":1,"ops":[{"op":"update|delete|add","entity":"message|channel|user",
                                  "match":{...},"set":{...}}]}
    """
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    ops = doc.get("ops") if isinstance(doc, dict) else doc
    if not isinstance(ops, list):
        raise PatchError(f"patch must contain an 'ops' list, got {type(ops).__name__}")

    ids = IdMap()  # reused for name->id on `add` ops (same content-hash the importer uses)
    touched_channels: set[str] = set()
    n = 0
    for i, op in enumerate(ops):
        kind = op.get("op")
        entity = op.get("entity")
        match = op.get("match") or {}
        sets = op.get("set") or {}
        tag = f"op[{i}] {kind} {entity}"

        if entity not in ("message", "channel", "user"):
            raise PatchError(f"{tag}: entity must be message|channel|user")

        if kind == "add":
            # Reuse the existing overlay upsert path. Names resolve to the same ids the importer uses.
            if entity == "channel":
                store.upsert_channel(id=ids.cid(sets.get("id") or sets.get("name") or ""),
                                     **{k: v for k, v in sets.items() if k != "id"})
                touched_channels.add(ids.cid(sets.get("id") or sets.get("name") or ""))
            elif entity == "user":
                store.upsert_user(id=ids.uid(sets.get("id") or sets.get("name") or ""),
                                  **{k: v for k, v in sets.items() if k != "id"})
            else:  # message
                cid = ids.cid(sets.get("channel") or match.get("channel") or "")
                fields = {k: v for k, v in sets.items() if k != "channel"}
                store.insert_message(channel_id=cid, **fields)
                touched_channels.add(cid)
            n += 1
            continue

        if kind not in ("update", "delete"):
            raise PatchError(f"{tag}: op must be add|update|delete")

        if entity == "message":
            row = _resolve_message(store, match)
            if kind == "update":
                store.update_message(row["channel_id"], row["ts"], **sets)
            else:
                store.delete_message(row["channel_id"], row["ts"])
            touched_channels.add(row["channel_id"])
        elif entity == "channel":
            row = _resolve_channel(store, match)
            if kind == "update":
                store.update_channel(row["id"], **sets)
            else:
                store.delete_channel(row["id"])
            touched_channels.add(row["id"])
        else:  # user
            row = _resolve_user(store, match)
            if kind == "update":
                store.update_user(row["id"], **sets)
            else:
                store.delete_user(row["id"])
        n += 1

    # Member counts may have shifted (deleted messages, deleted channels, added messages).
    store.recount_members(sorted(touched_channels) or None)
    store.commit()
    return {"ops": n}


def main() -> None:
    ap = argparse.ArgumentParser(description="Import a Slack export (or legacy scraped.json) into SQLite.")
    ap.add_argument("--export-dir", help="path to a Slack export directory")
    ap.add_argument("--scraped", help="path to a legacy scraped.json")
    ap.add_argument("--channels", help="comma-separated channel names to include")
    ap.add_argument("--start", help="earliest day YYYY-MM-DD (inclusive)")
    ap.add_argument("--end", help="latest day YYYY-MM-DD (inclusive)")
    ap.add_argument("--db", help="SQLite path (default $SLACK_DB or /tmp/slack.db)")
    ap.add_argument("--write-metadata", action="store_true",
                    help="derive + write channels.json and users.json into --export-dir "
                         "(completes an anonymized export that had them stripped), then exit")
    ap.add_argument("--force", action="store_true", help="overwrite existing metadata files")
    ap.add_argument("--names", choices=["raw", "synthetic"], default="raw",
                    help="with --write-metadata: 'synthetic' assigns stable human-readable names to "
                         "users that have none (anonymized exports); 'raw' keeps the source id")
    ap.add_argument("--overlay", action="store_true",
                    help="layer this export on top of an existing (prod) DB: preserve existing "
                         "channel/user rows, add only new entities + all messages")
    ap.add_argument("--patch", help="path to a JSON op-list that MUTATES the corpus "
                    "(update/delete/add existing rows); applied to --db")
    args = ap.parse_args()

    if args.write_metadata:
        if not args.export_dir:
            ap.error("--write-metadata requires --export-dir")
        stats = write_metadata(args.export_dir, force=args.force, names=args.names)
        print(f"WROTE_METADATA channels={stats['channels']} users={stats['users']} "
              f"messages_scanned={stats['messages_scanned']} team_id={stats['team_id']}")
        return

    store = Store(args.db)
    if args.patch:
        # Mutating patch step (run AFTER any seed/overlay import). Fail loud on an unresolved match.
        try:
            stats = apply_patch(store, args.patch)
        except PatchError as e:
            print(str(e) if str(e).startswith("PATCH_ERROR") else f"PATCH_ERROR {e}", file=sys.stderr)
            sys.exit(2)
        print(f"PATCH_OK ops={stats['ops']}")
        return
    if args.export_dir:
        chans = [c.strip() for c in args.channels.split(",")] if args.channels else None
        stats = import_export(store, args.export_dir, chans, args.start, args.end, overlay=args.overlay)
    elif args.scraped:
        stats = import_scraped(store, args.scraped)
    else:
        ap.error("one of --export-dir or --scraped is required")
        return
    print(f"IMPORT_OK channels={stats['channels']} messages={stats['messages']} users={stats['users']}")


if __name__ == "__main__":
    main()
