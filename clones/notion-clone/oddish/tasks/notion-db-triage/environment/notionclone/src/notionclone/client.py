"""The shared HTTP client — the single seam the CLI and the MCP server both import.

Both surfaces (``notion-cli``, ``notion-mcp``) are thin clients of the one HTTP API
(``$NOTION_API_URL``, default http://localhost:3000), authenticated with the
integration token (``$NOTION_TOKEN``) and ``Notion-Version`` header. Keeping the
request logic here — and *only* here — is what makes CLI⇄MCP parity hold by
construction: one capability is one ``NotionClient`` method, called identically
from both.

``_transport()`` is factored out so tests can route the client through an
in-process ASGI app (``httpx.ASGITransport``) instead of a real network server,
proving parity without sockets.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

NOTION_VERSION = "2022-06-28"


def api_base() -> str:
    return os.environ.get("NOTION_API_URL", "http://localhost:3000").rstrip("/")


def token() -> str:
    return os.environ.get("NOTION_TOKEN", "notion-clone-token")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token()}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


class NotionAPIError(RuntimeError):
    """A non-2xx response carrying Notion's ``{"object":"error", ...}`` body."""

    def __init__(self, status: int, body: dict | str) -> None:
        self.status = status
        self.body = body
        code = body.get("code") if isinstance(body, dict) else None
        message = body.get("message") if isinstance(body, dict) else str(body)
        super().__init__(f"{status} {code}: {message}")


class NotionClient:
    """Thin sync client. One method per covered capability — the parity seam."""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 json_body: dict | None = None) -> dict:
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        with httpx.Client(base_url=api_base(), headers=_headers(), timeout=30,
                          transport=self._transport) as c:
            r = c.request(method, path, params=clean, json=json_body)
        try:
            data = r.json()
        except Exception:
            raise NotionAPIError(r.status_code, r.text)
        if r.status_code >= 400 or (isinstance(data, dict) and data.get("object") == "error"):
            raise NotionAPIError(r.status_code, data)
        return data

    # ---- pages ----
    def get_page(self, page_id: str) -> dict:
        return self._request("GET", f"/v1/pages/{page_id}")

    def create_page(self, parent: dict, properties: dict, *, children: list | None = None,
                    icon: dict | None = None, cover: dict | None = None) -> dict:
        body: dict[str, Any] = {"parent": parent, "properties": properties}
        if children:
            body["children"] = children
        if icon:
            body["icon"] = icon
        if cover:
            body["cover"] = cover
        return self._request("POST", "/v1/pages", json_body=body)

    def update_page(self, page_id: str, *, properties: dict | None = None,
                    archived: bool | None = None) -> dict:
        body: dict[str, Any] = {}
        if properties is not None:
            body["properties"] = properties
        if archived is not None:
            body["archived"] = archived
        return self._request("PATCH", f"/v1/pages/{page_id}", json_body=body)

    # ---- blocks ----
    def get_block_children(self, block_id: str, *, page_size: int | None = None,
                           start_cursor: str | None = None) -> dict:
        return self._request("GET", f"/v1/blocks/{block_id}/children",
                             params={"page_size": page_size, "start_cursor": start_cursor})

    def append_block_children(self, block_id: str, children: list) -> dict:
        return self._request("PATCH", f"/v1/blocks/{block_id}/children",
                             json_body={"children": children})

    # ---- databases ----
    def get_database(self, database_id: str) -> dict:
        return self._request("GET", f"/v1/databases/{database_id}")

    def query_database(self, database_id: str, *, filter_obj: dict | None = None,
                       sorts: list | None = None, page_size: int | None = None,
                       start_cursor: str | None = None) -> dict:
        body: dict[str, Any] = {}
        if filter_obj is not None:
            body["filter"] = filter_obj
        if sorts is not None:
            body["sorts"] = sorts
        if page_size is not None:
            body["page_size"] = page_size
        if start_cursor is not None:
            body["start_cursor"] = start_cursor
        return self._request("POST", f"/v1/databases/{database_id}/query", json_body=body)

    # ---- search ----
    def search(self, query: str = "", *, object_type: str | None = None,
               sort_direction: str | None = None, page_size: int | None = None,
               start_cursor: str | None = None) -> dict:
        body: dict[str, Any] = {"query": query}
        if object_type:
            body["filter"] = {"property": "object", "value": object_type}
        if sort_direction:
            body["sort"] = {"direction": sort_direction, "timestamp": "last_edited_time"}
        if page_size is not None:
            body["page_size"] = page_size
        if start_cursor is not None:
            body["start_cursor"] = start_cursor
        return self._request("POST", "/v1/search", json_body=body)

    # ---- comments ----
    def list_comments(self, block_id: str, *, page_size: int | None = None,
                      start_cursor: str | None = None) -> dict:
        return self._request("GET", "/v1/comments",
                             params={"block_id": block_id, "page_size": page_size,
                                     "start_cursor": start_cursor})

    def create_comment(self, page_id: str, rich_text: list, *,
                       discussion_id: str | None = None) -> dict:
        body: dict[str, Any] = {"rich_text": rich_text}
        if discussion_id:
            body["discussion_id"] = discussion_id
        else:
            body["parent"] = {"page_id": page_id}
        return self._request("POST", "/v1/comments", json_body=body)

    # ---- users ----
    def list_users(self, *, page_size: int | None = None, start_cursor: str | None = None) -> dict:
        return self._request("GET", "/v1/users",
                             params={"page_size": page_size, "start_cursor": start_cursor})

    def get_user(self, user_id: str) -> dict:
        return self._request("GET", f"/v1/users/{user_id}")

    def me(self) -> dict:
        return self._request("GET", "/v1/users/me")


def rich_text(content: str) -> list[dict]:
    """Convenience: a one-run rich-text array (shared by CLI + MCP)."""
    return [{"type": "text", "text": {"content": content}}]
