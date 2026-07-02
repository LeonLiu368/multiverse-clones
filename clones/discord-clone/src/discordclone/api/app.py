"""FastAPI app implementing the agent-used subset of the Discord REST API v10.

Endpoints live under the real Discord paths, with the real envelopes and errors:

  GET  /users/@me                                          → the bot user
  GET  /users/@me/guilds                                   → guilds the bot is in
  GET  /guilds/{guild.id}                                  → guild object
  GET  /guilds/{guild.id}/channels                         → guild channels
  GET  /guilds/{guild.id}/members?limit=&after=            → guild members
  GET  /guilds/{guild.id}/members/{user.id}                → one member
  GET  /guilds/{guild.id}/messages/search?content=&…       → search (T2 grammar)
  GET  /channels/{channel.id}                              → channel object
  GET  /channels/{channel.id}/messages?before=&after=&…    → message history
  GET  /channels/{channel.id}/messages/{message.id}        → one message
  POST /channels/{channel.id}/messages                     → send a message
  GET  /channels/{channel.id}/pins                          → pinned messages
  PUT  /channels/{channel.id}/messages/{id}/reactions/{e}/@me  → add a reaction
  GET  /channels/{channel.id}/messages/{id}/reactions/{e}  → list reactors

Auth mirrors a Discord bot token: requests carry ``Authorization: Bot <token>``;
presence of a token == valid (like a real integration secret). Errors mirror
Discord's ``{"code": <int>, "message": "<str>", "errors": {…}}`` body with the
matching HTTP status: 401 unauthorized, 404 with a JSON error code (10003 Unknown
Channel / 10008 Unknown Message / 10004 Unknown Guild / 10013 Unknown User /
10007 Unknown Member), 400 (50035) validation, 403 (50001) Missing Access.
"""

from __future__ import annotations

import os
import urllib.parse
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .. import store
from ..db import get_engine, init_db, session_factory
from ..store import SearchError

# The bot's own identity (Discord's GET /users/@me). The seed can override via meta,
# but the default is a stable bot user the verifier can rely on.
BOT_USER_ID = os.environ.get("DISCORD_BOT_USER_ID", "900000000000000001")


class DiscordError(HTTPException):
    """An error rendered as Discord's ``{"code":…, "message":…}`` body."""

    def __init__(self, status: int, code: int, message: str, errors: dict | None = None) -> None:
        super().__init__(status_code=status, detail=message)
        self.code = code
        self.errors = errors


def _err_body(code: int, message: str, errors: dict | None = None) -> dict:
    body: dict[str, Any] = {"code": code, "message": message}
    if errors is not None:
        body["errors"] = errors
    return body


