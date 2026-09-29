"""FastAPI app implementing a subset of the Figma REST API.

Endpoints live under ``/v1/...`` with the real Figma paths and shapes:

  GET  /v1/files/{key}                      → document tree + components/styles
  GET  /v1/files/{key}/nodes?ids=1:2,1:3    → specific subtrees
  GET  /v1/files/{key}/comments             → comments
  POST /v1/files/{key}/comments             → create a comment (agent write surface)
  DELETE /v1/files/{key}/comments/{id}
  GET  /v1/files/{key}/components | /component_sets | /styles
  GET  /v1/files/{key}/versions
  GET  /v1/images/{key}?ids=1:2&format=png  → node → rendered PNG url
  GET  /v1/teams/{team_id}/projects
  GET  /v1/projects/{project_id}/files

Auth mirrors Figma's personal-access-token header: requests must carry a non-empty
``X-Figma-Token`` (or ``Authorization: Bearer …``). Errors mirror Figma's
``{"status": <code>, "err": "<message>"}`` body with the matching HTTP status.
"""

from __future__ import annotations

import io
import os
import struct
import zlib
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from .. import store
from ..db import get_engine, init_db, session_factory


class FigmaError(HTTPException):
    """An error rendered as Figma's ``{"status", "err"}`` body."""

    def __init__(self, status: int, err: str) -> None:
        super().__init__(status_code=status, detail=err)


