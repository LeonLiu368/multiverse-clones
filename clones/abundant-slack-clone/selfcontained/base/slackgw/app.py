"""Slack Web API gateway over a SQLite store (FastAPI).

Implements the task-scoped subset of the Slack Web API the eval tasks + off-the-shelf Slack tooling
(our `slack` CLI and the korotovsky `slack-mcp-server`) use, served from a local SQLite store seeded
from a real Slack export (`import_export.py`). Faithful where it's cheap and where agents/tools trip:
the `{"ok":...}` envelope (always HTTP 200), `C…`/`U…` ids, `ts` strings, thread replies, reactions,
cursor fields, and snake_case error codes. No external backend — the store is the source of truth.
"""
from __future__ import annotations

import datetime
import json
import os
import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from slackgw.store import Store

# The bearer token the agent/tools present; validated against this single value. An xoxp- (user)
# token by default so the korotovsky MCP enables its search tool (it disables search for xoxb bots).
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "xoxp-acme-eval-0001")
BOT_USER_ID = os.environ.get("SLACK_BOT_USER_ID", "U0BOTACME0")
BOT_ID = os.environ.get("SLACK_BOT_ID", "B0BOTACME0")

app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
store = Store()


def ok(**kw) -> JSONResponse:
    return JSONResponse({"ok": True, **kw})


def err(code: str) -> JSONResponse:
    return JSONResponse({"ok": False, "error": code})


# --------------------------------------------------------------------------- param + auth helpers
async def params(request: Request) -> dict[str, Any]:
    """Collect params from query + body, robust to how slack_sdk / slack-go frame requests. Never raises."""
    data: dict[str, Any] = dict(request.query_params)
    try:
        body = await request.body()
    except Exception:
        body = b""
    if not body:
        return data
    ct = request.headers.get("content-type", "")
    if "application/json" in ct:
        try:
            data.update(await request.json())
        except Exception:
            pass
        return data
    try:
        form = await request.form()
        data.update({k: v for k, v in form.items()})
    except Exception:
        try:
            from urllib.parse import parse_qsl
            data.update(dict(parse_qsl(body.decode(errors="ignore"))))
        except Exception:
            pass
    return data


def authed(request: Request, p: dict[str, Any]) -> bool:
    tok = ""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        tok = auth[7:].strip()
    tok = tok or str(p.get("token", ""))
    return bool(tok) and tok == SLACK_BOT_TOKEN


@app.middleware("http")
async def neutral_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["server"] = "slack"
    return resp


# --------------------------------------------------------------------------- serializers
def _msg(m: dict, *, channel: str | None = None) -> dict:
    out: dict[str, Any] = {"type": "message", "user": m["user"], "text": m.get("text", ""),
                           "ts": m["ts"]}
    if m.get("subtype"):
        out["subtype"] = m["subtype"]
    if m.get("thread_ts"):
        out["thread_ts"] = m["thread_ts"]
    if m.get("reply_count"):
        out["reply_count"] = m["reply_count"]
    if m.get("edited_ts"):
        out["edited"] = {"user": m["user"], "ts": m["edited_ts"]}
    if m.get("reactions"):
        try:
            out["reactions"] = json.loads(m["reactions"])
        except Exception:
            pass
    if channel:
        out["channel"] = {"id": channel}
    return out


def _channel(c: dict) -> dict:
    name = c.get("name")
    return {
        # name_normalized matters: the korotovsky MCP renders a channel as "#" + name_normalized,
        # so without it every channel shows up as just "#" and can't be found/filtered by name.
        "id": c["id"], "name": name, "name_normalized": name,
        "is_channel": True, "is_group": False, "is_im": False,
        "is_private": False, "is_archived": bool(c.get("is_archived")),
        "is_general": bool(c.get("is_general")), "created": c.get("created") or 0,
        "creator": c.get("creator") or "", "num_members": c.get("num_members") or 0,
        "topic": {"value": c.get("topic") or "", "creator": "", "last_set": 0},
        "purpose": {"value": c.get("purpose") or "", "creator": "", "last_set": 0},
    }


