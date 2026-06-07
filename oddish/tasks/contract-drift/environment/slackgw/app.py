"""Slack Web API gateway over Mattermost (FastAPI).

Implements the task-scoped subset of the Slack Web API the eval tasks use, translating each
method to Mattermost /api/v4. Faithful where it's cheap and where agents trip: the `{"ok":...}`
envelope (always HTTP 200), `C…`/`U…` ids, `ts` strings, cursor pagination, and snake_case
error codes. Mattermost is reached at MM_URL (localhost inside the sidecar) and is never exposed
to the agent; only this gateway is.
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

MM_URL = os.environ.get("MM_URL", "http://localhost:8065")
MM_TEAM = os.environ.get("MM_TEAM", "test-demo")
MM_ADMIN_USER = os.environ.get("MM_ADMIN_USER", "admin@demo.local")
MM_ADMIN_PASS = os.environ.get("MM_ADMIN_PASS", "AdminUser123!")
# The xoxb- token the agent presents. The gateway maps it (internally) to a Mattermost admin
# session; the agent never sees the Mattermost token.
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "xoxb-acme-slack-gateway-token")

app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)


# --------------------------------------------------------------------------- Mattermost client
class MM:
    def __init__(self) -> None:
        self._client = httpx.Client(base_url=MM_URL, timeout=15.0)
        self._token: str | None = None
        self._team_id: str | None = None
        # bidirectional id maps (Slack <-> Mattermost), built lazily and cached
        self.s2c: dict[str, str] = {}   # slack channel id -> mm channel id
        self.c2s: dict[str, str] = {}   # mm channel id -> slack channel id
        self.name2c: dict[str, str] = {}  # channel name -> mm channel id
        self.s2u: dict[str, str] = {}   # slack user id -> mm user id
        self.u2s: dict[str, str] = {}   # mm user id -> slack user id
        self.uname: dict[str, str] = {}  # mm user id -> username

    def _login(self) -> None:
        r = self._client.post("/api/v4/users/login",
                              json={"login_id": MM_ADMIN_USER, "password": MM_ADMIN_PASS})
        self._token = r.headers.get("Token")

    def _h(self) -> dict[str, str]:
        if not self._token:
            self._login()
        return {"Authorization": f"Bearer {self._token}"}

    def get(self, path: str, **params) -> httpx.Response:
        r = self._client.get(path, headers=self._h(), params=params or None)
        if r.status_code == 401:
            self._login()
            r = self._client.get(path, headers=self._h(), params=params or None)
        return r

    def post(self, path: str, json: Any = None) -> httpx.Response:
        r = self._client.post(path, headers=self._h(), json=json)
        if r.status_code == 401:
            self._login()
            r = self._client.post(path, headers=self._h(), json=json)
        return r

    def team_id(self) -> str:
        if not self._team_id:
            self._team_id = self.get(f"/api/v4/teams/name/{MM_TEAM}").json()["id"]
        return self._team_id

    # --- id mapping (deterministic, stable for the workspace lifetime) ---
    def _refresh_channels(self) -> None:
        chans = self.get(f"/api/v4/teams/{self.team_id()}/channels", per_page=200).json()
        for i, c in enumerate(sorted(chans, key=lambda x: x["id"])):
            sid = self.c2s.get(c["id"]) or f"C{i:010d}"
            self.s2c[sid] = c["id"]; self.c2s[c["id"]] = sid
            self.name2c[c["name"]] = c["id"]

    def _refresh_users(self) -> None:
        users = self.get("/api/v4/users", per_page=200).json()
        for i, u in enumerate(sorted(users, key=lambda x: x["id"])):
            sid = self.u2s.get(u["id"]) or f"U{i:010d}"
            self.s2u[sid] = u["id"]; self.u2s[u["id"]] = sid
            self.uname[u["id"]] = u["username"]

    def slack_cid(self, mm_cid: str) -> str:
        if mm_cid not in self.c2s:
            self._refresh_channels()
        return self.c2s.get(mm_cid, "C" + mm_cid)

    def slack_uid(self, mm_uid: str) -> str:
        if mm_uid not in self.u2s:
            self._refresh_users()
        return self.u2s.get(mm_uid, "U" + mm_uid)

    def resolve_channel(self, ref: str) -> str | None:
        """Accept a Slack channel id (C…), a name, or #name -> mm channel id."""
        if not self.s2c:
            self._refresh_channels()
        ref = (ref or "").lstrip("#")
        if ref in self.s2c:
            return self.s2c[ref]
        if ref in self.name2c:
            return self.name2c[ref]
        # lazy refresh once more in case of a newly-created channel
        self._refresh_channels()
        return self.s2c.get(ref) or self.name2c.get(ref)

    def resolve_user(self, ref: str) -> str | None:
        if not self.s2u:
            self._refresh_users()
        if ref in self.s2u:
            return self.s2u[ref]
        self._refresh_users()
        return self.s2u.get(ref)


mm = MM()


def ts_of(create_at_ms: int) -> str:
    return f"{create_at_ms // 1000}.{create_at_ms % 1000:03d}000"


def ok(**kw) -> JSONResponse:
    return JSONResponse({"ok": True, **kw})


def err(code: str) -> JSONResponse:
    return JSONResponse({"ok": False, "error": code})


# --------------------------------------------------------------------------- param + auth helpers
async def params(request: Request) -> dict[str, Any]:
    """Collect params from query + body, robust to how slack_sdk frames requests (it can set a
    form/urlencoded content-type even on GETs with no body). Never raises."""
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
    if not tok:
        return False
    return tok == SLACK_BOT_TOKEN


