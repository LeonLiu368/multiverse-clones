"""Shared fixtures: a seeded API served by a real uvicorn server in a background
thread. The shared client (and thus the CLI and MCP) talk to it over HTTP at
``$NOTION_API_URL`` — the same path used in production — so the CLI⇄MCP parity and
endpoint tests exercise the real network surface, not an in-process shim.
"""

from __future__ import annotations

import os
import socket
import tempfile
import threading
import time

import httpx
import pytest
import uvicorn

from notionclone.api.app import create_app
from notionclone.seed.generator import generate
from notionclone.seed.load import load_seed


@pytest.fixture(scope="session")
def seed_doc() -> dict:
    return generate(seed=0)


@pytest.fixture(scope="session")
def db_path(seed_doc) -> str:
    path = tempfile.mktemp(suffix=".db")
    load_seed(seed_doc, path)
    return path


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def app(db_path):
    return create_app(db_path)


@pytest.fixture(scope="session", autouse=True)
def live_server(db_path):
    """Run the API on a real port for the whole session and export NOTION_API_URL."""
    port = _free_port()
    app = create_app(db_path)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    # wait for health
    for _ in range(100):
        try:
            if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(0.05)
    else:
        raise RuntimeError("test server did not become healthy")
    os.environ["NOTION_API_URL"] = base
    os.environ["NOTION_TOKEN"] = "test-token"
    yield base
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def client(live_server) -> httpx.Client:
    c = httpx.Client(base_url=live_server,
                     headers={"Authorization": "Bearer test-token",
                              "Notion-Version": "2022-06-28"})
    yield c
    c.close()


@pytest.fixture(scope="session")
def ids(seed_doc) -> dict:
    db = seed_doc["databases"][0]
    pages = seed_doc["pages"]
    db_pages = [p for p in pages if p["parent"].get("database_id") == db["id"]]
    doc_pages = [p for p in pages if p["parent"].get("type") == "workspace"]
    return {
        "database_id": db["id"],
        "task_page_id": db_pages[0]["id"],
        "doc_page_id": doc_pages[0]["id"],
        "user_id": seed_doc["users"][0]["id"],
        "bot_id": next(u["id"] for u in seed_doc["users"] if u["type"] == "bot"),
    }
