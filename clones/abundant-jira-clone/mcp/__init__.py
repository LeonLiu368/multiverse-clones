"""jira MCP server package — a thin, dependency-free client of the ticketvector /rpc API.

See mcp/server.py for the tool surface (CLI↔MCP parity, R3) and mcp/client.py for the
HTTP transport. This package imports NOTHING from `world_issues`, by design (R2.k): the
agent image strips the gateway's API/seed source, so the MCP server must stand alone.
"""
