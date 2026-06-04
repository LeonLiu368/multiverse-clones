"""FastAPI app implementing a subset of the Slack Web API.

Methods live at ``/api/<method>`` (e.g. ``/api/conversations.history``), accept
GET or POST (query params, JSON, or form — like Slack), and return the Slack
envelope ``{"ok": true, ...}`` / ``{"ok": false, "error": "..."}``. No auth.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Request
from sqlalchemy import select

from .. import store
from ..db import get_engine, init_db, session_factory
from ..models import User, Workspace


def _int(v: Any, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _truthy(v: Any) -> bool:
    return str(v).lower() in ("1", "true", "yes")


def create_app(db_path: str | None = None) -> FastAPI:
    engine = get_engine(db_path)
    init_db(engine)
    Session = session_factory(engine)
    app = FastAPI(title="abundant-slack-clone", version="0.1.0")

    def ok(**kw: Any) -> dict:
        return {"ok": True, **kw}

    def err(e: str) -> dict:
        return {"ok": False, "error": e}

    async def params(request: Request) -> dict:
        data = dict(request.query_params)
        if request.method == "POST":
            ctype = request.headers.get("content-type", "")
            try:
                if "application/json" in ctype:
                    data.update(await request.json())
                else:
                    form = await request.form()
                    data.update({k: v for k, v in form.items()})
            except Exception:
                pass
        return data

    def default_user(s) -> str:
        env = os.environ.get("SLACK_USER")
        if env:
            return env
        bot = s.scalars(select(User).where(User.is_bot.is_(True))).first()
        if bot:
            return bot.id
        any_user = s.scalars(select(User)).first()
        return any_user.id if any_user else "USIMBOT"

    # ----- meta -----
    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "status": "healthy"}

    @app.api_route("/api/auth.test", methods=["GET", "POST"])
    def auth_test() -> dict:
        with Session() as s:
            w = s.scalars(select(Workspace)).first()
            return ok(
                url="http://slack:3000/",
                team=(w.name if w else "workspace"),
                team_id=(w.id if w else "T0SIMULATED"),
                user="incidentbot",
                user_id=default_user(s),
            )

    # ----- conversations -----
    @app.api_route("/api/conversations.list", methods=["GET", "POST"])
    async def conversations_list(request: Request) -> dict:
        p = await params(request)
        types = [t.strip() for t in (p.get("types") or "public_channel,private_channel").split(",")]
        with Session() as s:
            chans, cur = store.list_channels(
                s,
                types=types,
                exclude_archived=_truthy(p.get("exclude_archived")),
                cursor=p.get("cursor"),
                limit=_int(p.get("limit"), 100),
            )
        return ok(channels=chans, response_metadata={"next_cursor": cur})

    @app.api_route("/api/conversations.history", methods=["GET", "POST"])
    async def conversations_history(request: Request) -> dict:
        p = await params(request)
        if not p.get("channel"):
            return err("channel_not_found")
        with Session() as s:
            try:
                msgs, has_more, cur = store.history(
                    s, p["channel"],
                    oldest=_float(p.get("oldest")), latest=_float(p.get("latest")),
                    inclusive=_truthy(p.get("inclusive")),
                    cursor=p.get("cursor"), limit=_int(p.get("limit"), 100),
                )
            except KeyError as e:
                return err(e.args[0])
        return ok(messages=msgs, has_more=has_more, response_metadata={"next_cursor": cur})

    @app.api_route("/api/conversations.replies", methods=["GET", "POST"])
    async def conversations_replies(request: Request) -> dict:
        p = await params(request)
        if not p.get("channel") or not p.get("ts"):
            return err("thread_not_found")
        with Session() as s:
            try:
                msgs = store.replies(s, p["channel"], str(p["ts"]))
            except KeyError as e:
                return err(e.args[0])
        return ok(messages=msgs, has_more=False)

    @app.api_route("/api/conversations.info", methods=["GET", "POST"])
    async def conversations_info(request: Request) -> dict:
        p = await params(request)
        with Session() as s:
            try:
                return ok(channel=store.channel_info(s, p.get("channel", "")))
            except KeyError as e:
                return err(e.args[0])

    @app.api_route("/api/conversations.members", methods=["GET", "POST"])
    async def conversations_members(request: Request) -> dict:
        p = await params(request)
        with Session() as s:
            try:
                return ok(members=store.members(s, p.get("channel", "")),
                          response_metadata={"next_cursor": ""})
            except KeyError as e:
                return err(e.args[0])

    # ----- chat -----
    @app.api_route("/api/chat.postMessage", methods=["GET", "POST"])
    async def chat_post(request: Request) -> dict:
        p = await params(request)
        if not p.get("channel"):
            return err("channel_not_found")
        with Session() as s:
            try:
                res = store.post_message(
                    s, p["channel"], p.get("text", ""),
                    user=p.get("user") or default_user(s),
                    thread_ts=p.get("thread_ts"),
                )
            except KeyError as e:
                return err(e.args[0])
        return ok(**res)

    @app.api_route("/api/chat.update", methods=["GET", "POST"])
    async def chat_update(request: Request) -> dict:
        p = await params(request)
        with Session() as s:
            try:
                res = store.update_message(s, p.get("channel", ""), str(p.get("ts", "")),
                                           p.get("text", ""), user=p.get("user"))
            except KeyError as e:
                return err(e.args[0])
        return ok(**res)

    @app.api_route("/api/chat.delete", methods=["GET", "POST"])
    async def chat_delete(request: Request) -> dict:
        p = await params(request)
        with Session() as s:
            try:
                res = store.delete_message(s, p.get("channel", ""), str(p.get("ts", "")))
            except KeyError as e:
                return err(e.args[0])
        return ok(**res)

    # ----- users -----
    @app.api_route("/api/users.list", methods=["GET", "POST"])
    async def users_list(request: Request) -> dict:
        p = await params(request)
        with Session() as s:
            users, cur = store.list_users(s, cursor=p.get("cursor"), limit=_int(p.get("limit"), 100))
        return ok(members=users, response_metadata={"next_cursor": cur})

    @app.api_route("/api/users.info", methods=["GET", "POST"])
    async def users_info(request: Request) -> dict:
        p = await params(request)
        with Session() as s:
            u = store.get_user(s, p.get("user", ""))
        return ok(user=u) if u else err("user_not_found")

    # ----- search -----
    @app.api_route("/api/search.messages", methods=["GET", "POST"])
    async def search_messages(request: Request) -> dict:
        p = await params(request)
        if not p.get("query"):
            return err("no_query")
        with Session() as s:
            res = store.search_messages(s, p["query"], count=_int(p.get("count"), 20),
                                        page=_int(p.get("page"), 1))
        return ok(query=p["query"], messages=res)

    # ----- reactions / pins -----
    @app.api_route("/api/reactions.add", methods=["GET", "POST"])
    async def reactions_add(request: Request) -> dict:
        p = await params(request)
        with Session() as s:
            try:
                store.add_reaction(s, p.get("channel", ""), str(p.get("timestamp", p.get("ts", ""))),
                                   p.get("name", ""), user=p.get("user") or default_user(s))
            except KeyError as e:
                return err(e.args[0])
            except ValueError as e:
                return err(e.args[0])
        return ok()

    @app.api_route("/api/pins.add", methods=["GET", "POST"])
    async def pins_add(request: Request) -> dict:
        p = await params(request)
        with Session() as s:
            try:
                store.add_pin(s, p.get("channel", ""), str(p.get("timestamp", p.get("ts", ""))),
                              user=p.get("user") or default_user(s))
            except KeyError as e:
                return err(e.args[0])
        return ok()

    return app


# module-level app for `uvicorn slackclone.api.app:app`
app = create_app()
