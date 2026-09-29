"""stdio MCP server exposing the Slack-clone API as MCP tools.

Each tool is a thin pass-through to ``POST $SLACK_API_URL/api/<method>`` returning
the Slack envelope (``{"ok": true, ...}``). The tool names mirror the Slack Web API
method names so an agent familiar with Slack tooling is immediately at home, and
they stay in lockstep with ``slack-cli`` because both call the same HTTP surface.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


def api_base() -> str:
    return os.environ.get("SLACK_API_URL", "http://localhost:3000").rstrip("/")


def _client() -> httpx.AsyncClient:
    """The httpx client used for API calls.

    Factored out so tests can monkeypatch it to route through an in-process ASGI
    app (``httpx.ASGITransport``) instead of a real network server.
    """
    return httpx.AsyncClient(base_url=api_base(), timeout=30)


async def call(method: str, **params: Any) -> dict:
    """POST to ``/api/<method>`` with non-None params; return the JSON envelope."""
    data = {k: v for k, v in params.items() if v is not None}
    async with _client() as client:
        r = await client.post(f"/api/{method}", data=data)
        r.raise_for_status()
        return r.json()


def build_server() -> FastMCP:
    """Construct the FastMCP server with all Slack-clone tools registered."""
    mcp = FastMCP("abundant-slack-clone")

    # ---- reads ----
    @mcp.tool()
    async def slack_conversations_list(limit: int = 1000) -> dict:
        """List channels in the workspace."""
        return await call("conversations.list", limit=limit)

    @mcp.tool()
    async def slack_conversations_history(
        channel: str, limit: int = 50, oldest: str | None = None, latest: str | None = None
    ) -> dict:
        """Fetch top-level messages in a channel (newest first)."""
        return await call("conversations.history", channel=channel, limit=limit, oldest=oldest, latest=latest)

    @mcp.tool()
    async def slack_conversations_replies(channel: str, ts: str) -> dict:
        """Fetch a thread (parent message + replies) by its root ts."""
        return await call("conversations.replies", channel=channel, ts=ts)

    @mcp.tool()
    async def slack_conversations_info(channel: str) -> dict:
        """Fetch channel metadata (topic, purpose, members count)."""
        return await call("conversations.info", channel=channel)

    @mcp.tool()
    async def slack_conversations_members(channel: str) -> dict:
        """List the member user ids of a channel."""
        return await call("conversations.members", channel=channel)

    @mcp.tool()
    async def slack_users_list(limit: int = 1000) -> dict:
        """List users in the workspace."""
        return await call("users.list", limit=limit)

    @mcp.tool()
    async def slack_users_info(user: str) -> dict:
        """Fetch a single user by id (e.g. U...)."""
        return await call("users.info", user=user)

    @mcp.tool()
    async def slack_search_messages(query: str, count: int = 20) -> dict:
        """Search messages. Supports `in:#channel` and `from:@user` modifiers."""
        return await call("search.messages", query=query, count=count)

    # ---- writes ----
    @mcp.tool()
    async def slack_post_message(
        channel: str, text: str, thread_ts: str | None = None, user: str | None = None
    ) -> dict:
        """Post a message (optionally a thread reply via thread_ts). Returns the new ts."""
        return await call("chat.postMessage", channel=channel, text=text, thread_ts=thread_ts, user=user)

    @mcp.tool()
    async def slack_chat_update(channel: str, ts: str, text: str, user: str | None = None) -> dict:
        """Edit an existing message."""
        return await call("chat.update", channel=channel, ts=ts, text=text, user=user)

    @mcp.tool()
    async def slack_chat_delete(channel: str, ts: str) -> dict:
        """Delete a message."""
        return await call("chat.delete", channel=channel, ts=ts)

    @mcp.tool()
    async def slack_reactions_add(channel: str, timestamp: str, name: str, user: str | None = None) -> dict:
        """Add an emoji reaction (name is the short code without colons)."""
        return await call("reactions.add", channel=channel, timestamp=timestamp, name=name, user=user)

    @mcp.tool()
    async def slack_pins_add(channel: str, timestamp: str, user: str | None = None) -> dict:
        """Pin a message to a channel."""
        return await call("pins.add", channel=channel, timestamp=timestamp, user=user)

    return mcp


def main() -> None:
    """Entry point: run the MCP server over stdio."""
    build_server().run()


if __name__ == "__main__":
    main()
