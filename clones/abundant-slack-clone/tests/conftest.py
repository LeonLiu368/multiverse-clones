"""Shared fixtures for the slack-clone unit suite.

The suite proves the clone meets Clone Standard v1 R6: every covered endpoint (happy + error),
every CLI command, every MCP tool, a CLI<->MCP parity check, and an isolation/import-leak check.

It runs against a LIVE gateway over HTTP so the CLI (a real `slack` subprocess) and the korotovsky
`slack-mcp` server (a real stdio subprocess) exercise the same HTTP API the agent uses — no logic is
re-implemented in the test. Two modes:

  * SLACK_TEST_URL set  -> use that already-running gateway (e.g. a booted sidecar / `slack` service).
  * otherwise            -> boot the gateway in-process from this repo against a fresh, deterministic
                            fixture DB on an ephemeral port (the default for `pytest` from a checkout).

The deterministic fixture (`seed_fixture`) is a tiny 2-channel workspace with a known thread and a
known searchable phrase, so endpoint/CLI/MCP assertions are exact and seed-agnostic.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BASE_SRC = REPO / "selfcontained" / "base"
TOKEN = "xoxp-acme-eval-0001"

# --- known fixture constants (asserted across HTTP/CLI/MCP) ----------------------------------------
TEAM_ID = "T0TESTTEAM0"
TEAM_NAME = "testworkspace"
CH_GENERAL = "C0000000001"
CH_ENG = "C0000000002"
U_ALICE = "U0000000A01"
U_BOB = "U0000000B02"
THREAD_TS = "1700000100.000000"
SEARCH_PHRASE = "ZEBRAFISH"  # unique token that appears in exactly one message


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _seed(db_path: str) -> None:
    """Build the deterministic fixture workspace directly through the Store (import path)."""
    sys.path.insert(0, str(BASE_SRC))
    from slackgw.store import Store  # noqa: E402

    st = Store(db_path)
    st.set_meta("team_id", TEAM_ID)
    st.set_meta("team_name", TEAM_NAME)
    st.upsert_channel(id=CH_GENERAL, name="general", is_general=1, creator=U_ALICE,
                      topic="company-wide", purpose="announcements")
    st.upsert_channel(id=CH_ENG, name="engineering", creator=U_BOB,
                      topic="eng chatter", purpose="builds and incidents")
    st.upsert_user(id=U_ALICE, name="alice", real_name="Alice Ant", email="alice@test.dev")
    st.upsert_user(id=U_BOB, name="bob", real_name="Bob Bee", email="bob@test.dev")
    # general: a couple of standalone messages, one carrying the unique search phrase.
    st.insert_message(ts="1700000001.000000", channel_id=CH_GENERAL, user=U_ALICE,
                      text="welcome to the workspace")
    st.insert_message(ts="1700000002.000000", channel_id=CH_GENERAL, user=U_BOB,
                      text=f"secret marker {SEARCH_PHRASE} lives here")
    # engineering: a thread (parent + two replies) for conversations.replies.
    st.insert_message(ts=THREAD_TS, channel_id=CH_ENG, user=U_ALICE,
                      text="deploy thread: starting rollout", reply_count=2)
    st.insert_message(ts="1700000101.000000", channel_id=CH_ENG, user=U_BOB,
                      text="canary looks healthy", thread_ts=THREAD_TS)
    st.insert_message(ts="1700000102.000000", channel_id=CH_ENG, user=U_ALICE,
                      text="rollout complete", thread_ts=THREAD_TS)
    st.recount_members()
    st.commit()


@pytest.fixture(scope="session")
def gateway() -> dict:
    """Yield {url, token}. Reuse SLACK_TEST_URL if set, else boot a fresh in-process gateway."""
    external = os.environ.get("SLACK_TEST_URL")
    if external:
        yield {"url": external.rstrip("/"), "token": os.environ.get("SLACK_BOT_TOKEN", TOKEN)}
        return

    import tempfile

    tmp = tempfile.mkdtemp(prefix="slacktest-")
    db_path = os.path.join(tmp, "fixture.db")
    _seed(db_path)

    # Point the gateway module at the fixture DB before importing the app (Store() reads SLACK_DB).
    os.environ["SLACK_DB"] = db_path
    os.environ["SLACK_BOT_TOKEN"] = TOKEN
    sys.path.insert(0, str(BASE_SRC))
    import uvicorn  # noqa: E402
    from slackgw.app import app  # noqa: E402  (imports after SLACK_DB is set)

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}"
    import urllib.request

    for _ in range(50):
        try:
            urllib.request.urlopen(f"{url}/api/auth.test", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    yield {"url": url, "token": TOKEN}
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def http(gateway):
    """A tiny HTTP helper that hits the gateway's Slack Web API and returns parsed JSON."""
    import json
    import urllib.request

    def call(method: str, **params):
        url = f"{gateway['url']}/api/{method}"
        data = None
        if params:
            from urllib.parse import urlencode
            data = urlencode(params).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Authorization": f"Bearer {gateway['token']}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())

    return call


@pytest.fixture()
def cli_env(gateway):
    """Environment for invoking the `slack` CLI / client as a subprocess against the gateway."""
    env = dict(os.environ)
    env["SLACK_API_URL"] = gateway["url"]
    env["SLACK_BOT_TOKEN"] = gateway["token"]
    env["PYTHONPATH"] = f"{BASE_SRC / 'slackcli'}:{env.get('PYTHONPATH','')}"
    return env


def run_cli(cli_env, *args, expect_ok=True):
    """Invoke `python -m slackcli.cli <args> --json` and return (rc, parsed_json_or_text)."""
    import json

    proc = subprocess.run([sys.executable, "-m", "slackcli.cli", *args, "--json"],
                          env=cli_env, capture_output=True, text=True)
    if expect_ok and proc.returncode != 0:
        raise AssertionError(f"CLI {args} failed rc={proc.returncode}: {proc.stderr}")
    try:
        return proc.returncode, json.loads(proc.stdout)
    except Exception:
        return proc.returncode, proc.stdout