def create_app(db_path: str | None = None) -> FastAPI:
    engine = get_engine(db_path)
    init_db(engine)
    Session = session_factory(engine)
    app = FastAPI(title="abundant-discord-clone", version="0.1.0")

    from .control import make_control_router
    app.include_router(make_control_router(engine))

    require_token = os.environ.get("DISCORD_REQUIRE_TOKEN", "1") != "0"

    def auth(authorization: str | None) -> str:
        token = ""
        if authorization:
            a = authorization.strip()
            if a.lower().startswith("bot "):
                token = a[4:].strip()
            elif a.lower().startswith("bearer "):
                token = a[7:].strip()
            else:
                token = a
        if require_token and not token:
            # Discord's 401 body for a missing/invalid token.
            raise DiscordError(401, 0, "401: Unauthorized")
        return token

    @app.exception_handler(DiscordError)
    async def _discord_error_handler(_req: Request, exc: DiscordError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code,
                            content=_err_body(exc.code, str(exc.detail), exc.errors))

    @app.exception_handler(SearchError)
    async def _search_error_handler(_req: Request, exc: SearchError) -> JSONResponse:
        return JSONResponse(status_code=400,
                            content=_err_body(50035, "Invalid Form Body",
                                              {"_errors": [{"code": "BASE_TYPE_BAD", "message": str(exc)}]}))

    @app.exception_handler(HTTPException)
    async def _http_error_handler(_req: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc, DiscordError):
            return await _discord_error_handler(_req, exc)
        return JSONResponse(status_code=exc.status_code,
                            content=_err_body(0, str(exc.detail)))

    # --------------------------------------------------------------- meta
    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    # --------------------------------------------------------------- users
    @app.get("/users/@me")
    def users_me(authorization: str | None = Header(None)) -> dict:
        auth(authorization)
        with Session() as s:
            u = store.get_user(s, BOT_USER_ID)
            if u is not None:
                return store.user_dict(u)
        return {"id": BOT_USER_ID, "username": "clone-bot", "global_name": "Clone Bot",
                "discriminator": "0", "avatar": None, "bot": True}

    @app.get("/users/@me/guilds")
    def users_me_guilds(authorization: str | None = Header(None)) -> list:
        auth(authorization)
        with Session() as s:
            # Discord's partial guild objects for the current user.
            return [{"id": g.id, "name": g.name, "icon": g.icon, "owner": g.owner_id == BOT_USER_ID,
                     "permissions": "0"} for g in store.list_guilds(s)]

    @app.get("/users/{user_id}")
    def users_get(user_id: str, authorization: str | None = Header(None)) -> dict:
        auth(authorization)
        with Session() as s:
            u = store.get_user(s, user_id)
            if u is None:
                raise DiscordError(404, 10013, "Unknown User")
            return store.user_dict(u)

    # --------------------------------------------------------------- guilds
    @app.get("/guilds/{guild_id}")
    def guild_get(guild_id: str, authorization: str | None = Header(None)) -> dict:
        auth(authorization)
        with Session() as s:
            g = store.get_guild(s, guild_id)
            if g is None:
                raise DiscordError(404, 10004, "Unknown Guild")
            return store.guild_dict(g)

    @app.get("/guilds/{guild_id}/channels")
    def guild_channels(guild_id: str, authorization: str | None = Header(None)) -> list:
        auth(authorization)
        with Session() as s:
            if store.get_guild(s, guild_id) is None:
                raise DiscordError(404, 10004, "Unknown Guild")
            return [store.channel_dict(c) for c in store.list_guild_channels(s, guild_id)]

    @app.get("/guilds/{guild_id}/members")
    def guild_members(guild_id: str, limit: int = Query(1, ge=1, le=1000),
                      after: str | None = Query(None),
                      authorization: str | None = Header(None)) -> list:
        auth(authorization)
        with Session() as s:
            if store.get_guild(s, guild_id) is None:
                raise DiscordError(404, 10004, "Unknown Guild")
            users = store._user_map(s)
            return [store.member_dict(m, users)
                    for m in store.list_members(s, guild_id, limit, after)]

    @app.get("/guilds/{guild_id}/members/{user_id}")
    def guild_member(guild_id: str, user_id: str,
                     authorization: str | None = Header(None)) -> dict:
        auth(authorization)
        with Session() as s:
            if store.get_guild(s, guild_id) is None:
                raise DiscordError(404, 10004, "Unknown Guild")
            m = store.get_member(s, guild_id, user_id)
            if m is None:
                raise DiscordError(404, 10007, "Unknown Member")
            return store.member_dict(m, store._user_map(s))

    # --------------------------------------------------------------- search (T2)
    @app.get("/guilds/{guild_id}/messages/search")
    def guild_search(guild_id: str, request: Request,
                     content: str | None = Query(None),
                     channel_id: str | None = Query(None),
                     author_id: str | None = Query(None),
                     mentions: str | None = Query(None),
                     has: str | None = Query(None),
                     pinned: str | None = Query(None),
                     before: str | None = Query(None),
                     after: str | None = Query(None),
                     limit: int = Query(25, ge=1, le=25),
                     offset: int = Query(0, ge=0),
                     authorization: str | None = Header(None)) -> dict:
        auth(authorization)
        with Session() as s:
            if store.get_guild(s, guild_id) is None:
                raise DiscordError(404, 10004, "Unknown Guild")
            return store.search_messages(
                s, guild_id, content=content, channel_id=channel_id, author_id=author_id,
                mentions=mentions, has=has, pinned=pinned, before=before, after=after,
                limit=limit, offset=offset)

    # --------------------------------------------------------------- channels
    @app.get("/channels/{channel_id}")
    def channel_get(channel_id: str, authorization: str | None = Header(None)) -> dict:
        auth(authorization)
        with Session() as s:
            c = store.get_channel(s, channel_id)
            if c is None:
                raise DiscordError(404, 10003, "Unknown Channel")
            return store.channel_dict(c)

    @app.get("/channels/{channel_id}/messages")
    def channel_messages(channel_id: str, limit: int = Query(50, ge=1, le=100),
                         before: str | None = Query(None), after: str | None = Query(None),
                         around: str | None = Query(None),
                         authorization: str | None = Header(None)) -> list:
        auth(authorization)
        with Session() as s:
            if store.get_channel(s, channel_id) is None:
                raise DiscordError(404, 10003, "Unknown Channel")
            users = store._user_map(s)
            msgs = store.channel_messages(s, channel_id, limit=limit, before=before,
                                          after=after, around=around)
            return [store.message_dict(s, m, users) for m in msgs]

    @app.get("/channels/{channel_id}/messages/{message_id}")
    def channel_message(channel_id: str, message_id: str,
                        authorization: str | None = Header(None)) -> dict:
        auth(authorization)
        with Session() as s:
            if store.get_channel(s, channel_id) is None:
                raise DiscordError(404, 10003, "Unknown Channel")
            m = store.get_message(s, channel_id, message_id)
            if m is None:
                raise DiscordError(404, 10008, "Unknown Message")
            return store.message_dict(s, m)

    @app.post("/channels/{channel_id}/messages")
    async def channel_post(channel_id: str, request: Request,
                           authorization: str | None = Header(None)) -> dict:
        auth(authorization)
        body = await _json(request)
        content = body.get("content")
        if content is None or (isinstance(content, str) and content == "" and not body.get("embeds")):
            raise DiscordError(400, 50006, "Cannot send an empty message",
                               {"content": {"_errors": [
                                   {"code": "BASE_TYPE_REQUIRED", "message": "This field is required"}]}})
        with Session() as s:
            c = store.get_channel(s, channel_id)
            if c is None:
                raise DiscordError(404, 10003, "Unknown Channel")
            mentions = _extract_mentions(s, str(content))
            msg = store.create_message(
                s, channel_id, c.guild_id, BOT_USER_ID, str(content),
                mentions=mentions, mention_everyone="@everyone" in str(content))
            return store.message_dict(s, msg)

    @app.get("/channels/{channel_id}/pins")
    def channel_pins(channel_id: str, authorization: str | None = Header(None)) -> list:
        auth(authorization)
        with Session() as s:
            if store.get_channel(s, channel_id) is None:
                raise DiscordError(404, 10003, "Unknown Channel")
            users = store._user_map(s)
            return [store.message_dict(s, m, users) for m in store.channel_pins(s, channel_id)]

    # --------------------------------------------------------------- reactions
    @app.put("/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me")
    def add_reaction(channel_id: str, message_id: str, emoji: str,
                     authorization: str | None = Header(None)) -> JSONResponse:
        auth(authorization)
        emoji = urllib.parse.unquote(emoji)
        with Session() as s:
            if store.get_channel(s, channel_id) is None:
                raise DiscordError(404, 10003, "Unknown Channel")
            if store.get_message(s, channel_id, message_id) is None:
                raise DiscordError(404, 10008, "Unknown Message")
            store.add_reaction(s, message_id, emoji, BOT_USER_ID)
        return JSONResponse(status_code=204, content=None)  # Discord returns 204 No Content

    @app.get("/channels/{channel_id}/messages/{message_id}/reactions/{emoji}")
    def list_reactions(channel_id: str, message_id: str, emoji: str,
                       limit: int = Query(25, ge=1, le=100), after: str | None = Query(None),
                       authorization: str | None = Header(None)) -> list:
        auth(authorization)
        emoji = urllib.parse.unquote(emoji)
        with Session() as s:
            if store.get_channel(s, channel_id) is None:
                raise DiscordError(404, 10003, "Unknown Channel")
            if store.get_message(s, channel_id, message_id) is None:
                raise DiscordError(404, 10008, "Unknown Message")
            return [store.user_dict(u)
                    for u in store.reaction_users(s, message_id, emoji, limit=limit, after=after)]

    return app


def _extract_mentions(s, content: str) -> list[str]:
    """Pull <@id> / <@!id> user mentions out of message content (Discord markup)."""
    import re

    ids = re.findall(r"<@!?(\d+)>", content or "")
    return [uid for uid in ids if store.get_user(s, uid) is not None]


async def _json(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        body = {}
    return body if isinstance(body, dict) else {}


# module-level app for `uvicorn discordclone.api.app:app`
app = create_app()
