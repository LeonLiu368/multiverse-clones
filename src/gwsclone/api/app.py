"""FastAPI app implementing a subset of the Google Workspace REST APIs.

Drive v3 and Docs v1, served from one host (the clients are pointed here):

  GET /drive/v3/files                  → {kind:"drive#fileList", files:[...]}  (?q=, ?pageSize=)
  GET /drive/v3/files/{fileId}         → a Drive file resource
  GET /v1/documents/{documentId}       → a Docs document (body = structural-element tree)
  GET /health                          ; token-gated /_control/*

Auth mirrors Google's OAuth bearer: requests must carry a non-empty
``Authorization: Bearer …`` (or ``access_token`` / ``key`` query). Errors mirror
Google's ``{"error": {"code", "message", "status"}}`` body with the matching HTTP
status (e.g. 404 NOT_FOUND, 401 UNAUTHENTICATED).
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from .. import store
from ..db import get_engine, init_db, session_factory

_STATUS = {400: "INVALID_ARGUMENT", 401: "UNAUTHENTICATED", 403: "PERMISSION_DENIED",
           404: "NOT_FOUND", 500: "INTERNAL"}


class GoogleError(HTTPException):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(status_code=status, detail=message)


def create_app(db_path: str | None = None) -> FastAPI:
    engine = get_engine(db_path)
    init_db(engine)
    Session = session_factory(engine)
    app = FastAPI(title="abundant-gworkspace-clone", version="0.1.0")

    from .control import make_control_router
    app.include_router(make_control_router(engine))

    require_token = os.environ.get("GWS_REQUIRE_TOKEN", "1") != "0"

    def auth(authorization: str | None = Header(None),
             access_token: str | None = None, key: str | None = None) -> str:
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        token = token or access_token or key
        if require_token and not token:
            raise GoogleError(401, "Request is missing required authentication credential.")
        return token or ""

    @app.exception_handler(GoogleError)
    async def _ge(_r: Request, exc: GoogleError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={
            "error": {"code": exc.status_code, "message": exc.detail,
                      "status": _STATUS.get(exc.status_code, "ERROR")}})

    @app.exception_handler(HTTPException)
    async def _he(_r: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc, GoogleError):
            return await _ge(_r, exc)
        return JSONResponse(status_code=exc.status_code, content={
            "error": {"code": exc.status_code, "message": str(exc.detail),
                      "status": _STATUS.get(exc.status_code, "ERROR")}})

    def _int(v: Any, default: int) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    @app.get("/health")
    def health() -> dict:
        return {"status": "healthy"}

    # ----- Drive v3 -----
    @app.get("/drive/v3/files")
    def files_list(q: str | None = None, pageSize: str | None = None,
                   fields: str | None = None, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            files = store.list_files(s, q, _int(pageSize, 100))
        return {"kind": "drive#fileList", "incompleteSearch": False, "files": files}

    @app.get("/drive/v3/files/{file_id}")
    def files_get(file_id: str, fields: str | None = None, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            f = store.get_file(s, file_id)
            if not f:
                raise GoogleError(404, f"File not found: {file_id}.")
            return store.file_resource(f)

    # ----- Docs v1 -----
    @app.get("/v1/documents/{document_id}")
    def documents_get(document_id: str, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            d = store.get_document(s, document_id)
            if not d:
                raise GoogleError(404, f"Requested entity was not found.")
            return store.document_resource(d)

    return app


app = create_app()
