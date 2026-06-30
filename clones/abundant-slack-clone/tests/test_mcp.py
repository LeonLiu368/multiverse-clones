"""R6.1/R6.2: the korotovsky `slack-mcp` server — all 5 enabled tools + CLI<->MCP parity.

The MCP server is a real stdio subprocess (`slack-mcp`), present in the gateway/agent images. When
the binary isn't on PATH (a bare `pip` checkout run), these tests skip — they are exercised in the
container suite (tests/test.sh), which is where R6.4 ("green from cold boot") is asserted.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from conftest import CH_GENERAL, SEARCH_PHRASE, THREAD_TS, run_cli

MCP_BIN = shutil.which("slack-mcp")
ENABLED_TOOLS = {
    "channels_list",
    "conversations_history",
    "conversations_replies",
    "conversations_search_messages",
    "conversations_add_message",
}

pytestmark = pytest.mark.skipif(MCP_BIN is None, reason="slack-mcp not installed (run in-container)")


def _mcp_session(cli_env, *requests):
    """Drive the stdio MCP server through initialize -> initialized -> the given requests."""
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "pytest", "version": "1"}}}
    initialized = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    lines = [json.dumps(init), json.dumps(initialized)] + [json.dumps(r) for r in requests]
    proc = subprocess.run([MCP_BIN], input="\n".join(lines) + "\n",
                          env=cli_env, capture_output=True, text=True, timeout=60)
    out = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if "id" in obj:
            out[obj["id"]] = obj
    return out


def _tool_text(resp):
    """Extract the text payload from an MCP tools/call result."""
    content = resp["result"]["content"]
    return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")


def test_mcp_lists_exactly_the_enabled_tools(cli_env):
    resp = _mcp_session(cli_env, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = {t["name"] for t in resp[2]["result"]["tools"]}
    assert tools == ENABLED_TOOLS


def test_mcp_channels_list(cli_env):
    resp = _mcp_session(cli_env, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                  "params": {"name": "channels_list",
                                             "arguments": {"channel_types": "public_channel"}}})
    text = _tool_text(resp[2])
    assert "general" in text and "engineering" in text


def test_mcp_history(cli_env):
    resp = _mcp_session(cli_env, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                  "params": {"name": "conversations_history",
                                             "arguments": {"channel_id": CH_GENERAL, "limit": "50"}}})
    assert "welcome to the workspace" in _tool_text(resp[2])


def test_mcp_replies(cli_env):
    resp = _mcp_session(cli_env, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                  "params": {"name": "conversations_replies",
                                             "arguments": {"channel_id": CH_GENERAL,
                                                           "thread_ts": THREAD_TS}}})
    # engineering channel holds the thread; ask there via id resolution in a second call.
    from conftest import CH_ENG
    resp = _mcp_session(cli_env, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                  "params": {"name": "conversations_replies",
                                             "arguments": {"channel_id": CH_ENG,
                                                           "thread_ts": THREAD_TS}}})
    text = _tool_text(resp[2])
    assert "canary looks healthy" in text and "rollout complete" in text


def test_mcp_search(cli_env):
    resp = _mcp_session(cli_env, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                  "params": {"name": "conversations_search_messages",
                                             "arguments": {"search_query": SEARCH_PHRASE}}})
    assert SEARCH_PHRASE in _tool_text(resp[2])


def test_mcp_add_message_roundtrip(cli_env):
    resp = _mcp_session(cli_env, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                  "params": {"name": "conversations_add_message",
                                             "arguments": {"channel_id": CH_GENERAL,
                                                           "payload": "mcp post marker",
                                                           "content_type": "text/plain"}}})
    assert resp[2]["result"].get("isError") in (False, None)
    # read it back through the CLI (cross-surface round-trip)
    _, hist = run_cli(cli_env, "history", "general", "--limit", "100")
    assert any(m["text"] == "mcp post marker" for m in hist)


# ------------------------------------------------------------------ R6.2 parity: CLI vs MCP same data
def test_parity_search_cli_vs_mcp(cli_env):
    _, cli_out = run_cli(cli_env, "search", SEARCH_PHRASE)
    cli_texts = {m["text"] for m in cli_out}
    resp = _mcp_session(cli_env, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                  "params": {"name": "conversations_search_messages",
                                             "arguments": {"search_query": SEARCH_PHRASE}}})
    mcp_text = _tool_text(resp[2])
    # every message the CLI found must appear in the MCP rendering (same underlying rows)
    for t in cli_texts:
        assert any(t in mcp_text for _ in [0]), f"CLI row {t!r} missing from MCP output"
    assert SEARCH_PHRASE in mcp_text


def test_parity_channels_cli_vs_mcp(cli_env):
    _, cli_out = run_cli(cli_env, "channels")
    cli_names = {c["name"] for c in cli_out}
    resp = _mcp_session(cli_env, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                  "params": {"name": "channels_list",
                                             "arguments": {"channel_types": "public_channel"}}})
    mcp_text = _tool_text(resp[2])
    for name in cli_names:
        assert name in mcp_text
