"""Capture abundant-slack-clone parity demos in-process against a seeded SQLite gateway.

Running this verifies the seed format is accepted (the slackgw Store loads it and serves reads)
AND captures the clone's ACTUAL Slack-Web-API envelopes for the dashboard comparison boxes. We seed
a realistic incident channel through the Store (the same import path conftest._seed uses), then
replicate the gateway's exact serializer call paths from `slackgw/app.py` (`_channel`, `_msg`,
`_parse_search`, the `{"ok":true,...}` envelope shaping) so `clone_output` is the true envelope the
gateway returns over HTTP. The `real_output` golden samples are authored from the real Slack Web API
docs (https://api.slack.com/web) so they share field SHAPE with the captured output.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

CLONE = Path(__file__).resolve().parents[2] / "clones" / "abundant-slack-clone"
BASE_SRC = CLONE / "selfcontained" / "base"
sys.path.insert(0, str(BASE_SRC))

# SLACK_DB must be set BEFORE importing store/app (Store() reads it at import time).
_TMP = tempfile.mkdtemp(prefix="slackviz-")
os.environ["SLACK_DB"] = os.path.join(_TMP, "seed.db")
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxp-acme-eval-0001")

from slackgw.store import Store  # noqa: E402
from slackgw import app as gw  # noqa: E402  (imports after SLACK_DB is set)

SEED_REL = "clones/abundant-slack-clone/tests/conftest.py (Store import path)"

# --- seeded workspace (a realistic incident thread in #general) ------------------------------------
TEAM_ID = "T0ACME0001"
TEAM_NAME = "acme"
CH_GENERAL = "C0000000001"
CH_INCIDENTS = "C0000000002"
U_ALICE = "U0000000A01"  # Alice Ant, SRE
U_BOB = "U0000000B02"    # Bob Bee, backend
U_CARA = "U0000000C03"   # Cara Cricket, on-call
INC_THREAD = "1700000200.000000"


def seed(db_path: str) -> Store:
    """Build a realistic incident workspace directly through the Store (the import path)."""
    st = Store(db_path)
    st.set_meta("team_id", TEAM_ID)
    st.set_meta("team_name", TEAM_NAME)
    st.upsert_channel(id=CH_GENERAL, name="general", is_general=1, creator=U_ALICE,
                      topic="company-wide", purpose="announcements")
    st.upsert_channel(id=CH_INCIDENTS, name="incidents", creator=U_CARA,
                      topic="live incident coordination", purpose="incident response")
    st.upsert_user(id=U_ALICE, name="alice", real_name="Alice Ant", email="alice@acme.dev")
    st.upsert_user(id=U_BOB, name="bob", real_name="Bob Bee", email="bob@acme.dev")
    st.upsert_user(id=U_CARA, name="cara", real_name="Cara Cricket", email="cara@acme.dev")

    # #general: a couple of standalone messages.
    st.insert_message(ts="1700000001.000000", channel_id=CH_GENERAL, user=U_ALICE,
                      text="welcome to the acme workspace :wave:")
    st.insert_message(ts="1700000050.000000", channel_id=CH_GENERAL, user=U_BOB,
                      text="reminder: deploy freeze starts friday")
    st.insert_message(ts="1700000120.000000", channel_id=CH_GENERAL, user=U_CARA,
                      text="heads up — seeing a lock_conflict spike on the payments DB")

    # #incidents: an incident thread (parent + replies) so history/search are rich.
    st.insert_message(ts=INC_THREAD, channel_id=CH_INCIDENTS, user=U_CARA,
                      text="INC-482: payments API 500s, root cause looks like a lock_conflict "
                           "on the orders table", reply_count=3)
    st.insert_message(ts="1700000201.000000", channel_id=CH_INCIDENTS, user=U_BOB,
                      text="confirmed — the retry loop holds the row lock across the RPC call",
                      thread_ts=INC_THREAD)
    st.insert_message(ts="1700000202.000000", channel_id=CH_INCIDENTS, user=U_ALICE,
                      text="mitigation: shortened the lock scope, error rate dropping",
                      thread_ts=INC_THREAD)
    st.insert_message(ts="1700000203.000000", channel_id=CH_INCIDENTS, user=U_CARA,
                      text="INC-482 resolved, lock_conflict cleared", thread_ts=INC_THREAD)
    st.recount_members()
    st.commit()
    return st


# --- capture helpers: replicate app.py's exact envelope shaping ------------------------------------
def _ok(**kw) -> dict:
    """The gateway's `ok(...)` envelope (JSONResponse({"ok": True, **kw}))."""
    return {"ok": True, **kw}


def conversations_list(store: Store) -> dict:
    # app.py conversations.list
    return _ok(channels=[gw._channel(c) for c in store.list_channels()],
               response_metadata={"next_cursor": ""})


