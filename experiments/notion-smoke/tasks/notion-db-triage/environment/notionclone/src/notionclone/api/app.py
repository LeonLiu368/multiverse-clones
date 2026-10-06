"""FastAPI app implementing the agent-used subset of the Notion API.

Endpoints live under ``/v1/...`` with the real Notion paths, envelopes and errors:

  GET   /v1/pages/{id}                       → page object
  POST  /v1/pages                            → create a page
  PATCH /v1/pages/{id}                       → update properties / archive
  GET   /v1/blocks/{id}/children             → list child blocks (paginated)
  PATCH /v1/blocks/{id}/children             → append child blocks
  GET   /v1/databases/{id}                   → database (schema) object
  POST  /v1/databases/{id}/query             → query with filter + sorts (T2)
  POST  /v1/search                           → search pages/databases by title
  GET   /v1/comments?block_id=…              → list comments on a page
  POST  /v1/comments                         → create a comment
  GET   /v1/users                            → list users
  GET   /v1/users/{id}                       → retrieve a user
  GET   /v1/users/me                         → the bot/integration user

Auth mirrors Notion's integration token: requests carry
``Authorization: Bearer <token>`` and ``Notion-Version: <date>``. Presence of a
token == valid (like a real integration secret). Errors mirror Notion's
``{"object":"error","status":<code>,"code":"<code>","message":"…"}`` body with the
matching HTTP status.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .. import store
from ..db import get_engine, init_db, session_factory
from ..store import QueryError

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 100


class NotionError(HTTPException):
    """An error rendered as Notion's ``{"object":"error", ...}`` body."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(status_code=status, detail=message)
        self.code = code


def _err_body(status: int, code: str, message: str) -> dict:
    return {"object": "error", "status": status, "code": code, "message": message,
            "request_id": store.gen_uuid()}


