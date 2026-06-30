"""R6.1 — every MCP tool exercised, happy path + at least one error path.

The MCP tools are thin /rpc clients (mcp/server.py). The gateway is the small WEB fixture
booted by conftest. The WEB project has issues WEB-1.. assigned to priya.singh/diego.brooks.
"""

from __future__ import annotations

import pytest

from mcp.client import RpcError
from mcp.jql import JqlError


def _first_web_issue(server) -> str:
    page = server.search_issues(limit=1)
    assert page["results"], "WEB fixture should have at least one issue"
    return page["results"][0]["identifier"]


def test_list_projects(mcp_server):
    projects = mcp_server.list_projects()
    keys = {p["key"] for p in projects}
    assert "WEB" in keys


def test_list_states(mcp_server):
    states = mcp_server.list_states()
    assert states and all("category" in s and "name" in s for s in states)


def test_list_labels(mcp_server):
    labels = mcp_server.list_labels()
    assert isinstance(labels, list)


def test_get_issue_happy(mcp_server):
    ident = _first_web_issue(mcp_server)
    issue = mcp_server.get_issue(ident)
    assert issue["identifier"] == ident
    assert "state" in issue and "assignees" in issue


def test_get_issue_with_comments_and_links(mcp_server):
    ident = _first_web_issue(mcp_server)
    issue = mcp_server.get_issue(ident, comments=True, links=True)
    assert "comments" in issue and "links" in issue


def test_get_issue_not_found_error(mcp_server):
    with pytest.raises(RpcError) as exc:
        mcp_server.get_issue("WEB-999999")
    assert exc.value.error_type == "NotFoundError"
    assert "not found" in str(exc.value).lower()


def test_search_issues_jql(mcp_server):
    # `priority in (...)` and `status = "..."` are fixture-valid JQL clauses; returns the
    # paginated envelope. (A single-project mounted fixture has no `project` filter registry.)
    page = mcp_server.search_issues(jql="priority in (high, medium)", limit=5)
    assert "results" in page and "next_cursor" in page
    assert all(i["priority"] in ("high", "medium") for i in page["results"])


def test_search_issues_jql_unsupported_clause(mcp_server):
    with pytest.raises(JqlError):
        mcp_server.search_issues(jql="reporter = bob")


def test_search_issues_filter_assignee(mcp_server):
    page = mcp_server.search_issues(assignee="priya.singh")
    assert isinstance(page["results"], list)
    # every returned issue is assigned to priya.singh
    for issue in page["results"]:
        handles = {a["handle"] for a in issue.get("assignees", [])}
        assert "priya.singh" in handles


def test_search_issues_query_text(mcp_server):
    page = mcp_server.search_issues(query="the", limit=3)
    assert "results" in page


def test_get_comments(mcp_server):
    ident = _first_web_issue(mcp_server)
    comments = mcp_server.get_comments(ident)
    assert isinstance(comments, list)


def test_list_links(mcp_server):
    ident = _first_web_issue(mcp_server)
    assert isinstance(mcp_server.list_links(ident), list)


def test_issue_history(mcp_server):
    ident = _first_web_issue(mcp_server)
    assert isinstance(mcp_server.issue_history(ident), list)


def test_issue_mine(mcp_server):
    page = mcp_server.issue_mine(limit=5)
    assert "results" in page


def test_transition_issue_roundtrip(mcp_server):
    """R5.2 write→read: transition then read the new state back."""
    ident = _first_web_issue(mcp_server)
    states = [s["name"] for s in mcp_server.list_states()]
    target = next((s for s in ("In Progress", "Done", "Todo", "Backlog") if s in states), states[0])
    receipt = mcp_server.transition_issue(ident, target)
    assert receipt["ok"] and receipt["action"] == "issue.transition"
    assert receipt["after"]["state"]["name"] == target
    # observe on a later read
    assert mcp_server.get_issue(ident)["state"]["name"] == target


def test_transition_issue_bad_state_error(mcp_server):
    ident = _first_web_issue(mcp_server)
    with pytest.raises(RpcError) as exc:
        mcp_server.transition_issue(ident, "NoSuchState")
    assert exc.value.error_type == "NotFoundError"


def test_add_comment_roundtrip(mcp_server):
    ident = _first_web_issue(mcp_server)
    marker = "mcp-test-comment-xyz"
    mcp_server.add_comment(ident, marker)
    bodies = [c["body"] for c in mcp_server.get_comments(ident)]
    assert any(marker in b for b in bodies)


def test_add_comment_unknown_issue_error(mcp_server):
    with pytest.raises(RpcError) as exc:
        mcp_server.add_comment("WEB-999999", "x")
    assert exc.value.error_type == "NotFoundError"


def test_tool_descriptors_and_listing(mcp_server):
    """tools/list surfaces all tools with input schemas (the MCP wire contract)."""
    listed = mcp_server._handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in listed["result"]["tools"]}
    assert names == mcp_server.TOOL_NAMES
    for tool in listed["result"]["tools"]:
        assert tool["inputSchema"]["type"] == "object"
        assert tool["description"]


def test_disable_write_hides_write_tools(mcp_server):
    read_only = mcp_server.tool_set(disable_write=True)
    assert not (set(read_only) & mcp_server.WRITE_TOOLS)
    assert "get_issue" in read_only
