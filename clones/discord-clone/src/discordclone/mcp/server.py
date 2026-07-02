"""stdio MCP server exposing the Discord-clone API as MCP tools.

Each tool is a thin pass-through to the shared ``DiscordClient`` — the SAME seam the
CLI uses — so the two surfaces stay in lockstep by construction (one capability →
one CLI command AND one MCP tool, both calling the identical client method). Tool
names mirror the Discord verbs (``discord_get_messages``, ``discord_send_message``…).
The control plane is never exposed.

The client is constructed per call so tests can monkeypatch ``DiscordClient`` to
route through an in-process ASGI app and prove CLI⇄MCP⇄API parity without sockets.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..client import DiscordAPIError, DiscordClient


def _call(fn) -> Any:
    """Run a client call, turning API errors into a structured error dict (not a raise)."""
    try:
        return fn(DiscordClient())
    except DiscordAPIError as e:
        return e.body if isinstance(e.body, dict) else {"code": 0, "message": str(e.body)}


def build_server() -> FastMCP:
    mcp = FastMCP("abundant-discord-clone")

    # ---- identity / users ----
    @mcp.tool()
    def discord_get_self() -> dict:
        """Retrieve the bot/integration user (Discord's GET /users/@me)."""
        return _call(lambda c: c.me())

    @mcp.tool()
    def discord_list_my_guilds() -> list:
        """List the guilds the bot is a member of (GET /users/@me/guilds)."""
        return _call(lambda c: c.my_guilds())

    @mcp.tool()
    def discord_get_user(user_id: str) -> dict:
        """Retrieve a user object by id."""
        return _call(lambda c: c.get_user(user_id))

    # ---- guilds ----
    @mcp.tool()
    def discord_get_guild(guild_id: str) -> dict:
        """Retrieve a guild (server) object."""
        return _call(lambda c: c.get_guild(guild_id))

    @mcp.tool()
    def discord_get_guild_channels(guild_id: str) -> list:
        """List the channels in a guild."""
        return _call(lambda c: c.get_guild_channels(guild_id))

    @mcp.tool()
    def discord_list_members(guild_id: str, limit: int | None = None,
                             after: str | None = None) -> list:
        """List a guild's members (paginated by ascending user id)."""
        return _call(lambda c: c.list_members(guild_id, limit=limit, after=after))

    @mcp.tool()
    def discord_get_member(guild_id: str, user_id: str) -> dict:
        """Retrieve one guild member (nick, roles, joined_at)."""
        return _call(lambda c: c.get_member(guild_id, user_id))

    # ---- search ----
    @mcp.tool()
    def discord_search_messages(guild_id: str, content: str | None = None,
                                channel_id: str | None = None, author_id: str | None = None,
                                mentions: str | None = None, has: str | None = None,
                                pinned: str | None = None, before: str | None = None,
                                after: str | None = None, limit: int | None = None,
                                offset: int | None = None) -> dict:
        """Search a guild's messages by content + filters (channel/author/mentions/has/pinned/before/after)."""
        return _call(lambda c: c.search_messages(
            guild_id, content=content, channel_id=channel_id, author_id=author_id,
            mentions=mentions, has=has, pinned=pinned, before=before, after=after,
            limit=limit, offset=offset))

    # ---- channels ----
    @mcp.tool()
    def discord_get_channel(channel_id: str) -> dict:
        """Retrieve a channel object."""
        return _call(lambda c: c.get_channel(channel_id))

    @mcp.tool()
    def discord_get_messages(channel_id: str, limit: int | None = None,
                             before: str | None = None, after: str | None = None,
                             around: str | None = None) -> list:
        """Read a channel's message history (newest-first; before/after/around snowflake pagination)."""
        return _call(lambda c: c.get_messages(channel_id, limit=limit, before=before,
                                              after=after, around=around))

    @mcp.tool()
    def discord_get_message(channel_id: str, message_id: str) -> dict:
        """Retrieve a single message by id."""
        return _call(lambda c: c.get_message(channel_id, message_id))

    @mcp.tool()
    def discord_send_message(channel_id: str, content: str) -> dict:
        """Post a message to a channel (returns the created message object)."""
        return _call(lambda c: c.send_message(channel_id, content))

    @mcp.tool()
    def discord_get_pins(channel_id: str) -> list:
        """List a channel's pinned messages."""
        return _call(lambda c: c.get_pins(channel_id))

    # ---- reactions ----
    @mcp.tool()
    def discord_add_reaction(channel_id: str, message_id: str, emoji: str) -> dict:
        """Add the bot's reaction (emoji) to a message."""
        return _call(lambda c: c.add_reaction(channel_id, message_id, emoji))

    @mcp.tool()
    def discord_list_reactions(channel_id: str, message_id: str, emoji: str,
                               limit: int | None = None, after: str | None = None) -> list:
        """List the users who reacted to a message with an emoji."""
        return _call(lambda c: c.list_reactions(channel_id, message_id, emoji,
                                                limit=limit, after=after))

    return mcp


def main() -> None:
    """Entry point: run the MCP server over stdio."""
    build_server().run()


if __name__ == "__main__":
    main()
