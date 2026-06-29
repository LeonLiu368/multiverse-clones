from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
from typing import Any, Callable

from .client import SentryClient


def _client() -> SentryClient:
    return SentryClient()


def list_organizations() -> list[dict[str, Any]]:
    """List Sentry organizations."""
    return _client().organizations()


def list_projects(org: str | None = None) -> list[dict[str, Any]]:
    """List projects in an organization."""
    return _client().projects(org)


def list_issues(project: str | None = None, org: str | None = None, query: str | None = None, sort: str | None = None) -> list[dict[str, Any]]:
    """List grouped issues, optionally filtered by query syntax."""
    return _client().issues(project=project, org=org, query=query, sort=sort)


def get_issue(issue: str) -> dict[str, Any]:
    """Get an issue by numeric id or short id."""
    return _client().issue(issue)


def get_issue_events(issue: str) -> list[dict[str, Any]]:
    """List events for an issue."""
    return _client().issue_events(issue)


def get_latest_event(issue: str) -> dict[str, Any]:
    """Get the latest event for an issue."""
    return _client().latest_event(issue)


def get_event(event_id: str, project: str, org: str | None = None) -> dict[str, Any]:
    """Get an event by id."""
    return _client().event(event_id, project, org)


def get_stacktrace(issue: str) -> dict[str, Any]:
    """Get the latest stacktrace for an issue."""
    return _client().stacktrace(issue)


def get_breadcrumbs(issue: str) -> dict[str, Any]:
    """Get the latest breadcrumbs for an issue."""
    return _client().breadcrumbs(issue)


def get_issue_tags(issue: str) -> dict[str, Any]:
    """Get issue tags."""
    return _client().issue_tags(issue)


def get_suspect_commits(issue: str) -> list[dict[str, Any]]:
    """Get suspect commits for an issue."""
    return _client().suspect_commits(issue)


def list_releases(project: str | None = None, org: str | None = None) -> list[dict[str, Any]]:
    """List releases."""
    return _client().releases(project=project, org=org)


def get_release(version: str, project: str | None = None, org: str | None = None) -> dict[str, Any]:
    """Get a release by version."""
    return _client().release(version, project=project, org=org)


def get_release_commits(version: str, project: str | None = None, org: str | None = None) -> list[dict[str, Any]]:
    """List commits for a release."""
    return _client().release_commits(version, project=project, org=org)


def list_comments(issue: str) -> list[dict[str, Any]]:
    """List comments for an issue."""
    return _client().comments(issue)


def add_comment(issue: str, text: str) -> dict[str, Any]:
    """Add a comment to an issue."""
    return _client().add_comment(issue, text)


def assign_issue(issue: str, team: str | None = None, user: str | None = None) -> dict[str, Any]:
    """Assign an issue to a team or user."""
    return _client().assign_issue(issue, team=team, user=user)


def resolve_issue(issue: str, in_release: str | None = None) -> dict[str, Any]:
    """Resolve an issue."""
    return _client().resolve_issue(issue, in_release)


def ignore_issue(issue: str, reason: str | None = None) -> dict[str, Any]:
    """Ignore an issue."""
    return _client().ignore_issue(issue, reason)


def reopen_issue(issue: str) -> dict[str, Any]:
    """Reopen an issue."""
    return _client().reopen_issue(issue)


def list_activity(issue: str) -> list[dict[str, Any]]:
    """List issue activity."""
    return _client().activity(issue)


def list_ownership_rules(project: str, org: str | None = None) -> list[dict[str, Any]]:
    """List ownership rules for a project."""
    return _client().ownership(project, org)


TOOL_NAMES = {
    "list_organizations",
    "list_projects",
    "list_issues",
    "get_issue",
    "get_issue_events",
    "get_latest_event",
    "get_event",
    "get_stacktrace",
    "get_breadcrumbs",
    "get_issue_tags",
    "get_suspect_commits",
    "list_releases",
    "get_release",
    "get_release_commits",
    "list_comments",
    "add_comment",
    "assign_issue",
    "resolve_issue",
    "ignore_issue",
    "reopen_issue",
    "list_activity",
    "list_ownership_rules",
}

WRITE_TOOLS = {"add_comment", "assign_issue", "resolve_issue", "ignore_issue", "reopen_issue"}

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
    parser = argparse.ArgumentParser(prog="sentry-mcp")
    parser.add_argument("--disable-write", action="store_true", help="disable MCP write tools")
    args = parser.parse_args(argv)
    tools = tool_set(disable_write=args.disable_write)
    if os.environ.get("SENTRY_MCP_FORCE_FALLBACK") == "1":
        _run_fallback_mcp(tools)
        return
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        _run_fallback_mcp(tools)
        return

    mcp = FastMCP("sentry-clone")
    for func in tools.values():
        mcp.tool()(func)
    mcp.run(transport="stdio")


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
                "serverInfo": {"name": "sentry-mcp", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": [_tool_descriptor(name, func) for name, func in active_tools.items()]}}
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in active_tools:
            return _rpc_error(request_id, -32602, f"unknown tool: {name}")
        try:
            result = active_tools[str(name)](**arguments)
            return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": json.dumps(result, sort_keys=True)}], "isError": False}}
        except Exception as exc:
            return _rpc_error(request_id, -32000, str(exc))
    if request_id is None:
        return None
    return _rpc_error(request_id, -32601, f"unsupported method: {method}")


def _tool_descriptor(name: str, func: Callable[..., Any]) -> dict[str, Any]:
    signature = inspect.signature(func)
    properties = {}
    required = []
    for param_name, param in signature.parameters.items():
        annotation = "string"
        if param.annotation is int:
            annotation = "integer"
        elif param.annotation in (list[str], list):
            annotation = "array"
        properties[param_name] = {"type": annotation}
        if param.default is inspect.Signature.empty:
            required.append(param_name)
    return {"name": name, "description": inspect.getdoc(func) or name, "inputSchema": {"type": "object", "properties": properties, "required": required}}


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
