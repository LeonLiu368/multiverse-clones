"""Round-trip: synthetic Slack API responses -> export dir -> abundant-slack-clone
importer. Proves the export format is byte-compatible with the clone WITHOUT a real
token. Run: pytest
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]          # .../spoink
PROJECTS = ROOT.parent                               # .../projects
# canonical slack clone now lives under multiverse-clones; its importer (import_export.py)
# + Store (slackgw.store) both sit in selfcontained/base
CLONE_SRC = Path(os.environ.get(
    "SPOINK_CLONES_DIR", str(PROJECTS / "multiverse-clones" / "clones")
)) / "abundant-slack-clone" / "selfcontained" / "base"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(CLONE_SRC))

from spoink.slack_export import fetch_workspace, write_export_dir  # noqa: E402

# --- canned Slack Web API responses -----------------------------------------

AUTH = {"ok": True, "team_id": "T9", "team": "Abundant", "url": "https://abundant.slack.com/", "user": "leon"}
USERS = [
    {"id": "U1", "name": "alice", "real_name": "Alice A",
     "profile": {"email": "alice@x.test", "display_name": "alice"}, "is_bot": False, "deleted": False, "tz": "America/Los_Angeles"},
    {"id": "U2", "name": "bob", "real_name": "Bob B",
     "profile": {"email": "bob@x.test"}, "is_bot": False, "deleted": False, "tz": "America/New_York"},
]
CHANNELS = [
    {"id": "C1", "name": "general", "is_private": False, "is_im": False, "is_mpim": False,
     "is_archived": False, "created": 1700000000, "creator": "U1",
     "topic": {"value": "General"}, "purpose": {"value": "all-hands"}},
    {"id": "C2", "name": "random", "is_private": False, "is_im": False, "is_mpim": False,
     "is_archived": False, "created": 1700000000, "creator": "U2",
     "topic": {"value": ""}, "purpose": {"value": ""}},
]
ROOT_TS = "1700000100.000100"
HISTORY_C1 = [
    {"ts": ROOT_TS, "user": "U1", "text": "deploy is failing", "thread_ts": ROOT_TS, "reply_count": 1},
    {"ts": "1700000200.000200", "user": "U2", "text": "looking", "reactions": [{"name": "eyes", "users": ["U1"], "count": 1}]},
]
REPLIES_C1 = {
    ROOT_TS: [
        {"ts": ROOT_TS, "user": "U1", "text": "deploy is failing", "thread_ts": ROOT_TS, "reply_count": 1},
        {"ts": "1700000150.000150", "user": "U2", "text": "on it", "thread_ts": ROOT_TS},
    ]
}
MEMBERS = {"C1": ["U1", "U2"], "C2": ["U2"]}


class FakeClient:
    """Implements just ok_call + paginate, as fetch_workspace expects."""

    def ok_call(self, method, **params):
        if method == "auth.test":
            return AUTH
        raise AssertionError(f"unexpected ok_call {method}")

    def paginate(self, method, key, **params):
        if method == "users.list":
            return iter(USERS)
        if method == "conversations.list":
            return iter(CHANNELS)
        if method == "conversations.members":
            return iter(MEMBERS.get(params["channel"], []))
        if method == "conversations.history":
            return iter(HISTORY_C1 if params["channel"] == "C1" else [])
        if method == "conversations.replies":
            return iter(REPLIES_C1.get(params["ts"], []))
        raise AssertionError(f"unexpected paginate {method}")


def test_fetch_and_export(tmp_path):
    data = fetch_workspace(FakeClient(), ["#general"], "0")
    # only the requested channel; threads deduped (root+reply+standalone = 3 unique ts)
    assert [c["id"] for c in data["channels"]] == ["C1"]
    assert len(data["messages_by_channel"]["C1"]) == 3

    out = tmp_path / "export"
    counts = write_export_dir(str(out), data)
    assert counts == {"users": 2, "channels": 1, "messages": 3}
    assert (out / "users.json").exists()
    assert (out / "channels.json").exists()
    assert list((out / "general").glob("*.json")), "per-day message files written"


def test_roundtrip_through_clone_importer(tmp_path):
    """The clone's import_export (multiverse layout) must read spoink's export into its
    SQLite Store with full fidelity: 1 channel, 2 users, 3 messages."""
    importer = pytest.importorskip("import_export")   # standalone module in selfcontained/base
    data = fetch_workspace(FakeClient(), ["#general"], "0")
    out = tmp_path / "export"
    write_export_dir(str(out), data)

    store = importer.Store(str(tmp_path / "slack.db"))
    stats = importer.import_export(store, str(out), None, None, None)
    assert stats["channels"] == 1
    assert stats["users"] == 2
    assert stats["messages"] == 3
