"""The `slack-mcp` MCP server (stdio) — the agent's Slack tools over the Model Context Protocol.

Same operations as the `slack` CLI, exposed as MCP tools backed by the gateway at $SLACK_API_URL.
Harbor launches this as a stdio MCP server (see each task's task.toml [[environment.mcp_servers]]).
"""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import client

mcp = FastMCP("slack")


@mcp.tool()
def slack_whoami() -> dict[str, Any]:
    """Return the authenticated Slack identity (auth.test)."""
    return client.whoami()


@mcp.tool()
def slack_list_channels() -> list[dict[str, Any]]:
    """List all channels in the workspace (id, name, topic, purpose)."""
    return client.list_channels()


@mcp.tool()
def slack_history(channel: str, limit: int = 50) -> list[dict[str, Any]]:
    """Read recent messages from a channel. `channel` is a name (e.g. 'general') or id (C…)."""
    return client.history(channel, limit)


@mcp.tool()
def slack_search(query: str) -> list[dict[str, Any]]:
    """Full-text search across messages. Results are noisy — read and disambiguate carefully."""
    return client.search(query)


@mcp.tool()
def slack_list_users() -> list[dict[str, Any]]:
    """List the workspace's users (id, name, real_name)."""
    return client.list_users()


@mcp.tool()
def slack_post_message(channel: str, text: str) -> dict[str, Any]:
    """Post a message to a channel (name or id). Returns the posted message metadata."""
    return client.post_message(channel, text)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
