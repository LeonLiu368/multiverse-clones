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

    return mcp


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
