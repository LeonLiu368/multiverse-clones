"""R6.2 — CLI↔MCP parity.

For each covered capability, the real `jira`/`linear` CLI dispatch (`world_issues.cli.run`)
and the matching MCP tool must return the SAME underlying data — proving R3.3 (both are
thin clients of one /rpc API). Skipped when the upstream CLI package is not importable in
this environment (the MCP-vs-/rpc tests in test_mcp_tools.py still cover correctness)."""

from __future__ import annotations

import pytest

from tests.conftest import CliError, cli, has_cli

pytestmark = pytest.mark.skipif(not has_cli(), reason="world_issues.cli not importable here")


def _first_web_issue(mcp_server) -> str:
    return mcp_server.search_issues(limit=1)["results"][0]["identifier"]


def test_parity_get_issue(mcp_server, cli_env):
    ident = _first_web_issue(mcp_server)
    cli_issue = cli("jira", "issue", "view", ident)
    mcp_issue = mcp_server.get_issue(ident)
    fields = ["identifier", "state", "assignees", "priority", "title", "labels"]
    assert {k: cli_issue[k] for k in fields} == {k: mcp_issue[k] for k in fields}


def test_parity_jql_query(mcp_server, cli_env):
    cli_page = cli("jira", "jql", "priority in (high, medium)", "--limit", "5")
    mcp_page = mcp_server.search_issues(jql="priority in (high, medium)", limit=5)
    assert [r["identifier"] for r in cli_page["results"]] == [r["identifier"] for r in mcp_page["results"]]
    assert cli_page["next_cursor"] == mcp_page["next_cursor"]


def test_parity_issue_query_assignee(mcp_server, cli_env):
    cli_page = cli("jira", "issue", "query", "--assignee", "priya.singh")
    mcp_page = mcp_server.search_issues(assignee="priya.singh")
    assert [r["identifier"] for r in cli_page["results"]] == [r["identifier"] for r in mcp_page["results"]]


def test_parity_list_projects(mcp_server, cli_env):
    assert cli("jira", "project", "list") == mcp_server.list_projects()


def test_parity_list_states(mcp_server, cli_env):
    assert cli("linear", "state", "list") == mcp_server.list_states()


def test_parity_list_labels(mcp_server, cli_env):
    assert cli("linear", "label", "list") == mcp_server.list_labels()


def test_parity_comments(mcp_server, cli_env):
    ident = _first_web_issue(mcp_server)
    cli_view = cli("jira", "issue", "view", ident, "--comments")
    assert cli_view.get("comments", []) == mcp_server.get_comments(ident)


def test_parity_not_found_error(mcp_server, cli_env):
    """Both surfaces surface the product's NotFoundError envelope for a missing issue."""
    from mcp.client import RpcError

    with pytest.raises(CliError) as cli_exc:
        cli("jira", "issue", "view", "WEB-999999")
    with pytest.raises(RpcError) as mcp_exc:
        mcp_server.get_issue("WEB-999999")
    assert "not found" in cli_exc.value.output.lower()
    assert mcp_exc.value.error_type == "NotFoundError"