# Slack search operators we honor: free text is ANDed; in:/from: scope to a channel/user; date
# operators bound the ts range. Anything else (is:, with:, during:) is parsed but ignored gracefully.
_FILTER_KEYS = {"in", "from", "with", "is", "before", "after", "on", "during"}


def _parse_search(raw: str) -> tuple[list[str], dict[str, str]]:
    """Split a Slack-style query into free-text terms (quoted phrases kept whole) + operator filters."""
    terms: list[str] = []
    ops: dict[str, str] = {}
    for tok in re.findall(r'"[^"]*"|\S+', raw or ""):
        if not tok.startswith('"') and ":" in tok:
            key, val = tok.split(":", 1)
            if key.lower() in _FILTER_KEYS and val:
                ops.setdefault(key.lower(), val)
                continue
        terms.append(tok.strip('"'))
    return [t for t in terms if t], ops


def _clean_ref(v: str) -> str:
    """Normalize a channel/user operator value (#name, @user, <#C123|name>, C123) to a bare ref."""
    v = v.strip().strip('"')
    if v.startswith("<") and v.endswith(">"):
        v = v[1:-1]
    if "|" in v:
        v = v.split("|")[-1]
    return v.lstrip("#@")


def _date_ts(d: str, *, end: bool = False) -> str | None:
    try:
        dt = datetime.datetime.strptime(d.strip(), "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None
    if end:
        dt = dt.replace(hour=23, minute=59, second=59)
    return f"{dt.timestamp():.6f}"


def _user(u: dict) -> dict:
    return {
        "id": u["id"], "name": u.get("name") or u["id"],
        "real_name": u.get("real_name") or u.get("display_name") or u.get("name") or "",
        "deleted": bool(u.get("deleted")), "is_bot": bool(u.get("is_bot")), "tz": u.get("tz") or "",
        "profile": {
            "real_name": u.get("real_name") or u.get("name") or "",
            "display_name": u.get("display_name") or u.get("name") or "",
            "email": u.get("email") or "",
        },
    }


# --------------------------------------------------------------------------- methods
async def _dispatch(method: str, request: Request) -> JSONResponse:
    p = await params(request)
    if not authed(request, p):
        return err("not_authed")
    team_id = store.get_meta("team_id", "T0000000000")
    team_name = store.get_meta("team_name", "workspace")

    if method == "auth.test":
        # A Slack-shaped workspace URL (host must have >=3 dotted parts) so clients that parse the
        # workspace name from it (e.g. the korotovsky MCP) succeed. The actual API base the tools
        # call is configured separately (our gateway), not derived from this field.
        ws = re.sub(r"[^a-z0-9-]+", "-", team_name.lower()).strip("-") or "workspace"
        return ok(url=f"https://{ws}.slack.com/", team=team_name, user="bot",
                  team_id=team_id, user_id=BOT_USER_ID, bot_id=BOT_ID, is_enterprise_install=False)

    if method in ("conversations.list", "users.conversations"):
        return ok(channels=[_channel(c) for c in store.list_channels()],
                  response_metadata={"next_cursor": ""})

    if method == "conversations.info":
        c = store.channel_by_ref(str(p.get("channel", "")))
        return ok(channel=_channel(c)) if c else err("channel_not_found")

    if method == "conversations.history":
        c = store.channel_by_ref(str(p.get("channel", "")))
        if not c:
            return err("channel_not_found")
        try:
            limit = int(p.get("limit", 100))
        except Exception:
            limit = 100
        msgs = store.history(c["id"], limit)
        return ok(messages=[_msg(m) for m in msgs], has_more=False,
                  response_metadata={"next_cursor": ""})

    if method == "conversations.replies":
        c = store.channel_by_ref(str(p.get("channel", "")))
        if not c:
            return err("channel_not_found")
        thread = str(p.get("ts", p.get("thread_ts", "")))
        msgs = store.replies(c["id"], thread)
        if not msgs:
            return err("thread_not_found")
        return ok(messages=[_msg(m) for m in msgs], has_more=False,
                  response_metadata={"next_cursor": ""})

    if method in ("search.messages", "search.all", "search.inline"):
        # slack-go's combined SearchContext posts to search.all (messages + files in one response);
        # search.messages is the messages-only variant. We have no files, so files is always empty.
        # Parse Slack search operators (in:/from:/before:/after:/on:) so channel-scoped and
        # multi-term queries work like the real API instead of literal-substring matching the whole
        # string (which the korotovsky MCP and agents lean on heavily).
        query = str(p.get("query", p.get("terms", "")))
        try:
            count = int(p.get("count", 100))
        except Exception:
            count = 100
        terms, ops = _parse_search(query)
        channel_id: str | None = None
        if ops.get("in"):
            c = store.channel_by_ref(_clean_ref(ops["in"]))
            channel_id = c["id"] if c else "\x00"  # unresolved channel -> no matches
        user_id: str | None = None
        if ops.get("from"):
            u = store.user_by_ref(_clean_ref(ops["from"]))
            user_id = u["id"] if u else "\x00"
        after = _date_ts(ops["after"]) if ops.get("after") else None
        before = _date_ts(ops["before"], end=True) if ops.get("before") else None
        if ops.get("on"):
            after, before = _date_ts(ops["on"]), _date_ts(ops["on"], end=True)
        rows = store.search(terms, count, channel_id=channel_id, user_id=user_id,
                            after=after, before=before)
        matches = [_msg(m, channel=m["channel_id"]) for m in rows]
        n = len(matches)
        msg_paging = {"count": n, "total": n, "page": 1, "pages": 1}
        msg_pag = {"total_count": n, "page": 1, "per_page": count, "page_count": 1, "first": 1, "last": n}
        files = {"total": 0, "matches": [], "paging": {"count": 0, "total": 0, "page": 1, "pages": 0},
                 "pagination": {"total_count": 0, "page": 1, "per_page": count,
                                "page_count": 0, "first": 0, "last": 0}}
        return ok(query=query,
                  messages={"total": n, "matches": matches, "paging": msg_paging, "pagination": msg_pag},
                  files=files)

    if method == "search.files":
        query = str(p.get("query", p.get("terms", "")))
        return ok(query=query, files={"total": 0, "matches": [],
                                      "paging": {"count": 0, "total": 0, "page": 1, "pages": 0},
                                      "pagination": {"total_count": 0, "page": 1, "per_page": 100,
                                                     "page_count": 0, "first": 0, "last": 0}})

    if method == "users.list":
        return ok(members=[_user(u) for u in store.list_users()],
                  response_metadata={"next_cursor": ""})

    if method == "users.info":
        u = store.user_by_ref(str(p.get("user", "")))
        return ok(user=_user(u)) if u else err("user_not_found")

    if method == "team.info":
        return ok(team={"id": team_id, "name": team_name, "domain": team_name})

    if method in ("chat.postMessage", "conversations.add_message"):
        c = store.channel_by_ref(str(p.get("channel", "")))
        if not c:
            return err("channel_not_found")
        text = str(p.get("text", ""))
        thread_ts = str(p.get("thread_ts", "") or "")
        m = store.post_message(c["id"], BOT_USER_ID, text, thread_ts)
        return ok(channel=c["id"], ts=m["ts"], message=_msg(m))

    return err("unknown_method")


@app.api_route("/api/{method}", methods=["GET", "POST"])
async def slack_method(method: str, request: Request) -> JSONResponse:
    try:
        return await _dispatch(method, request)
    except Exception:
        return err("internal_error")


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)


@app.exception_handler(StarletteHTTPException)
async def _http_exc(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "unknown_method" if exc.status_code == 404 else "error"
    return JSONResponse({"ok": False, "error": code}, status_code=exc.status_code)
