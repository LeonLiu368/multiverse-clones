"""CLI (3 commands) + MCP (3 tools): happy + error paths, and CLI<->MCP parity.

Both are thin clients of POST /v2/query (cli.query). The conftest `gateway` fixture sets
LOGFIRE_URL/TOKEN so the live server backs every call."""
import importlib
import io
import json

import pytest


@pytest.fixture()
def cli(gateway):
    from logfire_clone import cli as _cli
    importlib.reload(_cli)
    return _cli


@pytest.fixture()
def mcp(gateway):
    from logfire_clone import cli as _cli
    importlib.reload(_cli)
    from logfire_clone import mcp_server as _m
    importlib.reload(_m)
    return _m


# ---- CLI happy ----
def test_cli_query(cli, capsys):
    assert cli.main(["query", "SELECT count(*) n FROM records"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]["n"] == 4


def test_cli_exceptions(cli, capsys):
    assert cli.main(["exceptions", "--limit", "10"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert all(r["exception_type"] for r in out)
    assert any(r["service_name"] == "oddish-worker" for r in out)


def test_cli_schema(cli, capsys):
    assert cli.main(["schema"]) == 0
    out = json.loads(capsys.readouterr().out)
    names = {f["name"] for f in out["fields"]}
    assert "exception_type" in names


# ---- CLI error ----
def test_cli_bad_sql_exit1(cli, capsys):
    rc = cli.main(["query", "SELECT nope FROM records"])
    assert rc == 1
    assert "400" in capsys.readouterr().err


# ---- MCP happy ----
def test_mcp_arbitrary_query(mcp):
    res = json.loads(mcp.arbitrary_query("SELECT count(*) n FROM records",
                                         min_timestamp="2026-06-24T00:00:00Z"))
    assert res["data"][0]["n"] == 4


def test_mcp_find_exceptions(mcp):
    res = json.loads(mcp.find_exceptions(min_timestamp="2026-06-24T00:00:00Z"))
    assert isinstance(res, list) and all(r["exception_type"] for r in res)


def test_mcp_schema(mcp):
    res = json.loads(mcp.get_logfire_records_schema())
    names = {f["name"] for f in res["fields"]}
    assert "service_name" in names


# ---- MCP error (gateway 400 surfaces as an exception) ----
def test_mcp_bad_sql_raises(mcp):
    with pytest.raises(Exception):
        mcp.arbitrary_query("SELECT nope FROM records", min_timestamp="2026-06-24T00:00:00Z")


# ---- Parity: CLI vs MCP return the same underlying data ----
def test_parity_exceptions(cli, mcp, capsys):
    cli.main(["exceptions", "--limit", "5"])
    cli_rows = json.loads(capsys.readouterr().out)
    mcp_rows = json.loads(mcp.find_exceptions(min_timestamp="2026-06-24T00:00:00Z", limit=5))
    assert cli_rows == mcp_rows


def test_parity_schema(cli, mcp, capsys):
    cli.main(["schema"])
    cli_schema = json.loads(capsys.readouterr().out)
    mcp_schema = json.loads(mcp.get_logfire_records_schema())
    assert cli_schema == mcp_schema
