"""`logfire-mcp` — a thin MCP server mirroring the real Pydantic Logfire MCP, so an agent's
Logfire MCP tooling works against our gateway. stdio transport; wraps the same Query API the
`logfire` CLI uses (``$LOGFIRE_URL`` / ``$LOGFIRE_TOKEN``). Carries NO data.

Tools mirror the upstream Logfire MCP names so an agent that knows the real server is at home:
  * ``arbitrary_query(sql, min_timestamp?, max_timestamp?, limit?)`` — run SQL over `records`
  * ``find_exceptions(min_timestamp?, limit?)`` — recent exceptions across services
  * ``get_logfire_records_schema()`` — the `records` table columns + types
"""
from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from logfire_clone import cli

mcp = FastMCP("logfire")


@mcp.tool()
def arbitrary_query(sql: str, min_timestamp: str = "", max_timestamp: str = "", limit: int = 100) -> str:
    """Run a SQL query over the `records` table (SELECT/WITH only). Returns {schema, data} JSON."""
    res = cli.query(sql, min_timestamp or None, max_timestamp or None, limit)
    return json.dumps(res, default=str)


@mcp.tool()
def find_exceptions(min_timestamp: str = "", limit: int = 50) -> str:
    """Recent exception records (type, message, service, path, http status), newest first."""
    sql = ("SELECT start_timestamp, exception_type, exception_message, service_name, url_path, "
           "http_response_status_code FROM records WHERE exception_type IS NOT NULL "
           "ORDER BY start_timestamp DESC")
    res = cli.query(sql, min_timestamp or None, None, limit)
    return json.dumps(res.get("data", []), default=str)


@mcp.tool()
def get_logfire_records_schema() -> str:
    """The `records` table schema: column names + data types."""
    res = cli.query("SELECT * FROM records", limit=0)
    return json.dumps(res.get("schema", {}), default=str)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
