from __future__ import annotations

import json
import os

from sentry_clone.cli import mcp_server

from .helpers import TestServer


def test_mcp_tool_registration_and_disable_write_behavior() -> None:
    assert "add_comment" in mcp_server.tool_set()
    assert "add_comment" not in mcp_server.tool_set(disable_write=True)
    assert "get_issue" in mcp_server.tool_set(disable_write=True)


def test_mcp_smoke_direct_calls() -> None:
    with TestServer() as server:
        old_url = os.environ.get("SENTRY_URL")
        os.environ["SENTRY_URL"] = server.url
        try:
            issue = mcp_server.get_issue("PAYMENTS-501")
            assert issue["id"] == "1001"
            stacktrace = mcp_server.get_stacktrace("PAYMENTS-501")
            assert stacktrace["stacktrace"]["frames"][0]["filename"] == "payments/retry_policy.py"
            comment = mcp_server.add_comment("PAYMENTS-501", "mcp comment")
            assert comment["text"] == "mcp comment"
        finally:
            if old_url is None:
                os.environ.pop("SENTRY_URL", None)
            else:
                os.environ["SENTRY_URL"] = old_url


def test_mcp_fallback_tools_list() -> None:
    response = mcp_server._handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, mcp_server.tool_set(disable_write=True))
    names = {item["name"] for item in response["result"]["tools"]}
    assert "get_issue" in names
    assert "resolve_issue" not in names
    assert json.dumps(response)
