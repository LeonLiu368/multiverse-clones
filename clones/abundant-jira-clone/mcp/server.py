"""jira MCP server — a thin client of the ticketvector ``/rpc`` API.

This is the MCP half of the clone's tool surface (R3). It mirrors the agent-used
``jira``/``linear`` CLI commands 1:1, talking to the SAME ``POST /rpc`` endpoint on the
``jira`` sidecar (``PLANE_BASE_URL``, default ``http://jira:8765``) that the CLI uses in
``WORLD_ISSUES_BACKEND=remote`` mode. Every tool is a thin function over
``mcp/client.TicketVectorClient`` — there is **no business logic here and no dependency
on the ``world_issues`` package** (its source is stripped from the agent image, R2.k).
Because both surfaces hit one HTTP API with identical method+args, CLI↔MCP parity holds.

Transport: FastMCP over stdio when the ``mcp`` package is available; otherwise a
stdlib-only JSON-RPC stdio fallback (same protocol), so the server runs in the
dependency-free, leak-stripped agent image.

Tool ↔ CLI parity map (see docs/COVERAGE.md):
  get_issue          <-> jira issue view <ID> [--comments --links]
  search_issues      <-> jira jql "<JQL>"  /  jira issue query --<filter>  /  issue search
  get_comments       <-> jira issue view <ID> --comments  /  issue comment list
  issue_mine         <-> linear issue mine
  list_projects      <-> jira project list
  list_states        <-> linear state list
  list_labels        <-> linear label list
  list_links         <-> jira issue view <ID> --links
  issue_history      <-> jira issue history <ID>
  transition_issue   <-> jira issue transition <ID> "<state>"   (write)
  add_comment        <-> jira issue comment add <ID> --body "..." (write)
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
from typing import Any, Callable

try:  # package-relative when run as `python -m mcp.server`
    from .client import RpcError, TicketVectorClient
    from .jql import JqlError, parse_jql
except ImportError:  # script execution / sys.path fallback
    from client import RpcError, TicketVectorClient  # type: ignore
    from jql import JqlError, parse_jql  # type: ignore


def _client() -> TicketVectorClient:
    return TicketVectorClient()


# --------------------------------------------------------------------------- #
# Receipt shaping — reproduce world_issues.models.{minimal_issue,mutation_receipt}
# so the write tools return the SAME envelope the CLI prints (parity).
# --------------------------------------------------------------------------- #
def _minimal_issue(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": issue["id"],
        "identifier": issue["identifier"],
        "title": issue["title"],
        "state": issue["state"],
        "priority": issue.get("priority"),
        "assignees": issue.get("assignees", []),
        "labels": issue.get("labels", []),
        "updated_at": issue.get("updated_at"),
        "url": issue.get("url"),
    }


def _mutation_receipt(action: str, target: str, before: dict | None, after: dict | None) -> dict[str, Any]:
    return {
        "ok": True,
        "action": action,
        "target": target,
        "before": before,
        "after": after,
        "warnings": [],
        "dry_run": False,
    }


# --------------------------------------------------------------------------- #
# Tools (read)
# --------------------------------------------------------------------------- #
def get_issue(identifier: str, comments: bool = False, links: bool = False) -> dict[str, Any]:
    """Get one issue by identifier (e.g. PROJ-123). Mirrors `jira issue view`.

    Optionally embed comments/links (mirrors --comments/--links)."""
    client = _client()
    issue = client.get_issue(identifier)
    if comments:
        issue["comments"] = client.list_comments(identifier)
    if links:
        issue["links"] = client.list_links(identifier)
    return issue


def search_issues(
    jql: str | None = None,
    query: str | None = None,
    assignee: str | None = None,
    state: str | None = None,
    state_category: str | None = None,
    label: str | None = None,
    priority: str | None = None,
    project: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Search issues. Mirrors `jira jql "<JQL>"`, `jira issue search`, and `issue query`.

    Provide `jql` for the JQL grammar (assignee=me, status="X", project=KEY,
    priority in (a,b), text ~ "X", sprint is empty, ORDER BY updated asc|desc), OR a
    free-text `query`, OR structured filters (assignee/state/label/priority/...).
    Returns the paginated `{results, next_cursor}` envelope; follow next_cursor to page."""
    if jql is not None:
        filters = parse_jql(jql)
        return _client().issue_list(filters=filters, limit=limit, cursor=cursor)
    if query is not None:
        return _client().issue_list(query=query, limit=limit, cursor=cursor)
    filters: dict[str, Any] = {}
    for key, value in (
        ("assignee", assignee),
        ("state", state),
        ("state_category", state_category),
        ("label", label),
        ("priority", priority),
        ("project", project),
    ):
        if value:
            filters[key] = value
    return _client().issue_list(filters=filters or None, limit=limit, cursor=cursor)


def get_comments(identifier: str) -> list[dict[str, Any]]:
    """List an issue's comments. Mirrors `jira issue view <ID> --comments`."""
    return _client().list_comments(identifier)


def list_links(identifier: str) -> list[dict[str, Any]]:
    """List an issue's links. Mirrors `jira issue view <ID> --links`."""
    return _client().list_links(identifier)


