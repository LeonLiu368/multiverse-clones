"""CLI <-> MCP parity (R6.2): for each capability, the `sentry` CLI command and the
matching `sentry-mcp` tool return the same underlying data. Both are thin clients of
one HTTP API, so normalized outputs must be identical."""
from __future__ import annotations

import os
from typing import Any, Callable

from sentry_clone.cli import mcp_server

from .helpers import TestServer, json_out, run_sentry


def _mcp(server_url: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    old = os.environ.get("SENTRY_URL")
    os.environ["SENTRY_URL"] = server_url
    try:
        return fn(*args, **kwargs)
    finally:
        if old is None:
            os.environ.pop("SENTRY_URL", None)
        else:
            os.environ["SENTRY_URL"] = old


# (label, CLI argv, MCP callable + args) — covers >=5 capabilities (read + query grammar).
PARITY_CASES = [
    ("list_organizations", ["org", "list"], (mcp_server.list_organizations,)),
    ("list_projects", ["projects", "list"], (mcp_server.list_projects,)),
    ("get_issue", ["issues", "get", "PAYMENTS-501"], (mcp_server.get_issue, "PAYMENTS-501")),
    ("get_stacktrace", ["issues", "stacktrace", "PAYMENTS-501"], (mcp_server.get_stacktrace, "PAYMENTS-501")),
    ("get_suspect_commits", ["issues", "suspect-commits", "PAYMENTS-501"], (mcp_server.get_suspect_commits, "PAYMENTS-501")),
    ("list_releases", ["releases", "list"], (mcp_server.list_releases,)),
    ("list_comments", ["issues", "comments", "PAYMENTS-501"], (mcp_server.list_comments, "PAYMENTS-501")),
]


def test_cli_mcp_parity() -> None:
    with TestServer() as server:
        for label, cli_args, mcp_call in PARITY_CASES:
            cli_out = json_out(run_sentry(server.url, [*cli_args, "--json"]))
            mcp_out = _mcp(server.url, *mcp_call)
            assert cli_out == mcp_out, f"parity mismatch for {label}: {cli_out!r} != {mcp_out!r}"


def test_query_grammar_parity() -> None:
    with TestServer() as server:
        cli_out = json_out(run_sentry(server.url, ["issues", "list", "--project", "payments-api", "--query", "is:unresolved", "--json"]))
        mcp_out = _mcp(server.url, mcp_server.list_issues, project="payments-api", query="is:unresolved")
        assert cli_out == mcp_out
        assert [i["shortId"] for i in cli_out] == ["PAYMENTS-501"]