def create_app(db_path: str | None = None) -> FastAPI:
    engine = get_engine(db_path)
    init_db(engine)
    Session = session_factory(engine)
    app = FastAPI(title="abundant-figma-clone", version="0.1.0")

    # Operator/harness-only control plane (seed/reset). Token-gated; routes 404
    # unless FIGMA_CONTROL_TOKEN is set AND X-Control-Token matches. The agent's
    # client container is never given the token.
    from .control import make_control_router

    app.include_router(make_control_router(engine))

    require_token = os.environ.get("FIGMA_REQUIRE_TOKEN", "1") != "0"

    def auth(
        x_figma_token: str | None = Header(None),
        authorization: str | None = Header(None),
    ) -> str:
        """Validate the Figma access token header (presence == valid, like a PAT)."""
        token = x_figma_token
        if not token and authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        if require_token and not token:
            raise FigmaError(403, "Invalid token")
        return token or ""

    @app.exception_handler(FigmaError)
    async def _figma_error_handler(_req: Request, exc: FigmaError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"status": exc.status_code, "err": exc.detail})

    @app.exception_handler(HTTPException)
    async def _http_error_handler(_req: Request, exc: HTTPException) -> JSONResponse:
        # Non-Figma HTTPExceptions (e.g. 404 from control plane) keep FastAPI default
        if isinstance(exc, FigmaError):
            return await _figma_error_handler(_req, exc)
        return JSONResponse(status_code=exc.status_code, content={"status": exc.status_code, "err": str(exc.detail)})

    def _file_or_404(s, key: str):
        f = store.get_file(s, key)
        if not f:
            raise FigmaError(404, "Not found")
        return f

    def _int(v: Any) -> int | None:
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    # --------------------------------------------------------------- meta
    @app.get("/health")
    def health() -> dict:
        return {"status": "healthy"}

    @app.get("/v1/me")
    def me(_tok: str = Depends(auth)) -> dict:
        return {"id": "U_AGENT", "handle": "agent", "email": "agent@figma-clone.local", "img_url": ""}

    # --------------------------------------------------------------- files
    @app.get("/v1/files/{key}")
    def get_file(key: str, request: Request, ids: str | None = None, depth: str | None = None,
                 geometry: str | None = None, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            f = _file_or_404(s, key)
            if ids:
                return store.file_nodes_response(s, f, _split_ids(ids), depth=_int(depth))
            return store.file_response(s, f, depth=_int(depth), geometry=geometry)

    @app.get("/v1/files/{key}/nodes")
    def get_file_nodes(key: str, ids: str | None = None, depth: str | None = None,
                       _tok: str = Depends(auth)) -> dict:
        if not ids:
            raise FigmaError(400, "ids is required")
        with Session() as s:
            f = _file_or_404(s, key)
            return store.file_nodes_response(s, f, _split_ids(ids), depth=_int(depth))

    # --------------------------------------------------------------- comments
    @app.get("/v1/files/{key}/comments")
    def get_comments(key: str, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            _file_or_404(s, key)
            return {"comments": store.list_comments(s, key)}

    @app.post("/v1/files/{key}/comments")
    async def post_comment(key: str, request: Request, x_figma_token: str | None = Header(None),
                           authorization: str | None = Header(None)) -> dict:
        auth(x_figma_token, authorization)
        try:
            body = await request.json()
        except Exception:
            body = {}
        message = (body or {}).get("message", "")
        if not message:
            raise FigmaError(400, "message is required")
        with Session() as s:
            _file_or_404(s, key)
            return store.post_comment(
                s, key, message,
                client_meta=(body or {}).get("client_meta"),
                comment_id=(body or {}).get("comment_id"),
            )

    @app.delete("/v1/files/{key}/comments/{comment_id}")
    def delete_comment(key: str, comment_id: str, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            _file_or_404(s, key)
            if not store.delete_comment(s, key, comment_id):
                raise FigmaError(404, "Not found")
            return {"status": 200}

    # --------------------------------------------------------------- components / styles
    @app.get("/v1/files/{key}/components")
    def get_components(key: str, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            f = _file_or_404(s, key)
            return {"meta": {"components": store.components_meta(f)}}

    @app.get("/v1/files/{key}/component_sets")
    def get_component_sets(key: str, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            f = _file_or_404(s, key)
            return {"meta": {"component_sets": store.component_sets_meta(f)}}

    @app.get("/v1/files/{key}/styles")
    def get_styles(key: str, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            f = _file_or_404(s, key)
            return {"meta": {"styles": store.styles_meta(f)}}

    # --------------------------------------------------------------- versions
    @app.get("/v1/files/{key}/versions")
    def get_versions(key: str, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            _file_or_404(s, key)
            return {"versions": store.list_versions(s, key),
                    "pagination": {"next_page": None, "prev_page": None}}

    # --------------------------------------------------------------- images
    @app.get("/v1/images/{key}")
    def get_images(key: str, request: Request, ids: str | None = None, format: str = "png",
                   scale: str | None = None, _tok: str = Depends(auth)) -> dict:
        if not ids:
            raise FigmaError(400, "ids is required")
        base = str(request.base_url)
        with Session() as s:
            f = _file_or_404(s, key)
            return store.images_response(f, _split_ids(ids), base)

    # --------------------------------------------------------------- teams / projects
    @app.get("/v1/teams/{team_id}/projects")
    def get_projects(team_id: str, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            res = store.list_projects(s, team_id)
            if res is None:
                raise FigmaError(404, "Not found")
            return res

    @app.get("/v1/projects/{project_id}/files")
    def get_project_files(project_id: str, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            res = store.list_project_files(s, project_id)
            if res is None:
                raise FigmaError(404, "Not found")
            return res

    # --------------------------------------------------------------- static images
    # Pre-baked render URLs in the seed point at /static/...; serve a 1x1 PNG
    # placeholder so any image URL resolves. The node tree is the source of truth;
    # pixels are not graded.
    _PNG = _placeholder_png()

    @app.get("/static/{path:path}")
    def static_png(path: str) -> Response:
        return Response(content=_PNG, media_type="image/png")

    return app


def _split_ids(ids: str) -> list[str]:
    from ..ids import normalize_node_id
    return [normalize_node_id(s.strip()) for s in ids.split(",") if s.strip()]


def _placeholder_png() -> bytes:
    """A 1x1 transparent PNG, built without external assets."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    raw = b"\x00\x00\x00\x00\x00"  # one filtered scanline of a transparent RGBA pixel
    idat = zlib.compress(raw)
    buf = io.BytesIO()
    buf.write(sig)
    buf.write(chunk(b"IHDR", ihdr))
    buf.write(chunk(b"IDAT", idat))
    buf.write(chunk(b"IEND", b""))
    return buf.getvalue()


# module-level app for `uvicorn figmaclone.api.app:app`
app = create_app()
