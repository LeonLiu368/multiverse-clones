"""Shared fixtures: a seeded API served by a real uvicorn server in a background
thread. The shared client (and thus the CLI and MCP) talk to it over HTTP at
``$DISCORD_API_URL`` — the same path used in production — so the CLI⇄MCP parity and
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

from discordclone.api.app import create_app
from discordclone.seed.generator import generate
from discordclone.seed.load import load_seed


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


@pytest.fixture(scope="session", autouse=True)
def live_server(db_path):
    """Run the API on a real port for the whole session and export DISCORD_API_URL."""
    port = _free_port()
    app = create_app(db_path)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(0.05)
    else:
        raise RuntimeError("test server did not become healthy")
    os.environ["DISCORD_API_URL"] = base
    os.environ["DISCORD_BOT_TOKEN"] = "test-token"
    yield base
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def client(live_server) -> httpx.Client:
    c = httpx.Client(base_url=live_server,
                     headers={"Authorization": "Bot test-token"})
    yield c
    c.close()


@pytest.fixture(scope="session")
def ids(seed_doc) -> dict:
    idx = seed_doc["_index"]
    channels = idx["channels"]
    users = idx["users"]
    return {
        "bot_user_id": seed_doc["bot_user_id"],
        "guild_id": idx["guild_id"],
        "incidents_channel_id": channels["incidents"],
        "general_channel_id": channels["general"],
        "engineering_channel_id": channels["engineering"],
        "decision_message_id": idx["incident_decision_message_id"],
        "mira_id": users["mira"],
        "lena_id": users["lena"],
    }
