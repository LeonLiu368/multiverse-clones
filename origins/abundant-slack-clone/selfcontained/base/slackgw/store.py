"""SQLite-backed store for the Slack Web API gateway.

The gateway (`app.py`) reads/writes this store and serializes rows into Slack shapes. The store is
populated by `import_export.py` — from a real Slack export directory, or a legacy `scraped.json`
(`--scraped`). Stdlib only — no external deps.

Schema preserves real-export fidelity: channel topic/purpose, user display names, message threads
(`thread_ts`), reactions, and subtypes. IDs are Slack-shaped (`C…`/`U…`); the importer normalizes
any non-conforming source ids before they reach here.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any

DB_PATH = os.environ.get("SLACK_DB", "/tmp/slack.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY, name TEXT, created INTEGER DEFAULT 0, creator TEXT DEFAULT '',
    is_archived INTEGER DEFAULT 0, is_general INTEGER DEFAULT 0,
    topic TEXT DEFAULT '', purpose TEXT DEFAULT '', num_members INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, name TEXT, real_name TEXT DEFAULT '', display_name TEXT DEFAULT '',
    email TEXT DEFAULT '', is_bot INTEGER DEFAULT 0, deleted INTEGER DEFAULT 0, tz TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS messages (
    ts TEXT, channel_id TEXT, user TEXT, text TEXT DEFAULT '', subtype TEXT DEFAULT '',
    thread_ts TEXT DEFAULT '', reply_count INTEGER DEFAULT 0, edited_ts TEXT DEFAULT '',
    reactions TEXT DEFAULT '', PRIMARY KEY (channel_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_msg_chan_ts ON messages (channel_id, ts);
CREATE INDEX IF NOT EXISTS idx_msg_thread ON messages (thread_ts);
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    # check_same_thread=False because the Store is built at import time (a different thread than the
    # request handlers). This is safe ONLY because every gateway endpoint is `async def` and runs on
    # the single event-loop thread, so store calls are serialized. Do NOT convert a handler to sync
    # `def` (FastAPI would run it in a threadpool → concurrent use of this shared connection).
    conn = sqlite3.connect(path or DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


class Store:
    def __init__(self, path: str | None = None) -> None:
        self.conn = connect(path)
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        # Add num_members to channels for a DB built before the column existed (an older prebuilt
        # seed), then backfill it once. import_export populates num_members via recount_members(), so
        # this only does real work for a prebuilt DB that predates the column (then it's baked in).
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(channels)")}
        if "num_members" not in cols:
            self.conn.execute("ALTER TABLE channels ADD COLUMN num_members INTEGER DEFAULT 0")
        has_counts = self.conn.execute("SELECT 1 FROM channels WHERE num_members > 0 LIMIT 1").fetchone()
        has_msgs = self.conn.execute("SELECT 1 FROM messages LIMIT 1").fetchone()
        if has_msgs and not has_counts:
            self.recount_members()

    def recount_members(self, channel_ids: list[str] | None = None) -> None:
        """Recompute num_members (distinct posters) for every channel, or just `channel_ids`."""
        if channel_ids is not None:
            if not channel_ids:
                return
            ph = ",".join("?" * len(channel_ids))
            counts = self.conn.execute(
                f"SELECT channel_id, COUNT(DISTINCT user) AS n FROM messages "
                f"WHERE channel_id IN ({ph}) GROUP BY channel_id", list(channel_ids)).fetchall()
        else:
            counts = self.conn.execute(
                "SELECT channel_id, COUNT(DISTINCT user) AS n FROM messages GROUP BY channel_id").fetchall()
        self.conn.executemany("UPDATE channels SET num_members = ? WHERE id = ?",
                              [(r["n"], r["channel_id"]) for r in counts])

    # ------------------------------------------------------------------ meta / write (import)
    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    def get_meta(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def upsert_channel(self, *, if_absent: bool = False, **c: Any) -> None:
        # if_absent=True (overlay mode) preserves an existing prod row instead of replacing it.
        verb = "INSERT OR IGNORE" if if_absent else "INSERT OR REPLACE"
        self.conn.execute(
            f"""{verb} INTO channels
               (id,name,created,creator,is_archived,is_general,topic,purpose)
               VALUES (:id,:name,:created,:creator,:is_archived,:is_general,:topic,:purpose)""",
            {"created": 0, "creator": "", "is_archived": 0, "is_general": 0,
             "topic": "", "purpose": "", **c},
        )

    def upsert_user(self, *, if_absent: bool = False, **u: Any) -> None:
        verb = "INSERT OR IGNORE" if if_absent else "INSERT OR REPLACE"
        self.conn.execute(
            f"""{verb} INTO users
               (id,name,real_name,display_name,email,is_bot,deleted,tz)
               VALUES (:id,:name,:real_name,:display_name,:email,:is_bot,:deleted,:tz)""",
            {"real_name": "", "display_name": "", "email": "", "is_bot": 0,
             "deleted": 0, "tz": "", **u},
        )

    def insert_message(self, **m: Any) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO messages
               (ts,channel_id,user,text,subtype,thread_ts,reply_count,edited_ts,reactions)
               VALUES (:ts,:channel_id,:user,:text,:subtype,:thread_ts,:reply_count,:edited_ts,:reactions)""",
            {"text": "", "subtype": "", "thread_ts": "", "reply_count": 0,
             "edited_ts": "", "reactions": "", **m},
        )

    # ------------------------------------------------------------------ mutate (patch)
    # These do real UPDATE/DELETE ... WHERE on already-resolved PKs/ids. The patch driver
    # (import_export.apply_patch) is responsible for resolving human-stable match keys to exactly
    # one row BEFORE calling these, so they take ids/PKs and trust them. Column names mirror the
    # SCHEMA above. Callers commit() + recount_members() after a batch.
    _MSG_COLS = {"user", "text", "subtype", "thread_ts", "reply_count", "edited_ts", "reactions"}
    _CHAN_COLS = {"name", "created", "creator", "is_archived", "is_general", "topic", "purpose",
                  "num_members"}
    _USER_COLS = {"name", "real_name", "display_name", "email", "is_bot", "deleted", "tz"}

    @staticmethod
    def _set_clause(fields: dict, allowed: set) -> tuple[str, list]:
        cols = [k for k in fields if k in allowed]
        if not cols:
            raise ValueError(f"no updatable columns in {sorted(fields)} (allowed: {sorted(allowed)})")
        return ", ".join(f"{c} = ?" for c in cols), [fields[c] for c in cols]

    def update_message(self, channel_id: str, ts: str, **fields: Any) -> int:
        set_sql, vals = self._set_clause(fields, self._MSG_COLS)
        cur = self.conn.execute(
            f"UPDATE messages SET {set_sql} WHERE channel_id = ? AND ts = ?",
            [*vals, channel_id, ts])
        return cur.rowcount

    def delete_message(self, channel_id: str, ts: str) -> int:
        cur = self.conn.execute(
            "DELETE FROM messages WHERE channel_id = ? AND ts = ?", (channel_id, ts))
        return cur.rowcount

    def update_channel(self, id: str, **fields: Any) -> int:
        set_sql, vals = self._set_clause(fields, self._CHAN_COLS)
        cur = self.conn.execute(
            f"UPDATE channels SET {set_sql} WHERE id = ?", [*vals, id])
        return cur.rowcount

    def delete_channel(self, id: str) -> int:
        # Delete the channel and all its messages (a channel that no longer exists has no history).
        self.conn.execute("DELETE FROM messages WHERE channel_id = ?", (id,))
        cur = self.conn.execute("DELETE FROM channels WHERE id = ?", (id,))
        return cur.rowcount

    def update_user(self, id: str, **fields: Any) -> int:
        set_sql, vals = self._set_clause(fields, self._USER_COLS)
        cur = self.conn.execute(
            f"UPDATE users SET {set_sql} WHERE id = ?", [*vals, id])
        return cur.rowcount

    def delete_user(self, id: str) -> int:
        # Remove the user record. Messages authored by the user are left in place (Slack keeps the
        # history of a deactivated user); only the user row goes away.
        cur = self.conn.execute("DELETE FROM users WHERE id = ?", (id,))
        return cur.rowcount

    def commit(self) -> None:
        self.conn.commit()

    # ------------------------------------------------------------------ read (gateway)
    def list_channels(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM channels ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def channel_by_ref(self, ref: str) -> dict | None:
        ref = (ref or "").strip().lstrip("#")
        row = self.conn.execute("SELECT * FROM channels WHERE id = ?", (ref,)).fetchone()
        if not row:
            row = self.conn.execute(
                "SELECT * FROM channels WHERE name = ? COLLATE NOCASE", (ref,)
            ).fetchone()
        return dict(row) if row else None

    def list_users(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def user_by_ref(self, ref: str) -> dict | None:
        ref = (ref or "").strip()
        row = self.conn.execute("SELECT * FROM users WHERE id = ?", (ref,)).fetchone()
        if not row:
            row = self.conn.execute(
                "SELECT * FROM users WHERE name = ? COLLATE NOCASE", (ref,)
            ).fetchone()
        return dict(row) if row else None

    def history(self, channel_id: str, limit: int = 100) -> list[dict]:
        """Top-level messages newest-first (thread replies excluded, like Slack's conversations.history)."""
        rows = self.conn.execute(
            # ORDER BY ts (not CAST(ts AS REAL)) so the (channel_id, ts) index serves the sort —
            # ts is uniformly "<10-digit secs>.<usecs>", so text order == chronological order.
            # This keeps history O(limit) even on huge channels (2s -> ~0s at 2.4M messages).
            """SELECT * FROM messages
               WHERE channel_id = ? AND (thread_ts = '' OR thread_ts = ts)
               ORDER BY ts DESC LIMIT ?""",
            (channel_id, max(1, min(limit, 1000))),
        ).fetchall()
        return [dict(r) for r in rows]

    def replies(self, channel_id: str, thread_ts: str) -> list[dict]:
        """Thread parent + replies, oldest-first (Slack's conversations.replies)."""
        rows = self.conn.execute(
            """SELECT * FROM messages
               WHERE channel_id = ? AND (ts = ? OR thread_ts = ?)
               ORDER BY ts ASC""",
            (channel_id, thread_ts, thread_ts),
        ).fetchall()
        return [dict(r) for r in rows]

    def search(self, terms: list[str], limit: int = 100, *, channel_id: str | None = None,
               user_id: str | None = None, after: str | None = None,
               before: str | None = None) -> list[dict]:
        # `terms` are free-text substrings ANDed together (each must appear in the message text);
        # the keyword filters (channel/user/date) come from parsed Slack search operators. Returns
        # most-recent-first. An empty WHERE (no terms and no filters) returns nothing.
        where: list[str] = []
        args: list[Any] = []
        for t in terms or []:
            t = (t or "").strip()
            if not t:
                continue
            esc = t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where.append(r"text LIKE ? ESCAPE '\'")
            args.append(f"%{esc}%")
        if channel_id is not None:
            where.append("channel_id = ?")
            args.append(channel_id)
        if user_id is not None:
            where.append("user = ?")
            args.append(user_id)
        if after is not None:
            where.append("ts >= ?")
            args.append(after)
        if before is not None:
            where.append("ts <= ?")
            args.append(before)
        if not where:
            return []
        try:
            lim = int(limit)
        except (TypeError, ValueError):
            lim = 100
        args.append(max(1, min(lim, 1000)))
        rows = self.conn.execute(
            f"SELECT * FROM messages WHERE {' AND '.join(where)} ORDER BY ts DESC LIMIT ?", args
        ).fetchall()
        return [dict(r) for r in rows]

    def post_message(self, channel_id: str, user_id: str, text: str,
                     thread_ts: str = "") -> dict:
        # Nudge by a microsecond on the (channel_id, ts) PK so two posts in the same microsecond
        # don't overwrite each other (INSERT OR REPLACE would clobber).
        e = time.time()
        while True:
            ts = f"{e:.6f}"
            if not self.conn.execute(
                "SELECT 1 FROM messages WHERE channel_id = ? AND ts = ?", (channel_id, ts)
            ).fetchone():
                break
            e += 0.000001
        self.insert_message(ts=ts, channel_id=channel_id, user=user_id, text=text,
                            thread_ts=thread_ts)
        self.commit()
        return {"ts": ts, "channel_id": channel_id, "user": user_id, "text": text,
                "subtype": "", "thread_ts": thread_ts, "reactions": ""}
