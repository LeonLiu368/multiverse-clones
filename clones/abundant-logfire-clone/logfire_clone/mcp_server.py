"""`logfire-mcp` — a thin MCP server mirroring the real Pydantic Logfire MCP, so an agent's
Logfire MCP tooling works against our gateway. stdio transport; wraps the same Query API the
`logfire` CLI uses (``$LOGFIRE_URL`` / ``$LOGFIRE_TOKEN``). Carries NO data.

Tools mirror the upstream Logfire MCP names so an agent that knows the real server is at home.
Names/params follow ``github.com/pydantic/logfire-mcp`` so an agent prompted with the real
tool schema is at home:
  * ``arbitrary_query(query|sql, age?, min_timestamp?, max_timestamp?, limit?)`` — SQL over `records`
  * ``find_exceptions_in_file(filepath?, min_timestamp?, limit?)`` — recent exceptions (upstream name)
  * ``find_exceptions(...)`` — clone alias of the above, kept for existing tasks/tests
  * ``get_logfire_records_schema()`` / ``schema_reference()`` — the `records` table columns + types
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from mcp.server.fastmcp import FastMCP

from logfire_clone import cli

mcp = FastMCP("logfire")


def _min_from_age(age: int | None, min_timestamp: str) -> str:
    """Map an ``age`` (minutes look-back, real logfire-mcp) to an ISO min_timestamp.

    An explicit ``min_timestamp`` wins if both are given; otherwise ``age`` becomes
    ``now - age`` minutes. Returns "" when neither is set (cli.query applies its default)."""
    if min_timestamp:
        return min_timestamp
    if age:
        return (datetime.now(timezone.utc) - timedelta(minutes=age)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ""


@mcp.tool()
def arbitrary_query(sql: str = "", min_timestamp: str = "", max_timestamp: str = "",
                    limit: int = 100, query: str = "", age: int = 0) -> str:
    """Run a SQL query over the `records` table (SELECT/WITH only). Returns {schema, data} JSON.

    Accepts both the clone's ``sql`` and the real logfire-mcp ``query`` param (aliases), and the
    real ``age`` (minutes look-back, mapped to min_timestamp = now - age)."""
    sql = query or sql
    min_ts = _min_from_age(age, min_timestamp)
    res = cli.query(sql, min_ts or None, max_timestamp or None, limit)
    return json.dumps(res, default=str)


def _exceptions(min_ts: str, limit: int, filepath: str = "") -> str:
    sql = ("SELECT start_timestamp, exception_type, exception_message, service_name, url_path, "
           "http_response_status_code FROM records WHERE exception_type IS NOT NULL ")
    if filepath:
        # Best-effort: our corpus keys request context on url_path, not source file. Filter on it
        # when a filepath is supplied so the param is honored where the data allows.
        safe = filepath.replace("'", "''")
        sql += f"AND url_path LIKE '%{safe}%' "
    sql += "ORDER BY start_timestamp DESC"
    res = cli.query(sql, min_ts or None, None, limit)
    return json.dumps(res.get("data", []), default=str)


@mcp.tool()
def find_exceptions_in_file(filepath: str = "", min_timestamp: str = "", limit: int = 50,
                            age: int = 0) -> str:
    """Recent exception records (upstream logfire-mcp name), newest first.

    ``filepath`` is honored where the corpus allows (matched against url_path); otherwise it is
    accepted and ignored. Returns a JSON list of exception rows."""
    return _exceptions(_min_from_age(age, min_timestamp), limit, filepath)


@mcp.tool()
def find_exceptions(min_timestamp: str = "", limit: int = 50) -> str:
    """Recent exception records (type, message, service, path, http status), newest first.

    Clone alias of ``find_exceptions_in_file`` — kept for existing tasks/tests."""
    return _exceptions(min_timestamp, limit)


@mcp.tool()
def get_logfire_records_schema() -> str:
    """The `records` table schema: column names + data types."""
    res = cli.query("SELECT * FROM records", limit=0)
    return json.dumps(res.get("schema", {}), default=str)


@mcp.tool()
def schema_reference() -> str:
    """The `records` table schema: column names + data types (upstream logfire-mcp name)."""
    return get_logfire_records_schema()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