# --------------------------------------------------------------------------- header scrub
@app.middleware("http")
async def neutral_headers(request: Request, call_next):
    resp = await call_next(request)
    # Remove anything that fingerprints the backend / framework.
    for h in ("server", "x-version-id", "x-request-id", "x-ratelimit-remaining"):
        if h in resp.headers:
            del resp.headers[h]
    resp.headers["server"] = "slack"
    return resp


# --------------------------------------------------------------------------- methods
def _serialize_user(u: dict) -> dict:
    return {
        "id": mm.slack_uid(u["id"]),
        "name": u.get("username"),
        "real_name": u.get("nickname") or u.get("first_name") or u.get("username"),
        "deleted": (u.get("delete_at") or 0) > 0,
        "is_bot": bool(u.get("is_bot")),
        "profile": {
            "real_name": u.get("nickname") or u.get("username"),
            "display_name": u.get("username"),
            "email": u.get("email"),
        },
    }


def _serialize_channel(c: dict) -> dict:
    return {
        "id": mm.slack_cid(c["id"]),
        "name": c.get("name"),
        "is_channel": c.get("type") == "O",
        "is_private": c.get("type") == "P",
        "is_archived": (c.get("delete_at") or 0) > 0,
        "num_members": c.get("total_msg_count") and None,  # omit noisy field
        "topic": {"value": c.get("header") or ""},
        "purpose": {"value": c.get("purpose") or ""},
    }


async def _dispatch(method: str, request: Request) -> JSONResponse:
    p = await params(request)
    if method != "api.test" and not authed(request, p):
        return err("not_authed")

    if method == "auth.test":
        me = mm.get("/api/v4/users/me").json()
        return ok(url=f"http://{request.url.hostname}/", team=MM_TEAM,
                  user=me.get("username"), team_id="T" + mm.team_id(),
                  user_id=mm.slack_uid(me["id"]))

    if method == "conversations.list":
        chans = mm.get(f"/api/v4/teams/{mm.team_id()}/channels", per_page=200).json()
        if not isinstance(chans, list):
            return err("invalid_auth")
        return ok(channels=[_serialize_channel(c) for c in chans],
                  response_metadata={"next_cursor": ""})

    if method == "conversations.info":
        mmc = mm.resolve_channel(str(p.get("channel", "")))
        if not mmc:
            return err("channel_not_found")
        c = mm.get(f"/api/v4/channels/{mmc}").json()
        return ok(channel=_serialize_channel(c))

    if method == "conversations.history":
        mmc = mm.resolve_channel(str(p.get("channel", "")))
        if not mmc:
            return err("channel_not_found")
        try:
            limit = int(p.get("limit", 100))
        except Exception:
            limit = 100
        data = mm.get(f"/api/v4/channels/{mmc}/posts", per_page=min(max(limit, 1), 200)).json()
        order = data.get("order", [])
        posts = data.get("posts", {})
        msgs = []
        for pid in order:  # MM order is newest-first, which matches Slack
            po = posts[pid]
            msgs.append({"type": "message", "user": mm.slack_uid(po["user_id"]),
                         "text": po.get("message", ""), "ts": ts_of(po["create_at"])})
        return ok(messages=msgs, has_more=False, response_metadata={"next_cursor": ""})

    if method == "search.messages":
        query = str(p.get("query", p.get("terms", "")))
        body = {"terms": query, "is_or_search": False}
        data = mm.post(f"/api/v4/teams/{mm.team_id()}/posts/search", json=body).json()
        order = data.get("order", [])
        posts = data.get("posts", {})
        matches = []
        for pid in order:
            po = posts[pid]
            matches.append({"type": "message", "user": mm.slack_uid(po["user_id"]),
                            "text": po.get("message", ""), "ts": ts_of(po["create_at"]),
                            "channel": {"id": mm.slack_cid(po["channel_id"])}})
        return ok(query=query, messages={"total": len(matches), "matches": matches})

    if method == "users.list":
        users = mm.get("/api/v4/users", per_page=200).json()
        return ok(members=[_serialize_user(u) for u in users],
                  response_metadata={"next_cursor": ""})

    if method == "users.info":
        mmu = mm.resolve_user(str(p.get("user", "")))
        if not mmu:
            return err("user_not_found")
        u = mm.get(f"/api/v4/users/{mmu}").json()
        return ok(user=_serialize_user(u))

    if method == "chat.postMessage":
        mmc = mm.resolve_channel(str(p.get("channel", "")))
        if not mmc:
            return err("channel_not_found")
        text = str(p.get("text", ""))
        r = mm.post("/api/v4/posts", json={"channel_id": mmc, "message": text})
        if r.status_code >= 300:
            return err("cannot_post")
        po = r.json()
        return ok(channel=mm.slack_cid(mmc), ts=ts_of(po["create_at"]),
                  message={"type": "message", "user": mm.slack_uid(po["user_id"]),
                           "text": po.get("message", ""), "ts": ts_of(po["create_at"])})

    return err("unknown_method")


# Slack accepts GET and POST on /api/<method>.
@app.api_route("/api/{method}", methods=["GET", "POST"])
async def slack_method(method: str, request: Request) -> JSONResponse:
    try:
        return await _dispatch(method, request)
    except Exception:
        return err("internal_error")


# A neutral root so a probing agent doesn't get a framework page.
@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)


# Slack-shaped responses for any unmatched path (e.g. probes at /api/v4/...), so the default
# FastAPI {"detail":"Not Found"} body doesn't fingerprint the framework.
@app.exception_handler(StarletteHTTPException)
async def _http_exc(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "unknown_method" if exc.status_code == 404 else "error"
    return JSONResponse({"ok": False, "error": code}, status_code=exc.status_code)
