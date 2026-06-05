"""MCP server parity tests.

The MCP server is a thin client of the same /api/* surface as slack-cli, so we
prove parity by routing its httpx client through the in-process ASGI app (via
httpx.ASGITransport) and exercising the underlying `call()` helper + tool registry.
"""

import asyncio
import os
import tempfile

import httpx
import pytest

from slackclone.api.app import create_app
from slackclone.mcp import server
from slackclone.seed import catalog

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACES = os.path.join(REPO_ROOT, "workspaces")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SLACK_WORKSPACE_DIR", WORKSPACES)
    db = tempfile.mktemp(suffix=".db")
    catalog.load_named("acme-incident", db)
    return create_app(db)


@pytest.fixture(autouse=True)
def _route_mcp_through_app(monkeypatch, app):
    def fake_client():
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30)

    monkeypatch.setattr(server, "_client", fake_client)


def test_tool_registry_matches_expected():
    mcp = server.build_server()
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    expected = {
        "slack_conversations_list",
        "slack_conversations_history",
        "slack_conversations_replies",
        "slack_conversations_info",
        "slack_conversations_members",
        "slack_users_list",
        "slack_users_info",
        "slack_search_messages",
        "slack_post_message",
        "slack_chat_update",
        "slack_chat_delete",
        "slack_reactions_add",
        "slack_pins_add",
    }
    assert names == expected


def test_history_parity():
    d = asyncio.run(server.call("conversations.history", channel="incidents", limit=50))
    assert d["ok"] and len(d["messages"]) >= 1


def test_post_then_search_roundtrip():
    posted = asyncio.run(server.call("chat.postMessage", channel="incidents", text="ROOT CAUSE: pool"))
    assert posted["ok"]
    ts = posted["ts"]
    found = asyncio.run(server.call("search.messages", query="root cause in:#incidents"))
    assert any(m["ts"] == ts for m in found["messages"]["matches"])


def test_reactions_and_pins():
    posted = asyncio.run(server.call("chat.postMessage", channel="incidents", text="status update"))
    ts = posted["ts"]
    r = asyncio.run(server.call("reactions.add", channel="incidents", timestamp=ts, name="eyes"))
    assert r["ok"]
    p = asyncio.run(server.call("pins.add", channel="incidents", timestamp=ts))
    assert p["ok"]
    # pinned message shows up as pinned in history
    hist = asyncio.run(server.call("conversations.history", channel="incidents", limit=100))
    assert any(m.get("ts") == ts and m.get("pinned_to") for m in hist["messages"])
