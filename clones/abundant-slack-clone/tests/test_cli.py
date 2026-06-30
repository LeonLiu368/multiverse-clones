"""R6.1: every `slack` CLI command, happy path + at least one error path.

Invokes the real CLI as a subprocess (the way the agent does) against the live gateway.
"""
from __future__ import annotations

from conftest import (CH_GENERAL, SEARCH_PHRASE, TEAM_NAME, THREAD_TS, run_cli)


def test_cli_whoami(cli_env):
    _, out = run_cli(cli_env, "whoami")
    assert out["ok"] is True and out["team"] == TEAM_NAME


def test_cli_channels(cli_env):
    _, out = run_cli(cli_env, "channels")
    names = {c["name"] for c in out}
    assert {"general", "engineering"} <= names


def test_cli_users(cli_env):
    _, out = run_cli(cli_env, "users")
    assert {"alice", "bob"} <= {u["name"] for u in out}


def test_cli_history(cli_env):
    _, out = run_cli(cli_env, "history", "general", "--limit", "50")
    assert any("welcome to the workspace" in m["text"] for m in out)


def test_cli_replies(cli_env):
    _, out = run_cli(cli_env, "replies", "engineering", THREAD_TS)
    assert [m["ts"] for m in out][0] == THREAD_TS
    assert len(out) == 3


def test_cli_search(cli_env):
    _, out = run_cli(cli_env, "search", SEARCH_PHRASE)
    assert len(out) == 1 and SEARCH_PHRASE in out[0]["text"]


def test_cli_post_roundtrip(cli_env):
    _, posted = run_cli(cli_env, "post", "general", "cli post marker")
    assert posted["ok"] is True and posted["channel"] == CH_GENERAL
    _, hist = run_cli(cli_env, "history", "general", "--limit", "100")
    assert any(m["text"] == "cli post marker" for m in hist)


def test_cli_history_error_nonzero_exit(cli_env):
    # A bad channel surfaces the gateway error; the CLI exits non-zero.
    rc, _ = run_cli(cli_env, "history", "C_NO_SUCH_CHANNEL", expect_ok=False)
    assert rc != 0
