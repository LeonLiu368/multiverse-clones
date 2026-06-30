"""Shared fixtures: boot the live gworkspace API against a seeded SQLite db, and
expose the env the CLI/MCP subprocess tests need.

Every surface test runs against a real running server (uvicorn), exercising the same
HTTP path the agent's tools take in a task — not the store in isolation. The db is
seeded once from ``tests/fixtures/clone_test.json`` (all four surfaces) into a temp
file; the server requires a bearer token (``GWS_REQUIRE_TOKEN=1``) so the 401 error
path is real.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

HERE = os.path.dirname(__file__)
FIXTURE = os.path.join(HERE, "fixtures", "clone_test.json")
TOKEN = "test-token"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_healthy(base: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/health", timeout=1) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"server at {base} never became healthy")


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    """Boot uvicorn against a freshly-seeded db; yields (base_url, token, env)."""
    db = str(tmp_path_factory.mktemp("gws") / "test.db")
    # seed via the CLI's offline seed loader (same path the gateway entrypoint uses)
    from gwsclone.seed.load import load_seed
    load_seed(json.load(open(FIXTURE)), db)

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ)
    env.update(GWS_DB=db, GWS_REQUIRE_TOKEN="1",
               GWS_API_URL=base, GWS_TOKEN=TOKEN,
               PYTHONPATH=os.path.join(os.path.dirname(HERE), "src"))
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "gwsclone.api.app:app",
         "--host", "127.0.0.1", "--port", str(port)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        _wait_healthy(base)
        yield base, TOKEN, env
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


@pytest.fixture()
def base_url(live_server):
    return live_server[0]


@pytest.fixture()
def token(live_server):
    return live_server[1]


@pytest.fixture()
def cli_env(live_server):
    return live_server[2]