def conversations_history(store: Store, channel_ref: str, limit: int = 100) -> dict:
    # app.py conversations.history
    c = store.channel_by_ref(channel_ref)
    if not c:
        return {"ok": False, "error": "channel_not_found"}
    latest = f"{time.time():.6f}"
    msgs = store.history(c["id"], limit, oldest="", latest=latest, inclusive=False)
    return _ok(messages=[gw._msg(m) for m in msgs], has_more=False,
               response_metadata={"next_cursor": ""})


def search_messages(store: Store, query: str, count: int = 100) -> dict:
    # app.py search.messages (operator parsing via app helpers)
    terms, ops = gw._parse_search(query)
    channel_id = None
    if ops.get("in"):
        c = store.channel_by_ref(gw._clean_ref(ops["in"]))
        channel_id = c["id"] if c else "\x00"
    user_id = None
    if ops.get("from"):
        u = store.user_by_ref(gw._clean_ref(ops["from"]))
        user_id = u["id"] if u else "\x00"
    after = gw._date_ts(ops["after"]) if ops.get("after") else None
    before = gw._date_ts(ops["before"], end=True) if ops.get("before") else None
    if ops.get("on"):
        after, before = gw._date_ts(ops["on"]), gw._date_ts(ops["on"], end=True)
    rows = store.search(terms, count, channel_id=channel_id, user_id=user_id,
                        after=after, before=before)
    matches = [gw._msg(m, channel=m["channel_id"]) for m in rows]
    n = len(matches)
    msg_paging = {"count": n, "total": n, "page": 1, "pages": 1}
    msg_pag = {"total_count": n, "page": 1, "per_page": count, "page_count": 1, "first": 1, "last": n}
    files = {"total": 0, "matches": [], "paging": {"count": 0, "total": 0, "page": 1, "pages": 0},
             "pagination": {"total_count": 0, "page": 1, "per_page": count,
                            "page_count": 0, "first": 0, "last": 0}}
    return _ok(query=query,
               messages={"total": n, "matches": matches, "paging": msg_paging, "pagination": msg_pag},
               files=files)


def chat_post_message(store: Store, channel_ref: str, text: str) -> dict:
    # app.py chat.postMessage
    c = store.channel_by_ref(channel_ref)
    if not c:
        return {"ok": False, "error": "channel_not_found"}
    m = store.post_message(c["id"], gw.BOT_USER_ID, text, "")
    return _ok(channel=c["id"], ts=m["ts"], message=gw._msg(m))


# --- ui adapters -----------------------------------------------------------------------------------
def _chat_messages(msgs: list[dict]) -> list[dict]:
    return [{"user": m.get("user"), "ts": m.get("ts"), "text": m.get("text", "")} for m in msgs]


