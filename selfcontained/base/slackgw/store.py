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
    topic TEXT DEFAULT '', purpose TEXT DEFAULT ''
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
        self.conn.commit()

    # ------------------------------------------------------------------ meta / write (import)
    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    def get_meta(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def upsert_channel(self, **c: Any) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO channels
               (id,name,created,creator,is_archived,is_general,topic,purpose)
               VALUES (:id,:name,:created,:creator,:is_archived,:is_general,:topic,:purpose)""",
            {"created": 0, "creator": "", "is_archived": 0, "is_general": 0,
             "topic": "", "purpose": "", **c},
        )

    def upsert_user(self, **u: Any) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO users
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

    def search(self, query: str, limit: int = 100) -> list[dict]:
        q = (query or "").strip()
        if not q:
            return []
        esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = self.conn.execute(
            r"""SELECT * FROM messages WHERE text LIKE ? ESCAPE '\'
                ORDER BY ts DESC LIMIT ?""",
            (f"%{esc}%", max(1, min(limit, 1000))),
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
