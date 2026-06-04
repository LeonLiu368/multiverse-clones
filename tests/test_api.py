import tempfile

import pytest
from fastapi.testclient import TestClient

from slackclone.api.app import create_app
from slackclone.seed.generator import generate
from slackclone.seed.load import load_seed


@pytest.fixture
def client():
    db = tempfile.mktemp(suffix=".db")
    load_seed(generate(users=6, channels=4, days=5, seed=42), db)
    return TestClient(create_app(db))


def _find_thread_parent(client):
    for ch in client.post("/api/conversations.list").json()["channels"]:
        msgs = client.post("/api/conversations.history", data={"channel": ch["id"], "limit": 200}).json()["messages"]
        for m in msgs:
            if m.get("reply_count"):
                return ch["id"], m
    return None, None


def test_channels_list(client):
    d = client.post("/api/conversations.list").json()
    assert d["ok"] and len(d["channels"]) >= 4
    assert "next_cursor" in d["response_metadata"]


def test_history_is_top_level_only(client):
    cid, parent = _find_thread_parent(client)
    assert parent is not None, "generator should produce at least one thread"
    msgs = client.post("/api/conversations.history", data={"channel": cid, "limit": 200}).json()["messages"]
    # nothing in history is a reply (a reply has thread_ts != its own ts)
    assert all(m.get("thread_ts", m["ts"]) == m["ts"] for m in msgs)


def test_replies_returns_parent_plus_replies(client):
    cid, parent = _find_thread_parent(client)
    r = client.post("/api/conversations.replies", data={"channel": cid, "ts": parent["ts"]}).json()
    assert r["ok"]
    assert len(r["messages"]) == parent["reply_count"] + 1  # parent + replies
    assert r["messages"][0]["ts"] == parent["ts"]  # parent first (chronological)


def test_pagination_no_overlap(client):
    p1 = client.post("/api/conversations.history", data={"channel": "general", "limit": 3}).json()
    cur = p1["response_metadata"]["next_cursor"]
    if cur:
        p2 = client.post("/api/conversations.history", data={"channel": "general", "limit": 3, "cursor": cur}).json()
        assert not ({m["ts"] for m in p1["messages"]} & {m["ts"] for m in p2["messages"]})


def test_post_search_react_update_pin(client):
    post = client.post("/api/chat.postMessage", data={"channel": "general", "text": "needle-xyz"}).json()
    assert post["ok"] and post["ts"]
    assert client.post("/api/search.messages", data={"query": "needle-xyz"}).json()["messages"]["total"] == 1
    assert client.post("/api/reactions.add", data={"channel": "general", "timestamp": post["ts"], "name": "tada"}).json()["ok"]
    # idempotency guard like Slack
    assert client.post("/api/reactions.add", data={"channel": "general", "timestamp": post["ts"], "name": "tada"}).json()["error"] == "already_reacted"
    assert client.post("/api/chat.update", data={"channel": "general", "ts": post["ts"], "text": "edited"}).json()["ok"]
    assert client.post("/api/pins.add", data={"channel": "general", "timestamp": post["ts"]}).json()["ok"]
    # the edited message now reports an `edited` block
    hist = client.post("/api/conversations.history", data={"channel": "general", "limit": 200}).json()["messages"]
    edited = next(m for m in hist if m["ts"] == post["ts"])
    assert edited["text"] == "edited" and "edited" in edited and "reactions" in edited


def test_thread_reply_roundtrip(client):
    parent = client.post("/api/chat.postMessage", data={"channel": "general", "text": "root"}).json()
    client.post("/api/chat.postMessage", data={"channel": "general", "text": "reply", "thread_ts": parent["ts"]})
    r = client.post("/api/conversations.replies", data={"channel": "general", "ts": parent["ts"]}).json()
    assert [m["text"] for m in r["messages"]] == ["root", "reply"]


def test_users(client):
    d = client.post("/api/users.list").json()
    assert d["ok"] and any(u["is_bot"] for u in d["members"])
    uid = d["members"][0]["id"]
    assert client.post("/api/users.info", data={"user": uid}).json()["user"]["id"] == uid


def test_unknown_channel_errors(client):
    assert client.post("/api/conversations.history", data={"channel": "does-not-exist"}).json()["error"] == "channel_not_found"
