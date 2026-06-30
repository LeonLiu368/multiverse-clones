"""Tool-level CLI<->MCP parity over the REAL HTTP API.

This drives the *registered* MCP tools through FastMCP's ``call_tool`` dispatch
(i.e. the same path a ``tools/call`` request takes) and the *real* ``figma-cli``
Typer app through ``CliRunner`` — both pointed at a live uvicorn server seeded
with the deterministic generator. For every capability we assert the MCP tool and
the matching CLI leaf return the same underlying data, proving R3.3 parity through
the actual tool surfaces (not helper functions).
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from typer.testing import CliRunner

from figmaclone.api.app import create_app
from figmaclone.cli.main import app as cli_app
from figmaclone.mcp.server import build_server
from figmaclone.seed.generator import generate
from figmaclone.seed.load import load_seed


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    """A real uvicorn server over a seeded DB; yields (base_url, file_key)."""
    db = str(tmp_path_factory.mktemp("parity") / "figma.db")
    sd = generate(seed=42)
    load_seed(sd, db)
    key = sd["files"][0]["key"]

    port = _free_port()
    app = create_app(db)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            httpx.get(f"{base}/health", timeout=1)
            break
        except httpx.HTTPError:
            time.sleep(0.05)
    else:
        raise RuntimeError("server did not start")

    old = {k: os.environ.get(k) for k in ("FIGMA_API_URL", "FIGMA_TOKEN")}
    os.environ["FIGMA_API_URL"] = base
    os.environ["FIGMA_TOKEN"] = "figma-clone-token"
    yield base, key
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    server.should_exit = True
    thread.join(timeout=5)


_runner = CliRunner()
_mcp = build_server()


def _cli(*args: str):
    res = _runner.invoke(cli_app, list(args))
    assert res.exit_code == 0, f"cli {args} failed: {res.output}\n{res.exception}"
    return json.loads(res.stdout)


def _tool(name: str, **kwargs):
    """Call a registered MCP tool through FastMCP's call_tool dispatch.

    Normalizes across FastMCP return shapes: a ``(content_blocks, structured)``
    tuple, a bare ``structured`` payload, or a list of ``TextContent`` blocks
    whose ``text`` is the JSON-encoded tool result.
    """
    result = asyncio.run(_mcp.call_tool(name, kwargs))
    if isinstance(result, tuple):
        result = result[1]
    if isinstance(result, dict):
        if set(result.keys()) == {"result"}:
            return result["result"]
        return result
    if isinstance(result, list):
        # list of content blocks (TextContent) — concatenate their JSON text
        text = "".join(getattr(b, "text", "") for b in result)
        return json.loads(text)
    return result


# capability -> (cli args, mcp tool name, mcp kwargs); KEY/PROJECT/TEAM filled below
PARITY = [
    "get_file", "get_nodes", "get_text", "inspect_node", "search_nodes",
    "list_comments", "list_components", "list_component_sets", "list_styles",
    "list_versions", "get_images", "list_projects", "list_project_files", "me",
]


@pytest.mark.parametrize("cap", PARITY)
def test_tool_parity(live_server, cap):
    base, KEY = live_server
    if cap == "get_file":
        assert _cli("files", "get", KEY) == _tool("figma_get_file", file_key=KEY)
    elif cap == "get_nodes":
        assert _cli("files", "nodes", KEY, "--ids", "1:7") == _tool("figma_get_nodes", file_key=KEY, ids="1:7")
    elif cap == "get_text":
        assert _cli("text", KEY) == _tool("figma_get_text", file_key=KEY)
    elif cap == "inspect_node":
        assert _cli("node", KEY, "1:19") == _tool("figma_inspect_node", file_key=KEY, node_id="1:19")
    elif cap == "search_nodes":
        assert _cli("search", KEY, "Pricing") == _tool("figma_search_nodes", file_key=KEY, query="Pricing")
    elif cap == "list_comments":
        assert _cli("comments", "list", KEY) == _tool("figma_list_comments", file_key=KEY)
    elif cap == "list_components":
        assert _cli("components", "list", KEY) == _tool("figma_list_components", file_key=KEY)
    elif cap == "list_component_sets":
        assert _cli("components", "sets", KEY) == _tool("figma_list_component_sets", file_key=KEY)
    elif cap == "list_styles":
        assert _cli("styles", "list", KEY) == _tool("figma_list_styles", file_key=KEY)
    elif cap == "list_versions":
        assert _cli("versions", KEY) == _tool("figma_list_versions", file_key=KEY)
    elif cap == "get_images":
        assert _cli("images", KEY, "--ids", "1:7") == _tool("figma_get_images", file_key=KEY, ids="1:7")
    elif cap == "list_projects":
        assert _cli("projects", "T1") == _tool("figma_list_projects", team_id="T1")
    elif cap == "list_project_files":
        assert _cli("project-files", "P1") == _tool("figma_list_project_files", project_id="P1")
    elif cap == "me":
        assert _cli("me") == _tool("figma_me")
    else:
        pytest.fail(f"unmapped capability {cap}")


def test_post_then_delete_comment_parity(live_server):
    """Write surfaces: post via MCP tool, list via CLI, delete via MCP tool."""
    base, KEY = live_server
    posted = _tool("figma_post_comment", file_key=KEY, message="parity write", node_id="1:19")
    cid = str(posted["id"])
    listed = _cli("comments", "list", KEY)
    assert any(str(c["id"]) == cid for c in listed["comments"])
    deleted = _tool("figma_delete_comment", file_key=KEY, comment_id=cid)
    assert deleted.get("status") == 200
    listed_after = _cli("comments", "list", KEY)
    assert not any(str(c["id"]) == cid for c in listed_after["comments"])


def test_tools_list_has_all_capabilities(live_server):
    """Every CLI client capability has a registered MCP tool (>=16 total)."""
    names = {t.name for t in asyncio.run(_mcp.list_tools())}
    required = {
        "figma_get_file", "figma_get_nodes", "figma_get_text", "figma_inspect_node",
        "figma_search_nodes", "figma_list_comments", "figma_post_comment",
        "figma_delete_comment", "figma_list_components", "figma_list_component_sets",
        "figma_list_styles", "figma_list_versions", "figma_get_images",
        "figma_list_projects", "figma_list_project_files", "figma_me",
    }
    assert required <= names
    assert len(names) >= 16
