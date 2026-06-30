"""stdio MCP server exposing the Notion-clone API as MCP tools.

Each tool is a thin pass-through to the shared ``NotionClient`` — the SAME seam the
CLI uses — so the two surfaces stay in lockstep by construction (one capability →
one CLI command AND one MCP tool, both calling the identical client method). Tool
names mirror the official Notion MCP verbs (``notion_retrieve_page``,
``notion_query_database`` …). The control plane is never exposed.

The client is constructed per call so tests can monkeypatch ``NotionClient`` to
route through an in-process ASGI app and prove CLI⇄MCP⇄API parity without sockets.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..client import NotionAPIError, NotionClient, rich_text


def _call(fn) -> Any:
    """Run a client call, turning API errors into a structured error dict (not a raise)."""
    try:
        return fn(NotionClient())
    except NotionAPIError as e:
        return e.body if isinstance(e.body, dict) else {"object": "error", "message": str(e.body)}


def build_server() -> FastMCP:
    mcp = FastMCP("abundant-notion-clone")

    # ---- pages ----
    @mcp.tool()
    def notion_retrieve_page(page_id: str) -> dict:
        """Retrieve a page object by id (properties, parent, archived, url)."""
        return _call(lambda c: c.get_page(page_id))

    @mcp.tool()
    def notion_create_page(parent: dict, properties: dict, children: list | None = None) -> dict:
        """Create a page under a database (parent={'database_id':…}) or page parent."""
        return _call(lambda c: c.create_page(parent, properties, children=children))

    @mcp.tool()
    def notion_update_page(page_id: str, properties: dict | None = None,
                           archived: bool | None = None) -> dict:
        """Update a page's property values, or archive/restore it (archived=true/false)."""
        return _call(lambda c: c.update_page(page_id, properties=properties, archived=archived))

    # ---- blocks ----
    @mcp.tool()
    def notion_get_block_children(block_id: str, page_size: int | None = None,
                                  start_cursor: str | None = None) -> dict:
        """List the child blocks of a page or block (paginated)."""
        return _call(lambda c: c.get_block_children(block_id, page_size=page_size,
                                                    start_cursor=start_cursor))

    @mcp.tool()
    def notion_append_block_children(block_id: str, children: list) -> dict:
        """Append child blocks (array of block objects) to a page or block."""
        return _call(lambda c: c.append_block_children(block_id, children))

    # ---- databases ----
    @mcp.tool()
    def notion_retrieve_database(database_id: str) -> dict:
        """Retrieve a database object (its property schema)."""
        return _call(lambda c: c.get_database(database_id))

    @mcp.tool()
    def notion_query_database(database_id: str, filter: dict | None = None,
                              sorts: list | None = None, page_size: int | None = None,
                              start_cursor: str | None = None) -> dict:
        """Query a database with a Notion filter object and/or sorts array."""
        return _call(lambda c: c.query_database(database_id, filter_obj=filter, sorts=sorts,
                                               page_size=page_size, start_cursor=start_cursor))

    # ---- search ----
    @mcp.tool()
    def notion_search(query: str = "", object_type: str | None = None,
                      direction: str | None = None, page_size: int | None = None) -> dict:
        """Search pages and databases by title. object_type filters to 'page' or 'database'."""
        return _call(lambda c: c.search(query, object_type=object_type, sort_direction=direction,
                                       page_size=page_size))

    # ---- comments ----
    @mcp.tool()
    def notion_list_comments(block_id: str) -> dict:
        """List comments on a page (block_id is the page id)."""
        return _call(lambda c: c.list_comments(block_id))

    @mcp.tool()
    def notion_create_comment(page_id: str, message: str) -> dict:
        """Add a comment to a page."""
        return _call(lambda c: c.create_comment(page_id, rich_text(message)))

    # ---- users ----
    @mcp.tool()
    def notion_list_users(page_size: int | None = None) -> dict:
        """List the users in the workspace."""
        return _call(lambda c: c.list_users(page_size=page_size))

    @mcp.tool()
    def notion_retrieve_user(user_id: str) -> dict:
        """Retrieve a single user by id."""
        return _call(lambda c: c.get_user(user_id))

    @mcp.tool()
    def notion_get_self() -> dict:
        """Retrieve the bot/integration user (Notion's users/me)."""
        return _call(lambda c: c.me())

    return mcp


def main() -> None:
    """Entry point: run the MCP server over stdio."""
    build_server().run()


if __name__ == "__main__":
    main()
