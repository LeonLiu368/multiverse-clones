"""stdio MCP server exposing the gworkspace API as MCP tools (thin clients).

Same operations as `gws-cli`; the derived doc tools walk the body locally via the
shared `store` helpers, so CLI and MCP stay in lockstep.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from ..store import document_text, iter_paragraphs


def api_base() -> str:
    return os.environ.get("GWS_API_URL", "http://localhost:8080").rstrip("/")


def _token() -> str:
    return os.environ.get("GWS_TOKEN", "gws-clone-token")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=api_base(),
                             headers={"Authorization": f"Bearer {_token()}"}, timeout=30)


async def _get(path: str, **params: Any) -> dict:
    clean = {k: v for k, v in params.items() if v is not None}
    async with _client() as c:
        r = await c.get(path, params=clean)
        return r.json()


def build_server() -> FastMCP:
    mcp = FastMCP("abundant-gworkspace-clone")

    @mcp.tool()
    async def gws_list_files(q: str | None = None) -> dict:
        """List Drive files. Optional `q` (Drive query, e.g. \"name contains 'plan'\")."""
        return await _get("/drive/v3/files", q=q)

    @mcp.tool()
    async def gws_get_file(file_id: str) -> dict:
        """Get a Drive file's metadata."""
        return await _get(f"/drive/v3/files/{file_id}")

    @mcp.tool()
    async def gws_get_document(document_id: str) -> dict:
        """Get a Google Doc (full structural body)."""
        return await _get(f"/v1/documents/{document_id}")

    @mcp.tool()
    async def gws_get_file_text(file_id: str) -> str:
        """Read a Drive file's text content (Docs, .docx/.pptx, .txt/.html, PDFs).

        Use this for non-Google-Doc files where `gws_get_document_text` doesn't
        apply — it exports the extracted plain text."""
        async with _client() as c:
            r = await c.get(f"/drive/v3/files/{file_id}/export")
            if r.status_code >= 400:
                try:
                    return f"error: {r.json().get('error', {}).get('message', r.status_code)}"
                except Exception:
                    return f"error: HTTP {r.status_code}"
            return r.text

    @mcp.tool()
    async def gws_get_document_text(document_id: str) -> str:
        """Get a Google Doc's plain text content."""
        body = (await _get(f"/v1/documents/{document_id}")).get("body", {})
        return document_text(body)

    @mcp.tool()
    async def gws_search_document(document_id: str, query: str) -> list[dict]:
        """Find paragraphs in a Doc containing the query (case-insensitive)."""
        body = (await _get(f"/v1/documents/{document_id}")).get("body", {})
        ql = query.lower()
        return [{"style": st, "text": t.strip()} for st, t in iter_paragraphs(body) if ql in t.lower()]

    # ----- Calendar -----
    @mcp.tool()
    async def gws_list_events(calendar_id: str = "primary", q: str | None = None,
                              time_min: str | None = None, time_max: str | None = None) -> dict:
        """List Calendar events. Optional free-text `q` and RFC-3339 `time_min`/`time_max` on the start."""
        return await _get(f"/calendar/v3/calendars/{calendar_id}/events",
                          q=q, timeMin=time_min, timeMax=time_max)

    @mcp.tool()
    async def gws_get_event(event_id: str, calendar_id: str = "primary") -> dict:
        """Get a single Calendar event."""
        return await _get(f"/calendar/v3/calendars/{calendar_id}/events/{event_id}")

    # ----- Gmail -----
    @mcp.tool()
    async def gws_search_messages(q: str | None = None, user_id: str = "me") -> dict:
        """Search Gmail. `q` supports from:/to:/subject:/label: + free-text (e.g. \"from:bob launch\")."""
        return await _get(f"/gmail/v1/users/{user_id}/messages", q=q)

    @mcp.tool()
    async def gws_get_message(message_id: str, user_id: str = "me") -> dict:
        """Get a Gmail message (headers + decoded plaintext body)."""
        m = await _get(f"/gmail/v1/users/{user_id}/messages/{message_id}")
        m["bodyText"] = _decode_gmail_body(m)
        return m

    @mcp.tool()
    async def gws_get_thread(thread_id: str, user_id: str = "me") -> dict:
        """Get a Gmail thread (all messages, chronological, with decoded bodies)."""
        t = await _get(f"/gmail/v1/users/{user_id}/threads/{thread_id}")
        for m in t.get("messages", []):
            m["bodyText"] = _decode_gmail_body(m)
        return t

    return mcp


def _decode_gmail_body(message: dict) -> str:
    import base64
    data = (message.get("payload", {}).get("body", {}) or {}).get("data", "")
    if not data:
        return message.get("snippet", "")
    return base64.urlsafe_b64decode(data.encode()).decode(errors="replace")


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