def create_app(db_path: str | None = None) -> FastAPI:
    engine = get_engine(db_path)
    init_db(engine)
    Session = session_factory(engine)
    app = FastAPI(title="abundant-notion-clone", version="0.1.0")

    from .control import make_control_router
    app.include_router(make_control_router(engine))

    require_token = os.environ.get("NOTION_REQUIRE_TOKEN", "1") != "0"

    def auth(authorization: str | None = Header(None),
             notion_version: str | None = Header(None)) -> str:
        token = ""
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        if require_token and not token:
            raise NotionError(401, "unauthorized", "API token is invalid.")
        return token

    @app.exception_handler(NotionError)
    async def _notion_error_handler(_req: Request, exc: NotionError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code,
                            content=_err_body(exc.status_code, exc.code, str(exc.detail)))

    @app.exception_handler(QueryError)
    async def _query_error_handler(_req: Request, exc: QueryError) -> JSONResponse:
        return JSONResponse(status_code=400,
                            content=_err_body(400, "validation_error", str(exc)))

    @app.exception_handler(HTTPException)
    async def _http_error_handler(_req: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc, NotionError):
            return await _notion_error_handler(_req, exc)
        # control-plane 404s etc. keep a generic shape
        return JSONResponse(status_code=exc.status_code,
                            content=_err_body(exc.status_code, "error", str(exc.detail)))

    def _page_size(v: Any) -> int:
        try:
            n = int(v)
        except (TypeError, ValueError):
            return DEFAULT_PAGE_SIZE
        return max(1, min(n, MAX_PAGE_SIZE))

    # --------------------------------------------------------------- meta
    @app.get("/health")
    def health() -> dict:
        return {"status": "healthy"}

    # --------------------------------------------------------------- users
    @app.get("/v1/users/me")
    def users_me(_tok: str = Depends(auth)) -> dict:
        with Session() as s:
            bot = next((u for u in s.query(store.User).all() if u.type == "bot"), None)
            if bot:
                return store.user_dict(bot)
        return {"object": "user", "id": "00000000-0000-4000-8000-000000000000",
                "name": "Integration", "type": "bot", "bot": {}}

    @app.get("/v1/users/{user_id}")
    def users_retrieve(user_id: str, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            u = store.get_user(s, user_id)
            if u is None:
                raise NotionError(404, "object_not_found",
                                  f"Could not find user with ID: {user_id}.")
            return store.user_dict(u)

    @app.get("/v1/users")
    def users_list(start_cursor: str | None = None, page_size: int | None = None,
                   _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            try:
                return store.list_users(s, _page_size(page_size), start_cursor)
            except ValueError:
                raise NotionError(400, "validation_error", "The start_cursor provided is invalid.")

    # --------------------------------------------------------------- pages
    @app.get("/v1/pages/{page_id}")
    def page_retrieve(page_id: str, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            p = store.get_page(s, page_id)
            if p is None:
                raise NotionError(404, "object_not_found",
                                  f"Could not find page with ID: {page_id}.")
            return store.page_dict(p)

    @app.post("/v1/pages")
    async def page_create(request: Request, x_actor: str | None = Header(None),
                          authorization: str | None = Header(None),
                          notion_version: str | None = Header(None)) -> dict:
        auth(authorization, notion_version)
        body = await _json(request)
        parent = body.get("parent")
        if not parent or not isinstance(parent, dict):
            raise NotionError(400, "validation_error", "body failed validation: body.parent should be defined.")
        with Session() as s:
            if parent.get("type") == "database_id" or parent.get("database_id"):
                db = store.get_database(s, parent.get("database_id", ""))
                if db is None:
                    raise NotionError(404, "object_not_found",
                                      f"Could not find database with ID: {parent.get('database_id')}.")
            elif parent.get("type") == "page_id" or parent.get("page_id"):
                if store.get_page(s, parent.get("page_id", "")) is None:
                    raise NotionError(404, "object_not_found",
                                      f"Could not find page with ID: {parent.get('page_id')}.")
            props = body.get("properties") or {}
            if not props:
                raise NotionError(400, "validation_error",
                                  "body failed validation: body.properties should be defined.")
            page = store.create_page(s, parent, props, children=body.get("children"),
                                     icon=body.get("icon"), cover=body.get("cover"),
                                     actor=x_actor or "")
            return store.page_dict(page)

    @app.patch("/v1/pages/{page_id}")
    async def page_update(page_id: str, request: Request, x_actor: str | None = Header(None),
                          authorization: str | None = Header(None),
                          notion_version: str | None = Header(None)) -> dict:
        auth(authorization, notion_version)
        body = await _json(request)
        with Session() as s:
            p = store.get_page(s, page_id)
            if p is None:
                raise NotionError(404, "object_not_found",
                                  f"Could not find page with ID: {page_id}.")
            page = store.update_page(s, p, properties=body.get("properties"),
                                     archived=body.get("archived", body.get("in_trash")),
                                     icon=body.get("icon"), cover=body.get("cover"),
                                     actor=x_actor or "")
            return store.page_dict(page)

    # --------------------------------------------------------------- blocks
    @app.get("/v1/blocks/{block_id}/children")
    def block_children(block_id: str, start_cursor: str | None = None,
                       page_size: int | None = None, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            # the parent must exist (page or block)
            if store.get_page(s, block_id) is None and s.get(store.Block, store.normalize_id(block_id)) is None:
                raise NotionError(404, "object_not_found",
                                  f"Could not find block with ID: {block_id}.")
            try:
                return store.block_children(s, block_id, _page_size(page_size), start_cursor)
            except ValueError:
                raise NotionError(400, "validation_error", "The start_cursor provided is invalid.")

    @app.patch("/v1/blocks/{block_id}/children")
    async def block_append(block_id: str, request: Request, x_actor: str | None = Header(None),
                           authorization: str | None = Header(None),
                           notion_version: str | None = Header(None)) -> dict:
        auth(authorization, notion_version)
        body = await _json(request)
        children = body.get("children")
        if not children or not isinstance(children, list):
            raise NotionError(400, "validation_error",
                              "body failed validation: body.children should be a non-empty array.")
        with Session() as s:
            if store.get_page(s, block_id) is None and s.get(store.Block, store.normalize_id(block_id)) is None:
                raise NotionError(404, "object_not_found",
                                  f"Could not find block with ID: {block_id}.")
            created = store.append_children(s, block_id, children, actor=x_actor or "")
            return store.list_envelope([store.block_dict(b) for b in created], obj_type="block")

    # --------------------------------------------------------------- databases
    @app.get("/v1/databases/{database_id}")
    def database_retrieve(database_id: str, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            d = store.get_database(s, database_id)
            if d is None:
                raise NotionError(404, "object_not_found",
                                  f"Could not find database with ID: {database_id}.")
            return store.database_dict(d)

    @app.post("/v1/databases/{database_id}/query")
    async def database_query(database_id: str, request: Request,
                             authorization: str | None = Header(None),
                             notion_version: str | None = Header(None)) -> dict:
        auth(authorization, notion_version)
        body = await _json(request)
        with Session() as s:
            try:
                res = store.query_database(
                    s, database_id, filter_obj=body.get("filter"),
                    sorts=body.get("sorts"), page_size=_page_size(body.get("page_size")),
                    start_cursor=body.get("start_cursor"))
            except QueryError:
                raise
            except ValueError:
                raise NotionError(400, "validation_error", "The start_cursor provided is invalid.")
            if res is None:
                raise NotionError(404, "object_not_found",
                                  f"Could not find database with ID: {database_id}.")
            return res

    # --------------------------------------------------------------- search
    @app.post("/v1/search")
    async def search(request: Request, authorization: str | None = Header(None),
                     notion_version: str | None = Header(None)) -> dict:
        auth(authorization, notion_version)
        body = await _json(request)
        flt = body.get("filter") or {}
        obj_filter = flt.get("value") if flt.get("property") == "object" else None
        if obj_filter not in (None, "page", "database"):
            raise NotionError(400, "validation_error",
                              "body.filter.value should be `page` or `database`.")
        sort = body.get("sort") or {}
        with Session() as s:
            return store.search(s, body.get("query", ""), obj_filter=obj_filter,
                                page_size=_page_size(body.get("page_size")),
                                start_cursor=body.get("start_cursor"),
                                sort_direction=sort.get("direction"))

    # --------------------------------------------------------------- comments
    @app.get("/v1/comments")
    def comments_list(block_id: str | None = Query(None), start_cursor: str | None = None,
                      page_size: int | None = None, _tok: str = Depends(auth)) -> dict:
        if not block_id:
            raise NotionError(400, "validation_error", "block_id is required.")
        with Session() as s:
            if store.get_page(s, block_id) is None:
                raise NotionError(404, "object_not_found",
                                  f"Could not find block with ID: {block_id}.")
            try:
                return store.list_comments(s, block_id, _page_size(page_size), start_cursor)
            except ValueError:
                raise NotionError(400, "validation_error", "The start_cursor provided is invalid.")

    @app.post("/v1/comments")
    async def comments_create(request: Request, x_actor: str | None = Header(None),
                              authorization: str | None = Header(None),
                              notion_version: str | None = Header(None)) -> dict:
        auth(authorization, notion_version)
        body = await _json(request)
        parent = body.get("parent") or {}
        rich = body.get("rich_text")
        if not rich:
            raise NotionError(400, "validation_error",
                              "body failed validation: body.rich_text should be defined.")
        page_id = parent.get("page_id") or body.get("discussion_id")
        if not parent.get("page_id") and not body.get("discussion_id"):
            raise NotionError(400, "validation_error",
                              "body failed validation: provide parent.page_id or discussion_id.")
        with Session() as s:
            if parent.get("page_id") and store.get_page(s, parent["page_id"]) is None:
                raise NotionError(404, "object_not_found",
                                  f"Could not find page with ID: {parent['page_id']}.")
            c = store.create_comment(s, parent, rich, discussion_id=body.get("discussion_id"),
                                     actor=x_actor or "")
            return store.comment_dict(c)

    return app


async def _json(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        body = {}
    return body if isinstance(body, dict) else {}


# module-level app for `uvicorn notionclone.api.app:app`
app = create_app()
