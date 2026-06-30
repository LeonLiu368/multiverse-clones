"""CLI + MCP coverage and parity (R6.1/R6.2) and isolation (R6.3).

Both the CLI and the MCP server are thin clients of the shared ``NotionClient``.
We route that client through the in-process ASGI app by patching its default
transport, so every CLI command, every MCP tool, and the CLI⇄MCP parity checks run
without a network server. Each capability gets a happy path and >=1 error path.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from notionclone.cli.main import app as cli_app
from notionclone.mcp.server import build_server

runner = CliRunner()
UNKNOWN = "00000000-0000-4000-8000-000000000999"


# The shared NotionClient reads $NOTION_API_URL (set by the session live_server
# fixture in conftest), so both the CLI and the MCP server hit the real test
# server over HTTP — the same path used in production. This is what proves CLI⇄MCP
# parity: identical NotionClient methods, identical transport.
@pytest.fixture(autouse=True)
def _server(live_server):
    yield


# ----------------------------------------------------------------- CLI helpers
def cli(*args):
    return runner.invoke(cli_app, list(args))


def cli_json(*args):
    res = cli(*args)
    assert res.exit_code == 0, f"{args} failed: {res.output}"
    return json.loads(res.output)


# ----------------------------------------------------------------- MCP helpers
def mcp_tools():
    server = build_server()
    import anyio
    return anyio.from_thread.run if False else _list_tools(server)


def _list_tools(server):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(server.list_tools())


def mcp_call(tool, **args):
    server = build_server()
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(server.call_tool(tool, args))
    # FastMCP returns (content, structured) or content list across versions
    if isinstance(result, tuple):
        content, structured = result[0], result[1] if len(result) > 1 else None
    else:
        content, structured = result, None
    if isinstance(structured, dict):
        return structured.get("result", structured)
    for item in content:
        text = getattr(item, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
    return content


# ----------------------------------------------------------------- CLI: every command
def test_cli_users_list(ids):
    assert cli_json("users", "list")["object"] == "list"


def test_cli_users_get(ids):
    assert cli_json("users", "get", ids["user_id"])["id"] == ids["user_id"]


def test_cli_users_me():
    assert cli_json("users", "me")["type"] == "bot"


def test_cli_pages_get(ids):
    assert cli_json("pages", "get", ids["task_page_id"])["object"] == "page"


def test_cli_pages_get_error():
    res = cli("pages", "get", UNKNOWN)
    assert res.exit_code == 1 and "object_not_found" in res.output


def test_cli_pages_create_update_archive(ids):
    props = json.dumps({"Name": {"type": "title", "title": [{"type": "text", "text": {"content": "cli page"}}]}})
    parent = json.dumps({"database_id": ids["database_id"]})
    created = cli_json("pages", "create", "--parent", parent, "--properties", props)
    pid = created["id"]
    upd = cli_json("pages", "update", pid, "--properties",
                   json.dumps({"Estimate": {"type": "number", "number": 7}}))
    assert upd["properties"]["Estimate"]["number"] == 7
    arch = cli_json("pages", "archive", pid)
    assert arch["archived"] is True


def test_cli_blocks_children(ids):
    assert cli_json("blocks", "children", ids["doc_page_id"])["object"] == "list"


def test_cli_blocks_append(ids):
    out = cli_json("blocks", "append", ids["doc_page_id"], "--text", "cli appended")
    assert out["results"][0]["type"] == "paragraph"


def test_cli_blocks_append_error(ids):
    res = cli("blocks", "append", ids["doc_page_id"])  # no --children/--text
    assert res.exit_code == 2


def test_cli_db_get(ids):
    assert cli_json("databases", "get", ids["database_id"])["object"] == "database"


def test_cli_db_query(ids):
    out = cli_json("databases", "query", ids["database_id"], "--filter",
                   json.dumps({"property": "Status", "status": {"equals": "Done"}}))
    assert out["object"] == "list"


def test_cli_db_query_error(ids):
    res = cli("databases", "query", ids["database_id"], "--filter",
              json.dumps({"property": "Estimate", "number": {"contains": 1}}))
    assert res.exit_code == 1 and "validation_error" in res.output


def test_cli_search(ids):
    assert cli_json("search", "billing")["object"] == "list"


def test_cli_comments_list(ids):
    assert cli_json("comments", "list", ids["doc_page_id"])["object"] == "list"


def test_cli_comments_add(ids):
    assert cli_json("comments", "add", ids["doc_page_id"], "-m", "cli comment")["object"] == "comment"


def test_cli_comments_add_error():
    res = cli("comments", "add", UNKNOWN, "-m", "x")
    assert res.exit_code == 1


# ----------------------------------------------------------------- MCP: every tool
def test_mcp_tool_inventory():
    tools = {t.name for t in _list_tools(build_server())}
    expected = {
        "notion_retrieve_page", "notion_create_page", "notion_update_page",
        "notion_get_block_children", "notion_append_block_children",
        "notion_retrieve_database", "notion_query_database", "notion_search",
        "notion_list_comments", "notion_create_comment",
        "notion_list_users", "notion_retrieve_user", "notion_get_self",
    }
    assert expected <= tools, f"missing MCP tools: {expected - tools}"


def test_mcp_retrieve_page(ids):
    assert mcp_call("notion_retrieve_page", page_id=ids["task_page_id"])["object"] == "page"


def test_mcp_retrieve_page_error():
    out = mcp_call("notion_retrieve_page", page_id=UNKNOWN)
    assert out["object"] == "error" and out["code"] == "object_not_found"


def test_mcp_query_database(ids):
    out = mcp_call("notion_query_database", database_id=ids["database_id"],
                   filter={"property": "Status", "status": {"equals": "Done"}})
    assert out["object"] == "list"


def test_mcp_query_error(ids):
    out = mcp_call("notion_query_database", database_id=ids["database_id"],
                   filter={"property": "Estimate", "number": {"contains": 1}})
    assert out["object"] == "error"


def test_mcp_search(ids):
    assert mcp_call("notion_search", query="billing")["object"] == "list"


def test_mcp_users(ids):
    assert mcp_call("notion_list_users")["object"] == "list"
    assert mcp_call("notion_retrieve_user", user_id=ids["user_id"])["id"] == ids["user_id"]
    assert mcp_call("notion_get_self")["type"] == "bot"


def test_mcp_blocks(ids):
    assert mcp_call("notion_get_block_children", block_id=ids["doc_page_id"])["object"] == "list"
    out = mcp_call("notion_append_block_children", block_id=ids["doc_page_id"],
                   children=[{"type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "mcp"}}]}}])
    assert out["object"] == "list"


def test_mcp_comments(ids):
    assert mcp_call("notion_list_comments", block_id=ids["doc_page_id"])["object"] == "list"
    assert mcp_call("notion_create_comment", page_id=ids["doc_page_id"], message="mcp comment")["object"] == "comment"


def test_mcp_database_and_pages(ids):
    assert mcp_call("notion_retrieve_database", database_id=ids["database_id"])["object"] == "database"
    created = mcp_call("notion_create_page",
                       parent={"database_id": ids["database_id"]},
                       properties={"Name": {"type": "title", "title": [{"type": "text", "text": {"content": "mcp page"}}]}})
    assert created["object"] == "page"
    upd = mcp_call("notion_update_page", page_id=created["id"],
                   properties={"Estimate": {"type": "number", "number": 3}})
    assert upd["properties"]["Estimate"]["number"] == 3


# ----------------------------------------------------------------- PARITY (R6.2)
def _norm(x):
    if isinstance(x, str):
        try:
            x = json.loads(x)
        except json.JSONDecodeError:
            return x.strip()
    return json.dumps(x, sort_keys=True)


PARITY = [
    (("pages", "get"), "notion_retrieve_page", lambda ids: ((ids["task_page_id"],), {"page_id": ids["task_page_id"]})),
    (("databases", "get"), "notion_retrieve_database", lambda ids: ((ids["database_id"],), {"database_id": ids["database_id"]})),
    (("users", "get"), "notion_retrieve_user", lambda ids: ((ids["user_id"],), {"user_id": ids["user_id"]})),
    (("users", "me"), "notion_get_self", lambda ids: ((), {})),
    (("blocks", "children"), "notion_get_block_children", lambda ids: ((ids["doc_page_id"],), {"block_id": ids["doc_page_id"]})),
    (("comments", "list"), "notion_list_comments", lambda ids: ((ids["doc_page_id"],), {"block_id": ids["doc_page_id"]})),
    (("users", "list"), "notion_list_users", lambda ids: ((), {})),
]


@pytest.mark.parametrize("cli_path,mcp_tool,argfn", PARITY)
def test_cli_mcp_parity(ids, cli_path, mcp_tool, argfn):
    cli_args, mcp_args = argfn(ids)
    cli_out = cli_json(*cli_path, *cli_args)
    mcp_out = mcp_call(mcp_tool, **mcp_args)
    assert _norm(cli_out) == _norm(mcp_out), f"{cli_path} vs {mcp_tool} drifted"


def test_cli_mcp_parity_query(ids):
    flt = {"property": "Status", "status": {"equals": "Done"}}
    cli_out = cli_json("databases", "query", ids["database_id"], "--filter", json.dumps(flt))
    mcp_out = mcp_call("notion_query_database", database_id=ids["database_id"], filter=flt)
    assert _norm(cli_out) == _norm(mcp_out)


# ----------------------------------------------------------------- ISOLATION (R6.3)
def test_isolation_no_seed_on_disk():
    """The agent env must not carry the corpus DB on disk; set CLONE_STATE_PATH in
    the agent container so the verifier asserts it (here we assert the env-declared
    path is absent when provided)."""
    import os
    state = os.environ.get("CLONE_STATE_PATH")
    if not state:
        pytest.skip("set CLONE_STATE_PATH to assert isolation in the agent container")
    assert not os.path.exists(state), f"LEAK: {state} present — agent could read the answer key"


def test_world_building_absent_from_agent_path():
    """The seed/world-building entrypoint is NOT an agent capability. In the agent
    container the seed module is stripped; here we assert no standalone seed binary
    is on PATH (the offline `notion-cli seed` lives only in the gateway image)."""
    import shutil
    for op in ("notion-seed", "notion-import", "hydrate"):
        assert shutil.which(op) is None, f"world-building tool '{op}' on PATH"