def issue_history(identifier: str) -> list[dict[str, Any]]:
    """List an issue's change history. Mirrors `jira issue history <ID>`."""
    return _client().history_list(identifier)


def issue_mine(limit: int = 50, cursor: str | None = None) -> dict[str, Any]:
    """List issues assigned to the current actor. Mirrors `linear issue mine`."""
    client = _client()
    return client.issue_mine(client.actor, limit=limit, cursor=cursor)


def list_projects() -> list[dict[str, Any]]:
    """List projects. Mirrors `jira project list`."""
    return _client().project_list()


def list_states() -> list[dict[str, Any]]:
    """List workflow states. Mirrors `linear state list`."""
    return _client().list_states()


def list_labels() -> list[dict[str, Any]]:
    """List labels. Mirrors `linear label list`."""
    return _client().list_labels()


# --------------------------------------------------------------------------- #
# Tools (write)
# --------------------------------------------------------------------------- #
def transition_issue(identifier: str, state: str) -> dict[str, Any]:
    """Move an issue to a workflow state (e.g. "In Progress", "Done"). Mirrors
    `jira issue transition <ID> "<state>"`. Returns a mutation receipt (before/after)."""
    before, after = _client().update_issue(identifier, state=state)
    return _mutation_receipt("issue.transition", identifier, _minimal_issue(before), _minimal_issue(after))


def add_comment(identifier: str, body: str) -> dict[str, Any]:
    """Add a comment to an issue. Mirrors `jira issue comment add <ID> --body "..."`."""
    return _client().add_comment(identifier, body)


TOOL_NAMES = {
    "get_issue",
    "search_issues",
    "get_comments",
    "list_links",
    "issue_history",
    "issue_mine",
    "list_projects",
    "list_states",
    "list_labels",
    "transition_issue",
    "add_comment",
}

WRITE_TOOLS = {"transition_issue", "add_comment"}

TOOLS: dict[str, Callable[..., Any]] = {
    name: obj
    for name, obj in list(globals().items())
    if callable(obj) and not name.startswith("_") and name in TOOL_NAMES
}


def tool_set(disable_write: bool = False) -> dict[str, Callable[..., Any]]:
    if not disable_write:
        return dict(TOOLS)
    return {name: tool for name, tool in TOOLS.items() if name not in WRITE_TOOLS}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="jira-mcp")
    parser.add_argument("--disable-write", action="store_true", help="disable MCP write tools")
    args = parser.parse_args(argv)
    tools = tool_set(disable_write=args.disable_write)
    if os.environ.get("JIRA_MCP_FORCE_FALLBACK") == "1":
        _run_fallback_mcp(tools)
        return
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        _run_fallback_mcp(tools)
        return
    server = FastMCP("jira")
    for func in tools.values():
        server.tool()(func)
    server.run(transport="stdio")


# --------------------------------------------------------------------------- #
# Dependency-free JSON-RPC stdio fallback (same wire protocol as FastMCP/stdio).
# This is what runs in the leak-stripped agent image, which has no `mcp` package.
# --------------------------------------------------------------------------- #
def _run_fallback_mcp(tools: dict[str, Callable[..., Any]] | None = None) -> None:
    active_tools = tools or TOOLS
    while True:
        message = _read_message(sys.stdin.buffer)
        if message is None:
            return
        response = _handle_message(message, active_tools)
        if response is not None:
            _write_message(sys.stdout.buffer, response)


def _handle_message(message: dict[str, Any], tools: dict[str, Callable[..., Any]] | None = None) -> dict[str, Any] | None:
    active_tools = tools or TOOLS
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "jira-mcp", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": [_tool_descriptor(name, func) for name, func in active_tools.items()]},
        }
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in active_tools:
            return _rpc_error(request_id, -32602, f"unknown tool: {name}")
        try:
            result = active_tools[str(name)](**arguments)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, sort_keys=True)}],
                    "isError": False,
                },
            }
        except (RpcError, JqlError) as exc:
            # Surface the gateway's realistic error envelope as a tool error, not a crash.
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            }
        except Exception as exc:  # pragma: no cover - defensive
            return _rpc_error(request_id, -32000, str(exc))
    if request_id is None:
        return None
    return _rpc_error(request_id, -32601, f"unsupported method: {method}")


def _tool_descriptor(name: str, func: Callable[..., Any]) -> dict[str, Any]:
    signature = inspect.signature(func)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param_name, param in signature.parameters.items():
        annotation = "string"
        if param.annotation is int:
            annotation = "integer"
        elif param.annotation is bool:
            annotation = "boolean"
        elif param.annotation in (list, list[str]):
            annotation = "array"
        properties[param_name] = {"type": annotation}
        if param.default is inspect.Signature.empty:
            required.append(param_name)
    return {
        "name": name,
        "description": inspect.getdoc(func) or name,
        "inputSchema": {"type": "object", "properties": properties, "required": required},
    }


def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _read_message(stream: Any) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        line_text = line.decode("utf-8").strip()
        if not line_text:
            break
        key, _, value = line_text.partition(":")
        headers[key.lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    return json.loads(stream.read(length).decode("utf-8"))


def _write_message(stream: Any, message: dict[str, Any]) -> None:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body)
    stream.flush()


if __name__ == "__main__":
    main()
