"""The MCP server and CLI must return the same data as the HTTP API.

We route the MCP server's httpx client through the in-process ASGI app, then check
its data-path helpers (the exact code each tool wraps) return what the raw API
returns — proving the thin-client parity the architecture depends on. We call the
async helpers with ``asyncio.run`` to avoid depending on an async pytest plugin.
"""

import asyncio

import httpx

import figmaclone.mcp.server as mcp_server
from figmaclone.store import find_node, iter_nodes


def _route_mcp_through(client, monkeypatch):
    monkeypatch.setattr(
        mcp_server, "_client",
        lambda: httpx.AsyncClient(transport=httpx.ASGITransport(app=client.figma_app),
                                  base_url="http://test", headers={"X-Figma-Token": "t"}),
    )


def test_get_file_parity(client, monkeypatch):
    _route_mcp_through(client, monkeypatch)
    api = client.get(f"/v1/files/{client.file_key}").json()
    mcp = asyncio.run(mcp_server._get(f"/v1/files/{client.file_key}"))
    assert mcp["document"] == api["document"]
    assert mcp["styles"] == api["styles"]


def test_get_text_parity(client, monkeypatch):
    _route_mcp_through(client, monkeypatch)
    doc = client.get(f"/v1/files/{client.file_key}").json()["document"]
    api_texts = {n["id"]: n.get("characters", "") for n in iter_nodes(doc) if n.get("type") == "TEXT"}
    doc_via_mcp = asyncio.run(mcp_server._document(client.file_key))
    mcp_texts = {n["id"]: n.get("characters", "") for n in iter_nodes(doc_via_mcp) if n.get("type") == "TEXT"}
    assert mcp_texts == api_texts
    assert "PricingCard" in api_texts.values()


def test_inspect_node_parity(client, monkeypatch):
    _route_mcp_through(client, monkeypatch)
    n = find_node(asyncio.run(mcp_server._document(client.file_key)), "1:19")
    assert n["name"] == "PricingCard"
    assert n["cornerRadius"] == 8 and n["itemSpacing"] == 12


def test_post_comment_via_mcp(client, monkeypatch):
    _route_mcp_through(client, monkeypatch)
    res = asyncio.run(mcp_server._post(f"/v1/files/{client.file_key}/comments",
                                       {"message": "mcp says hi", "client_meta": {"node_id": "1:19"}}))
    assert res["message"] == "mcp says hi"
    listed = client.get(f"/v1/files/{client.file_key}/comments").json()["comments"]
    assert any(c["message"] == "mcp says hi" for c in listed)
