"""The shared HTTP client — the single seam the CLI and the MCP server both import.

Both surfaces (``discord`` CLI, ``discord-mcp``) are thin clients of the one HTTP
API (``$DISCORD_API_URL``, default http://localhost:8080), authenticated with the
bot token (``$DISCORD_BOT_TOKEN``) sent as ``Authorization: Bot <token>`` — the same
way real Discord automation is configured. Keeping the request logic here — and
*only* here — is what makes CLI⇄MCP parity hold by construction: one capability is
one ``DiscordClient`` method, called identically from both.

``_transport()`` is factored out so tests can route the client through an in-process
ASGI app (``httpx.ASGITransport``) instead of a real network server.
"""

from __future__ import annotations

import os
import urllib.parse
from typing import Any

import httpx

API_VERSION = "v10"


def api_base() -> str:
    return os.environ.get("DISCORD_API_URL", "http://localhost:8080").rstrip("/")


def token() -> str:
    return os.environ.get("DISCORD_BOT_TOKEN", "discord-clone-token")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bot {token()}",
        "Content-Type": "application/json",
    }


class DiscordAPIError(RuntimeError):
    """A non-2xx response carrying Discord's ``{"code":…, "message":…}`` body."""

    def __init__(self, status: int, body: dict | str) -> None:
        self.status = status
        self.body = body
        code = body.get("code") if isinstance(body, dict) else None
        message = body.get("message") if isinstance(body, dict) else str(body)
        super().__init__(f"{status} [{code}]: {message}")


class DiscordClient:
    """Thin sync client. One method per covered capability — the parity seam."""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 json_body: dict | None = None) -> Any:
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        with httpx.Client(base_url=api_base(), headers=_headers(), timeout=30,
                          transport=self._transport) as c:
            r = c.request(method, path, params=clean, json=json_body)
        if r.status_code == 204:
            return {"status": 204}
        try:
            data = r.json()
        except Exception:
            if r.status_code >= 400:
                raise DiscordAPIError(r.status_code, r.text)
            return {"status": r.status_code}
        if r.status_code >= 400:
            raise DiscordAPIError(r.status_code, data)
        return data

    # ---- identity / users ----
    def me(self) -> dict:
        return self._request("GET", "/users/@me")

    def my_guilds(self) -> list:
        return self._request("GET", "/users/@me/guilds")

    def get_user(self, user_id: str) -> dict:
        return self._request("GET", f"/users/{user_id}")

    # ---- guilds ----
    def get_guild(self, guild_id: str) -> dict:
        return self._request("GET", f"/guilds/{guild_id}")

    def get_guild_channels(self, guild_id: str) -> list:
        return self._request("GET", f"/guilds/{guild_id}/channels")

    def list_members(self, guild_id: str, *, limit: int | None = None,
                     after: str | None = None) -> list:
        return self._request("GET", f"/guilds/{guild_id}/members",
                             params={"limit": limit, "after": after})

    def get_member(self, guild_id: str, user_id: str) -> dict:
        return self._request("GET", f"/guilds/{guild_id}/members/{user_id}")

    def search_messages(self, guild_id: str, *, content: str | None = None,
                        channel_id: str | None = None, author_id: str | None = None,
                        mentions: str | None = None, has: str | None = None,
                        pinned: str | None = None, before: str | None = None,
                        after: str | None = None, limit: int | None = None,
                        offset: int | None = None) -> dict:
        return self._request("GET", f"/guilds/{guild_id}/messages/search", params={
            "content": content, "channel_id": channel_id, "author_id": author_id,
            "mentions": mentions, "has": has, "pinned": pinned, "before": before,
            "after": after, "limit": limit, "offset": offset})

    # ---- channels ----
    def get_channel(self, channel_id: str) -> dict:
        return self._request("GET", f"/channels/{channel_id}")

    def get_messages(self, channel_id: str, *, limit: int | None = None,
                     before: str | None = None, after: str | None = None,
                     around: str | None = None) -> list:
        return self._request("GET", f"/channels/{channel_id}/messages",
                             params={"limit": limit, "before": before, "after": after,
                                     "around": around})

    def get_message(self, channel_id: str, message_id: str) -> dict:
        return self._request("GET", f"/channels/{channel_id}/messages/{message_id}")

    def send_message(self, channel_id: str, content: str) -> dict:
        return self._request("POST", f"/channels/{channel_id}/messages",
                             json_body={"content": content})

    def get_pins(self, channel_id: str) -> list:
        return self._request("GET", f"/channels/{channel_id}/pins")

    # ---- reactions ----
    def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> dict:
        e = urllib.parse.quote(emoji, safe="")
        return self._request(
            "PUT", f"/channels/{channel_id}/messages/{message_id}/reactions/{e}/@me")

    def list_reactions(self, channel_id: str, message_id: str, emoji: str, *,
                       limit: int | None = None, after: str | None = None) -> list:
        e = urllib.parse.quote(emoji, safe="")
        return self._request(
            "GET", f"/channels/{channel_id}/messages/{message_id}/reactions/{e}",
            params={"limit": limit, "after": after})
