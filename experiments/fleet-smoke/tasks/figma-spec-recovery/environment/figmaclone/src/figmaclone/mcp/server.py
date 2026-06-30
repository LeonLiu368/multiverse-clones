"""stdio MCP server exposing the Figma-clone API as MCP tools.

Each tool is a thin pass-through to ``$FIGMA_API_URL/v1/...`` with the
``X-Figma-Token`` header. The derived tools (``figma_get_text``,
``figma_inspect_node``, ``figma_search_nodes``) fetch the file once and walk the
node tree locally — mirroring ``figma-cli`` exactly, so the CLI and MCP stay in
lockstep because both call the same HTTP surface and share the same walk helpers.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from ..store import find_node, iter_nodes


def api_base() -> str:
    return os.environ.get("FIGMA_API_URL", "http://localhost:3000").rstrip("/")


def _token() -> str:
    return os.environ.get("FIGMA_TOKEN", "figma-clone-token")


def _client() -> httpx.AsyncClient:
    """The httpx client used for API calls.

    Factored out so tests can monkeypatch it to route through an in-process ASGI
    app (``httpx.ASGITransport``) instead of a real network server.
    """
    return httpx.AsyncClient(base_url=api_base(), headers={"X-Figma-Token": _token()}, timeout=30)


async def _get(path: str, **params: Any) -> dict:
    clean = {k: v for k, v in params.items() if v is not None}
    async with _client() as client:
        r = await client.get(path, params=clean)
        return r.json()


async def _post(path: str, body: dict) -> dict:
    async with _client() as client:
        r = await client.post(path, json=body)
        return r.json()


async def _delete(path: str) -> dict:
    async with _client() as client:
        r = await client.delete(path)
        return r.json()


async def _document(file_key: str) -> dict:
    data = await _get(f"/v1/files/{file_key}")
    return data.get("document", {})


def build_server() -> FastMCP:
    mcp = FastMCP("abundant-figma-clone")

    # ---- file reads ----
    @mcp.tool()
    async def figma_get_file(file_key: str, depth: int | None = None) -> dict:
        """Fetch a file's document tree, components and styles. Use depth to limit nesting."""
        return await _get(f"/v1/files/{file_key}", depth=depth)

    @mcp.tool()
    async def figma_get_nodes(file_key: str, ids: str) -> dict:
        """Fetch specific node subtrees by id (comma-separated, e.g. '1:2,1:3')."""
        return await _get(f"/v1/files/{file_key}/nodes", ids=ids)

    # ---- derived reads (local node-tree walk) ----
    @mcp.tool()
    async def figma_get_text(file_key: str) -> list[dict]:
        """Extract every TEXT node's characters as [{id, name, characters}]."""
        doc = await _document(file_key)
        return [{"id": n.get("id"), "name": n.get("name"), "characters": n.get("characters", "")}
                for n in iter_nodes(doc) if n.get("type") == "TEXT"]

    @mcp.tool()
    async def figma_inspect_node(file_key: str, node_id: str) -> dict:
        """Inspect one node: type, fills, style, characters, layout, cornerRadius, bbox."""
        n = find_node(await _document(file_key), node_id)
        if n is None:
            return {"err": "node_not_found", "node_id": node_id}
        keep = ("id", "name", "type", "characters", "fills", "strokes", "style", "cornerRadius",
                "layoutMode", "itemSpacing", "paddingLeft", "paddingRight", "paddingTop",
                "paddingBottom", "primaryAxisAlignItems", "counterAxisAlignItems", "absoluteBoundingBox")
        return {k: n[k] for k in keep if k in n}

    @mcp.tool()
    async def figma_search_nodes(file_key: str, query: str) -> list[dict]:
        """Find nodes whose name or text contains the query (case-insensitive)."""
        q = query.lower()
        out = []
        for n in iter_nodes(await _document(file_key)):
            name, chars = str(n.get("name", "")), str(n.get("characters", ""))
            if q in name.lower() or q in chars.lower():
                out.append({"id": n.get("id"), "type": n.get("type"), "name": name,
                            "characters": chars or None})
        return out

    # ---- comments ----
    @mcp.tool()
    async def figma_list_comments(file_key: str) -> dict:
        """List comments on a file."""
        return await _get(f"/v1/files/{file_key}/comments")

    @mcp.tool()
    async def figma_post_comment(file_key: str, message: str, node_id: str | None = None,
                                 reply_to: str | None = None) -> dict:
        """Post a comment, optionally anchored to a node (node_id) or as a reply (reply_to)."""
        body: dict[str, Any] = {"message": message}
        if node_id:
            body["client_meta"] = {"node_id": node_id}
        if reply_to:
            body["comment_id"] = reply_to
        return await _post(f"/v1/files/{file_key}/comments", body)

    @mcp.tool()
    async def figma_delete_comment(file_key: str, comment_id: str) -> dict:
        """Delete a comment (or reply) by id from a file."""
        return await _delete(f"/v1/files/{file_key}/comments/{comment_id}")

    # ---- components / styles / versions / images ----
    @mcp.tool()
    async def figma_list_components(file_key: str) -> dict:
        """List the published components in a file."""
        return await _get(f"/v1/files/{file_key}/components")

    @mcp.tool()
    async def figma_list_component_sets(file_key: str) -> dict:
        """List the published component sets (variant groups) in a file."""
        return await _get(f"/v1/files/{file_key}/component_sets")

    @mcp.tool()
    async def figma_list_styles(file_key: str) -> dict:
        """List the color/text/effect styles (design tokens) in a file."""
        return await _get(f"/v1/files/{file_key}/styles")

    @mcp.tool()
    async def figma_list_versions(file_key: str) -> dict:
        """List a file's version history."""
        return await _get(f"/v1/files/{file_key}/versions")

    @mcp.tool()
    async def figma_get_images(file_key: str, ids: str, img_format: str = "png") -> dict:
        """Get rendered image URLs for node ids (comma-separated)."""
        return await _get(f"/v1/images/{file_key}", ids=ids, format=img_format)

    # ---- teams / projects / identity ----
    @mcp.tool()
    async def figma_list_projects(team_id: str) -> dict:
        """List the projects in a team."""
        return await _get(f"/v1/teams/{team_id}/projects")

    @mcp.tool()
    async def figma_list_project_files(project_id: str) -> dict:
        """List the files in a project."""
        return await _get(f"/v1/projects/{project_id}/files")

    @mcp.tool()
    async def figma_me() -> dict:
        """Get the authenticated user's profile (id, handle, email)."""
        return await _get("/v1/me")

    return mcp


def main() -> None:
    """Entry point: run the MCP server over stdio."""
    build_server().run()


if __name__ == "__main__":
    main()
