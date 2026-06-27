"""FastAPI app implementing a subset of the Google Workspace REST APIs.

Drive v3, Docs v1, Calendar v3, and Gmail v1, served from one host (the clients
are pointed here):

  GET /drive/v3/files                          → {kind:"drive#fileList", files:[...]}  (?q= full grammar, ?pageSize=)
  GET /drive/v3/files/{fileId}                 → a Drive file resource (?alt=media → text content)
  GET /drive/v3/files/{fileId}/export          → the file's content as text (?mimeType=)
  GET /v1/documents/{documentId}               → a Docs document (body = structural-element tree)
  GET /calendar/v3/calendars/{calId}/events    → {kind:"calendar#events", items:[...]}  (?q=, ?timeMin=, ?timeMax=)
  GET /calendar/v3/calendars/{calId}/events/{eventId} → a Calendar event
  GET /gmail/v1/users/{userId}/messages        → {messages:[{id, threadId}], ...}  (?q=)
  GET /gmail/v1/users/{userId}/messages/{id}   → a Gmail message (payload.headers + base64url body)
  GET /gmail/v1/users/{userId}/threads/{id}    → a Gmail thread (its messages, chronological)
  GET /health                                  ; token-gated /_control/*

Auth mirrors Google's OAuth bearer: requests must carry a non-empty
``Authorization: Bearer …`` (or ``access_token`` / ``key`` query). Errors mirror
Google's ``{"error": {"code", "message", "status"}}`` body with the matching HTTP
status (e.g. 404 NOT_FOUND, 401 UNAUTHENTICATED).
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from .. import store
from ..store import QueryError
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
            try:
                files = store.list_files(s, q, _int(pageSize, 100))
            except QueryError as e:
                raise GoogleError(400, f"Invalid query: {e}")
        return {"kind": "drive#fileList", "incompleteSearch": False, "files": files}

    @app.get("/drive/v3/files/{file_id}")
    def files_get(file_id: str, alt: str | None = None, fields: str | None = None,
                  _tok: str = Depends(auth)):
        with Session() as s:
            f = store.get_file(s, file_id)
            if not f:
                raise GoogleError(404, f"File not found: {file_id}.")
            if alt == "media":  # download the file's content (Drive files.get?alt=media)
                text = store.file_text(s, file_id)
                if text is None:
                    raise GoogleError(400, "Only files with extractable text can be downloaded as media in this clone.")
                return PlainTextResponse(text)
            return store.file_resource(f)

    @app.get("/drive/v3/files/{file_id}/export")
    def files_export(file_id: str, mimeType: str = "text/plain",
                     _tok: str = Depends(auth)):
        """Export a file's content as text (Drive files.export). Returns the
        extracted plain text for any file we have a body for (Docs, .docx, .pptx,
        .txt/.html, and PDFs when text was extractable)."""
        with Session() as s:
            f = store.get_file(s, file_id)
            if not f:
                raise GoogleError(404, f"File not found: {file_id}.")
            text = store.file_text(s, file_id)
            if text is None:
                raise GoogleError(400, "This file has no extractable text to export.")
            return PlainTextResponse(text)

    # ----- Docs v1 -----
    @app.get("/v1/documents/{document_id}")
    def documents_get(document_id: str, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            d = store.get_document(s, document_id)
            if not d:
                raise GoogleError(404, f"Requested entity was not found.")
            return store.document_resource(d)

    # ----- Calendar v3 -----
    @app.get("/calendar/v3/calendars/{calendar_id}/events")
    def events_list(calendar_id: str, q: str | None = None, timeMin: str | None = None,
                    timeMax: str | None = None, maxResults: str | None = None,
                    _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            items = store.list_events(s, calendar_id, q, timeMin, timeMax)
        items = items[: _int(maxResults, 250)]
        return {"kind": "calendar#events", "summary": calendar_id, "items": items}

    @app.get("/calendar/v3/calendars/{calendar_id}/events/{event_id}")
    def events_get(calendar_id: str, event_id: str, _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            e = store.get_event(s, event_id)
            if not e or (calendar_id and e.calendar_id != calendar_id):
                raise GoogleError(404, "Not Found")
            return store.event_resource(e)

    # ----- Gmail v1 -----
    @app.get("/gmail/v1/users/{user_id}/messages")
    def messages_list(user_id: str, q: str | None = None, maxResults: str | None = None,
                      _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            try:
                msgs = store.list_messages(s, q, _int(maxResults, 100))
            except QueryError as e:
                raise GoogleError(400, f"Invalid query: {e}")
            refs = [{"id": m.id, "threadId": m.thread_id} for m in msgs]
        return {"messages": refs, "resultSizeEstimate": len(refs)}

    @app.get("/gmail/v1/users/{user_id}/messages/{message_id}")
    def messages_get(user_id: str, message_id: str, format: str = "full",
                     _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            m = store.get_message(s, message_id)
            if not m:
                raise GoogleError(404, "Not Found")
            return store.message_resource(m, format)

    @app.get("/gmail/v1/users/{user_id}/threads/{thread_id}")
    def threads_get(user_id: str, thread_id: str, format: str = "full",
                    _tok: str = Depends(auth)) -> dict:
        with Session() as s:
            msgs = store.thread_messages(s, thread_id)
            if not msgs:
                raise GoogleError(404, "Not Found")
            return {"id": thread_id, "messages": [store.message_resource(m, format) for m in msgs]}

    return app


app = create_app()