def build() -> dict:
    store = seed(os.environ["SLACK_DB"])
    demos = []

    # ---- GET: conversations.list (list view) ----------------------------------
    clone_list = conversations_list(store)
    demos.append({
        "id": "list-channels",
        "title": "List channels",
        "method": "GET",
        "capability": "conversations.list",
        "seed_excerpt": {"channels": [
            {"id": CH_GENERAL, "name": "general"}, {"id": CH_INCIDENTS, "name": "incidents"}]},
        "ui": {"type": "list", "title": "Slack › Channels",
               "rows": [{"icon": "#", "title": c["name"], "sub": c["id"],
                         "tags": [c["num_members"]]} for c in clone_list["channels"]]},
        "agent": {"cli": "slack channels",
                  "mcp": {"tool": "channels_list", "args": {}}},
        "real_mapping": {
            "api": "GET /api/conversations.list",
            "mcp": "slack-mcp › channels_list",
            "doc": "https://api.slack.com/methods/conversations.list"},
        "clone_output": clone_list,
        "real_output": {"ok": True, "channels": [{
            "id": CH_GENERAL, "name": "general", "name_normalized": "general",
            "is_channel": True, "is_group": False, "is_im": False, "is_private": False,
            "is_archived": False, "is_general": True, "created": 1700000000,
            "creator": U_ALICE, "num_members": 3,
            "topic": {"value": "company-wide", "creator": "", "last_set": 0},
            "purpose": {"value": "announcements", "creator": "", "last_set": 0}}],
            "response_metadata": {"next_cursor": ""}},
    })

    # ---- GET: conversations.history (chat view) -------------------------------
    clone_hist = conversations_history(store, "incidents", limit=50)
    demos.append({
        "id": "channel-history",
        "title": "Read a channel's history",
        "method": "GET",
        "capability": "conversations.history",
        "seed_excerpt": {"channel": CH_INCIDENTS, "messages": [
            {"user": U_CARA, "ts": INC_THREAD, "text": "INC-482: payments API 500s ..."}]},
        "ui": {"type": "chat", "title": "Slack › #incidents",
               "messages": _chat_messages(clone_hist["messages"])},
        "agent": {"cli": "slack history incidents --limit 50",
                  "mcp": {"tool": "conversations_history",
                          "args": {"channel_id": CH_INCIDENTS, "limit": 50}}},
        "real_mapping": {
            "api": "GET /api/conversations.history",
            "mcp": "slack-mcp › conversations_history",
            "doc": "https://api.slack.com/methods/conversations.history"},
        "clone_output": clone_hist,
        "real_output": {"ok": True, "messages": [{
            "type": "message", "user": U_CARA,
            "text": "INC-482: payments API 500s, root cause looks like a lock_conflict on the orders table",
            "ts": INC_THREAD, "reply_count": 3}],
            "has_more": False, "response_metadata": {"next_cursor": ""}},
    })

    # ---- GET: search.messages with an operator query (chat view) --------------
    query = "in:general lock_conflict"
    clone_search = search_messages(store, query)
    smatches = clone_search["messages"]["matches"]
    demos.append({
        "id": "search-messages",
        "title": "Search messages (operator query)",
        "method": "GET",
        "capability": "search.messages",
        "seed_excerpt": {"query": query, "expect": [
            {"channel": CH_GENERAL, "text": "... lock_conflict spike on the payments DB"}]},
        "ui": {"type": "chat", "title": f"Slack › Search: {query}",
               "messages": _chat_messages(smatches)},
        "agent": {"cli": f'slack search "{query}"',
                  "mcp": {"tool": "conversations_search_messages",
                          "args": {"search_query": "lock_conflict", "filter_in_channel": "general"}}},
        "real_mapping": {
            "api": "GET /api/search.messages",
            "mcp": "slack-mcp › conversations_search_messages",
            "doc": "https://api.slack.com/methods/search.messages"},
        "clone_output": clone_search,
        "real_output": {"ok": True, "query": query, "messages": {
            "total": 1,
            "matches": [{"type": "message", "user": U_CARA,
                         "text": "heads up — seeing a lock_conflict spike on the payments DB",
                         "ts": "1700000120.000000", "channel": {"id": CH_GENERAL}}],
            "paging": {"count": 1, "total": 1, "page": 1, "pages": 1},
            "pagination": {"total_count": 1, "page": 1, "per_page": 100,
                           "page_count": 1, "first": 1, "last": 1}},
            "files": {"total": 0, "matches": [],
                      "paging": {"count": 0, "total": 0, "page": 1, "pages": 0},
                      "pagination": {"total_count": 0, "page": 1, "per_page": 100,
                                     "page_count": 0, "first": 0, "last": 0}}},
    })

    # ---- POST: chat.postMessage (write -> read round-trip) --------------------
    before_hist = conversations_history(store, "incidents", limit=50)
    before = _chat_messages(before_hist["messages"])
    posted = chat_post_message(store, "incidents",
                               "postmortem doc drafted for INC-482, review by EOD")
    after_hist = conversations_history(store, "incidents", limit=50)
    after = _chat_messages(after_hist["messages"])
    new_ts = posted["ts"]
    demos.append({
        "id": "post-message",
        "title": "Post a message",
        "method": "POST",
        "capability": "chat.postMessage (write→read round-trip)",
        "seed_excerpt": {"channel": CH_INCIDENTS, "messages_before": len(before)},
        "ui": {"type": "chat", "title": "Slack › #incidents (after post)",
               "messages": after},
        "agent": {"cli": 'slack post incidents "postmortem doc drafted for INC-482, review by EOD"',
                  "mcp": {"tool": "conversations_add_message",
                          "args": {"channel_id": CH_INCIDENTS,
                                   "payload": "postmortem doc drafted for INC-482, review by EOD"}}},
        "real_mapping": {
            "api": "POST /api/chat.postMessage",
            "mcp": "slack-mcp › conversations_add_message",
            "doc": "https://api.slack.com/methods/chat.postMessage"},
        "clone_output": posted,
        "real_output": {"ok": True, "channel": CH_INCIDENTS, "ts": new_ts,
                        "message": {"type": "message", "user": gw.BOT_USER_ID,
                                    "text": "postmortem doc drafted for INC-482, review by EOD",
                                    "ts": new_ts}},
        "change": {
            "before": [{"id": m["ts"], "text": m["text"]} for m in before],
            "after": [{"id": m["ts"], "text": m["text"]} for m in after],
            "new_id": new_ts},
    })

    return {
        "clone": "abundant-slack-clone",
        "product": "Slack",
        "real_service": {
            "name": "Slack Web API",
            "reference": "https://api.slack.com/web",
            "api_base": "{gateway}/api"},
        "parity": {"verdict": "HIGH",
                   "note": "{ok:...} envelope always HTTP 200, C/U/T ids, ts strings, "
                           "search-operator grammar (in:/from:/before:/after:), korotovsky MCP tool names."},
        "seed_file": SEED_REL,
        "surfaces": {"cli": "slack", "mcp": "slack-mcp"},
        "demos": demos,
    }


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "data" / "abundant-slack-clone.json"
    manifest = build()
    out.write_text(json.dumps(manifest, indent=2, default=str))
    n_post = sum(1 for d in manifest["demos"] if d["method"] == "POST")
    print(f"OK abundant-slack-clone: {len(manifest['demos'])} demos ({n_post} POST), "
          f"seed accepted (Store import path) -> {out}")
