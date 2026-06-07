#!/usr/bin/env python3
"""Seed a Mattermost workspace for the incident-response task.

Adapted from APEX-SWE's embedded uploader but generalized:
  - one channel per distinct `channel` field in the seed file
  - `author` is a plain string (e.g. "alice"), not a Discord object
  - original timestamps preserved; no git-commit-time filtering

Seed file (/tmp/scraped.json): {"messages": [{"channel","author","content","timestamp"}, ...]}
Contract created: admin admin@demo.local / AdminUser123!, team `test-demo`, seeded channels.
"""
import json
import sys
import time
import uuid
from datetime import datetime

import psycopg2
import requests

BASE = "http://localhost:8065"
ADMIN = {
    "email": "admin@demo.local",
    "username": "admin",
    "password": "AdminUser123!",
    "first_name": "Admin",
    "last_name": "User",
}
TEAM = {"name": "test-demo", "display_name": "Test Demo", "type": "O"}


def api_setup():
    """Create the admin user + team over REST (idempotent). Returns (token, team_id)."""
    try:
        requests.post(f"{BASE}/api/v4/users", json=ADMIN, timeout=10)
    except Exception:
        pass
    r = requests.post(
        f"{BASE}/api/v4/users/login",
        json={"login_id": ADMIN["email"], "password": ADMIN["password"]},
        timeout=10,
    )
    token = r.headers.get("Token")
    if not token:
        print("❌ could not log in as admin", file=sys.stderr)
        sys.exit(1)
    headers = {"Authorization": f"Bearer {token}"}
    requests.post(f"{BASE}/api/v4/teams", json=TEAM, headers=headers, timeout=10)
    tr = requests.get(f"{BASE}/api/v4/teams/name/{TEAM['name']}", headers=headers, timeout=10)
    team_id = tr.json().get("id")
    print(f"✅ admin + team ready (token {token[:8]}…, team {team_id})")
    return token, team_id


def main():
    no_messages = "--no-messages" in sys.argv
    token, _ = api_setup()
    if no_messages:
        return
    headers = {"Authorization": f"Bearer {token}"}

    data = json.load(open("/tmp/scraped.json"))
    messages = data["messages"] if isinstance(data, dict) else data
    print(f"ℹ️ seeding {len(messages)} messages")

    conn = psycopg2.connect(
        host="localhost", port=5433, database="mattermost",
        user="mattermost", password="mattermost",
    )
    cur = conn.cursor()
    cur.execute("SELECT id FROM teams WHERE name = %s", (TEAM["name"],))
    team_id = cur.fetchone()[0]
    cur.execute("SELECT id FROM users WHERE email = %s", (ADMIN["email"],))
    admin_id = cur.fetchone()[0]
    now = int(time.time() * 1000)

    chan_cache = {}
    user_cache = {}

    def get_channel(name):
        # Create channels through the REST API (not raw SQL) so Mattermost's caches /
        # channel-list index know about them — they then show up in `mmctl channel list`.
        # Posts are still inserted via SQL below to preserve original timestamps.
        name = (name or "general").strip().lower()
        if name in chan_cache:
            return chan_cache[name]
        body = {"team_id": team_id, "name": name, "display_name": name.capitalize(), "type": "O"}
        r = requests.post(f"{BASE}/api/v4/channels", json=body, headers=headers, timeout=10)
        if r.status_code in (200, 201):
            cid = r.json()["id"]
        else:
            # Already exists (or race) — look it up by name.
            g = requests.get(
                f"{BASE}/api/v4/teams/{team_id}/channels/name/{name}", headers=headers, timeout=10
            )
            cid = g.json().get("id")
        chan_cache[name] = cid
        return cid

    def get_user(author):
        # Create users through the REST API (not raw SQL). REST users are fully
        # app-managed, so later admin operations on them — deactivate/activate, role
        # changes, channel membership — behave correctly (raw-SQL users do not: the app
        # caches bypass them). Posts below are still inserted via SQL to keep timestamps.
        uname = (author or "system").strip().lower().replace(" ", "").replace("@", "").replace("#", "")[:20]
        if not uname or not uname[0].isalpha():
            uname = "anonymous"
        if uname in user_cache:
            return user_cache[uname]
        display = author or uname
        body = {"email": f"{uname}@demo.local", "username": uname, "password": "Password123!",
                "nickname": display, "first_name": display.split()[0]}
        r = requests.post(f"{BASE}/api/v4/users", json=body, headers=headers, timeout=10)
        if r.status_code in (200, 201):
            uid = r.json()["id"]
        else:
            g = requests.get(f"{BASE}/api/v4/users/username/{uname}", headers=headers, timeout=10)
            uid = g.json().get("id")
        requests.post(f"{BASE}/api/v4/teams/{team_id}/members",
                      json={"team_id": team_id, "user_id": uid}, headers=headers, timeout=10)
        user_cache[uname] = uid
        return uid

    def ensure_member(cid, uid):
        cur.execute(
            """INSERT INTO channelmembers
               (channelid,userid,roles,lastviewedat,msgcount,mentioncount,notifyprops,
                lastupdateat,schemeuser,schemeadmin,schemeguest,mentioncountroot,
                msgcountroot,urgentmentioncount)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (channelid,userid) DO NOTHING""",
            (cid, uid, "channel_user", now, 0, 0, "{}", now, True, False, False, 0, 0, 0),
        )

    uploaded = 0
    for m in messages:
        content = (m.get("content") or "").strip()
        if not content:
            continue
        cid = get_channel(m.get("channel"))
        uid = get_user(m.get("author"))
        ensure_member(cid, uid)
        ts = m.get("timestamp")
        if ts:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            tsm = int(dt.timestamp() * 1000)
        else:
            tsm = now
        pid = uuid.uuid4().hex[:26]
        cur.execute(
            """INSERT INTO posts
               (id,createat,updateat,deleteat,userid,channelid,rootid,originalid,message,
                type,props,hashtags,filenames,fileids,hasreactions,editat,ispinned,remoteid)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::json,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s)""",
            (pid, tsm, now, 0, uid, cid, "", "", content, "", "{}", "", "[]", "[]",
             False, 0, False, ""),
        )
        uploaded += 1

    for cid in chan_cache.values():
        cur.execute(
            """UPDATE channels
               SET totalmsgcount = (SELECT COUNT(*) FROM posts WHERE channelid=%s),
                   lastpostat   = COALESCE((SELECT MAX(createat) FROM posts WHERE channelid=%s), 0)
               WHERE id=%s""",
            (cid, cid, cid),
        )

    conn.commit()
    conn.close()
    print(f"✅ SEED_OK channels={list(chan_cache.keys())} posts={uploaded}")


if __name__ == "__main__":
    main()
