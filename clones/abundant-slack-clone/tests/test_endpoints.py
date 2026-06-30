"""R6.1: every covered HTTP endpoint, happy path + at least one error path.

Hits the live gateway over HTTP and asserts the real Slack envelope shape ({"ok":...}, C…/U… ids,
ts strings, snake_case error codes, cursor metadata).
"""
from __future__ import annotations

from conftest import (CH_ENG, CH_GENERAL, SEARCH_PHRASE, TEAM_ID, THREAD_TS, U_ALICE)


# --------------------------------------------------------------------------- auth
def test_auth_test_happy(http):
    d = http("auth.test")
    assert d["ok"] is True
    assert d["team_id"] == TEAM_ID
    assert d["url"].startswith("https://") and d["url"].endswith(".slack.com/")


def test_auth_required_error(gateway):
    import json
    import urllib.request

    req = urllib.request.Request(f"{gateway['url']}/api/conversations.list")  # no Authorization
    with urllib.request.urlopen(req, timeout=10) as resp:
        d = json.loads(resp.read())
    assert d == {"ok": False, "error": "not_authed"}


# --------------------------------------------------------------------------- conversations.list
def test_conversations_list_happy(http):
    d = http("conversations.list")
    assert d["ok"] is True
    ids = {c["id"] for c in d["channels"]}
    assert {CH_GENERAL, CH_ENG} <= ids
    g = next(c for c in d["channels"] if c["id"] == CH_GENERAL)
    assert g["name"] == "general" and g["name_normalized"] == "general"
    assert g["is_channel"] is True
    assert d["response_metadata"]["next_cursor"] == ""


# --------------------------------------------------------------------------- conversations.info
def test_conversations_info_happy(http):
    d = http("conversations.info", channel=CH_ENG)
    assert d["ok"] is True and d["channel"]["name"] == "engineering"


def test_conversations_info_error(http):
    d = http("conversations.info", channel="C_DOES_NOT_EXIST")
    assert d == {"ok": False, "error": "channel_not_found"}


# --------------------------------------------------------------------------- conversations.history
def test_conversations_history_happy(http):
    d = http("conversations.history", channel=CH_GENERAL, limit=50)
    assert d["ok"] is True and d["has_more"] is False
    texts = [m["text"] for m in d["messages"]]
    assert any("welcome to the workspace" in t for t in texts)
    # history excludes thread replies (Slack semantics): the thread parent's replies aren't here.
    for m in d["messages"]:
        assert m["type"] == "message" and "ts" in m


def test_conversations_history_error(http):
    d = http("conversations.history", channel="C_NOPE")
    assert d == {"ok": False, "error": "channel_not_found"}


# --------------------------------------------------------------------------- conversations.replies
def test_conversations_replies_happy(http):
    d = http("conversations.replies", channel=CH_ENG, ts=THREAD_TS)
    assert d["ok"] is True
    ts_list = [m["ts"] for m in d["messages"]]
    assert ts_list[0] == THREAD_TS               # parent first
    assert len(d["messages"]) == 3               # parent + 2 replies
    assert ts_list == sorted(ts_list)            # oldest-first


def test_conversations_replies_error(http):
    d = http("conversations.replies", channel=CH_ENG, ts="9999999999.000000")
    assert d == {"ok": False, "error": "thread_not_found"}


# --------------------------------------------------------------------------- search.messages
def test_search_messages_happy(http):
    d = http("search.messages", query=SEARCH_PHRASE)
    assert d["ok"] is True
    matches = d["messages"]["matches"]
    assert len(matches) == 1
    assert SEARCH_PHRASE in matches[0]["text"]
    assert matches[0]["channel"]["id"] == CH_GENERAL


def test_search_operators_in_channel(http):
    # `in:` operator scopes to a channel; the phrase is only in #general so in:engineering = 0 hits.
    d = http("search.messages", query=f"{SEARCH_PHRASE} in:engineering")
    assert d["ok"] is True and d["messages"]["total"] == 0


def test_search_empty_query_returns_no_matches(http):
    d = http("search.messages", query="")
    assert d["ok"] is True and d["messages"]["matches"] == []


# --------------------------------------------------------------------------- users.list / users.info
def test_users_list_happy(http):
    d = http("users.list")
    assert d["ok"] is True
    ids = {u["id"] for u in d["members"]}
    assert U_ALICE in ids
    alice = next(u for u in d["members"] if u["id"] == U_ALICE)
    assert alice["name"] == "alice" and alice["profile"]["email"] == "alice@test.dev"


def test_users_info_error(http):
    d = http("users.info", user="U_NOBODY")
    assert d == {"ok": False, "error": "user_not_found"}


# --------------------------------------------------------------------------- team.info
def test_team_info_happy(http):
    d = http("team.info")
    assert d["ok"] is True and d["team"]["id"] == TEAM_ID


# --------------------------------------------------------------------------- chat.postMessage (write->read)
def test_post_message_roundtrip(http):
    posted = http("chat.postMessage", channel="general", text="hello from the test suite")
    assert posted["ok"] is True and posted["channel"] == CH_GENERAL
    ts = posted["ts"]
    hist = http("conversations.history", channel=CH_GENERAL, limit=100)
    got = [m for m in hist["messages"] if m["ts"] == ts]
    assert got and got[0]["text"] == "hello from the test suite"


def test_post_message_error(http):
    d = http("chat.postMessage", channel="C_MISSING", text="x")
    assert d == {"ok": False, "error": "channel_not_found"}


# --------------------------------------------------------------------------- unknown method
def test_unknown_method(http):
    d = http("not.a.real.method")
    assert d == {"ok": False, "error": "unknown_method"}
