"""CLI + MCP coverage and parity (R6.1/R6.2) and isolation (R6.3).

Both the CLI and the MCP server are thin clients of the shared ``DiscordClient``,
which reads ``$DISCORD_API_URL`` (set by the session ``live_server`` fixture), so
every CLI command and every MCP tool hit the real test server over HTTP — the same
path used in production. That is what proves CLI⇄MCP parity: identical
``DiscordClient`` methods, identical transport. Each capability gets a happy path
and (where applicable) an error path.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from discordclone.cli.main import app as cli_app
from discordclone.mcp.server import build_server

runner = CliRunner()
UNKNOWN = "999999999999999999"


@pytest.fixture(autouse=True)
def _server(live_server):
    yield


# ----------------------------------------------------------------- CLI helpers
def cli(*args):
    return runner.invoke(cli_app, [str(a) for a in args])


def cli_json(*args):
    res = cli(*args)
    assert res.exit_code == 0, f"{args} failed: {res.output}"
    return json.loads(res.output)


# ----------------------------------------------------------------- MCP helpers
def _list_tools(server):
    import asyncio

    return asyncio.get_event_loop().run_until_complete(server.list_tools())


def _parse_text(item):
    text = getattr(item, "text", None)
    if text is None:
        return item
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


# MCP tools whose Discord return value is a JSON array. FastMCP serializes these as
# one content block PER element, so the helper must re-assemble the list (a single
# content block otherwise unwraps to a bare object). Dict-returning tools aren't listed.
_LIST_TOOLS = {
    "discord_list_my_guilds", "discord_get_guild_channels", "discord_list_members",
    "discord_get_messages", "discord_get_pins", "discord_list_reactions",
}


def mcp_call(tool, **args):
    """Invoke an MCP tool and return the decoded payload.

    FastMCP serializes a dict-returning tool as one content block and a
    list-returning tool as one content block PER element. If a tuple
    (content, structured) is returned, prefer the structured payload. Otherwise parse
    every content block; list-returning tools (``_LIST_TOOLS``) always yield a list,
    dict-returning tools the single object — so both round-trip faithfully.
    """
    import asyncio

    server = build_server()
    result = asyncio.get_event_loop().run_until_complete(server.call_tool(tool, args))
    if isinstance(result, tuple):
        content = result[0]
        structured = result[1] if len(result) > 1 else None
        if isinstance(structured, dict):
            return structured.get("result", structured)
    else:
        content = result
    parsed = [_parse_text(item) for item in content]
    if tool in _LIST_TOOLS:
        # A single-element or empty content list is still an array for these tools.
        if len(parsed) == 1 and isinstance(parsed[0], dict) and parsed[0].get("code"):
            return parsed[0]  # an error dict, not a 1-element list
        return parsed
    return parsed[0] if len(parsed) == 1 else parsed


# ----------------------------------------------------------------- CLI: every command
def test_cli_users_me(ids):
    assert cli_json("users", "me")["id"] == ids["bot_user_id"]


def test_cli_users_guilds(ids):
    guilds = cli_json("users", "guilds")
    assert any(g["id"] == ids["guild_id"] for g in guilds)


def test_cli_users_get(ids):
    assert cli_json("users", "get", ids["mira_id"])["id"] == ids["mira_id"]


def test_cli_users_get_error():
    res = cli("users", "get", UNKNOWN)
    assert res.exit_code == 1 and "10013" in res.output


def test_cli_guilds_get(ids):
    assert cli_json("guilds", "get", ids["guild_id"])["id"] == ids["guild_id"]


def test_cli_guilds_get_error():
    res = cli("guilds", "get", UNKNOWN)
    assert res.exit_code == 1 and "10004" in res.output


def test_cli_guilds_channels(ids):
    names = {c["name"] for c in cli_json("guilds", "channels", ids["guild_id"])}
    assert "incidents" in names


def test_cli_guilds_members(ids):
    members = cli_json("guilds", "members", ids["guild_id"], "--limit", 100)
    assert len(members) >= 5


def test_cli_guilds_member(ids):
    assert cli_json("guilds", "member", ids["guild_id"], ids["mira_id"])["user"]["id"] == ids["mira_id"]


def test_cli_guilds_member_error(ids):
    res = cli("guilds", "member", ids["guild_id"], UNKNOWN)
    assert res.exit_code == 1 and "10007" in res.output


def test_cli_guilds_search(ids):
    body = cli_json("guilds", "search", ids["guild_id"], "--content", "PRICING_CACHE_TTL")
    assert body["total_results"] >= 2


def test_cli_guilds_search_error(ids):
    res = cli("guilds", "search", ids["guild_id"], "--has", "bogus")
    assert res.exit_code == 1 and "50035" in res.output


def test_cli_channels_get(ids):
    assert cli_json("channels", "get", ids["incidents_channel_id"])["name"] == "incidents"


def test_cli_channels_get_error():
    res = cli("channels", "get", UNKNOWN)
    assert res.exit_code == 1 and "10003" in res.output


def test_cli_channels_messages(ids):
    msgs = cli_json("channels", "messages", ids["incidents_channel_id"], "--limit", 50)
    assert [m["id"] for m in msgs] == sorted((m["id"] for m in msgs), key=int, reverse=True)


def test_cli_channels_message(ids):
    m = cli_json("channels", "message", ids["incidents_channel_id"], ids["decision_message_id"])
    assert "PRICING_CACHE_TTL" in m["content"]


def test_cli_channels_message_error(ids):
    res = cli("channels", "message", ids["incidents_channel_id"], UNKNOWN)
    assert res.exit_code == 1 and "10008" in res.output


def test_cli_channels_send_and_pins(ids):
    posted = cli_json("channels", "send", ids["general_channel_id"], "-m", "cli sent")
    assert posted["author"]["id"] == ids["bot_user_id"] and posted["type"] == 0
    pins = cli_json("channels", "pins", ids["incidents_channel_id"])
    assert all(m["pinned"] for m in pins)


def test_cli_send_error():
    res = cli("channels", "send", UNKNOWN, "-m", "x")
    assert res.exit_code == 1 and "10003" in res.output


def test_cli_reactions_add_and_list(ids):
    posted = cli_json("channels", "send", ids["general_channel_id"], "-m", "cli react target")
    mid = posted["id"]
    cli_json("reactions", "add", ids["general_channel_id"], mid, "👍")
    reactors = cli_json("reactions", "list", ids["general_channel_id"], mid, "👍")
    assert any(u["id"] == ids["bot_user_id"] for u in reactors)


# ----------------------------------------------------------------- MCP: every tool
def test_mcp_tool_inventory():
    tools = {t.name for t in _list_tools(build_server())}
    expected = {
        "discord_get_self", "discord_list_my_guilds", "discord_get_user",
        "discord_get_guild", "discord_get_guild_channels", "discord_list_members",
        "discord_get_member", "discord_search_messages", "discord_get_channel",
        "discord_get_messages", "discord_get_message", "discord_send_message",
        "discord_get_pins", "discord_add_reaction", "discord_list_reactions",
    }
    assert expected <= tools, f"missing MCP tools: {expected - tools}"


def test_mcp_get_self(ids):
    assert mcp_call("discord_get_self")["id"] == ids["bot_user_id"]


def test_mcp_get_user_error():
    out = mcp_call("discord_get_user", user_id=UNKNOWN)
    assert out["code"] == 10013


def test_mcp_guild_and_channels(ids):
    assert mcp_call("discord_get_guild", guild_id=ids["guild_id"])["id"] == ids["guild_id"]
    chans = mcp_call("discord_get_guild_channels", guild_id=ids["guild_id"])
    assert any(c["name"] == "incidents" for c in chans)


def test_mcp_members(ids):
    assert len(mcp_call("discord_list_members", guild_id=ids["guild_id"], limit=100)) >= 5
    assert mcp_call("discord_get_member", guild_id=ids["guild_id"],
                    user_id=ids["mira_id"])["user"]["id"] == ids["mira_id"]


def test_mcp_messages_and_send(ids):
    msgs = mcp_call("discord_get_messages", channel_id=ids["incidents_channel_id"], limit=50)
    assert msgs
    posted = mcp_call("discord_send_message", channel_id=ids["general_channel_id"],
                      content="mcp sent")
    assert posted["author"]["id"] == ids["bot_user_id"] and posted["type"] == 0
    got = mcp_call("discord_get_message", channel_id=ids["general_channel_id"],
                   message_id=posted["id"])
    assert got["content"] == "mcp sent"


def test_mcp_search(ids):
    body = mcp_call("discord_search_messages", guild_id=ids["guild_id"],
                    content="PRICING_CACHE_TTL")
    assert body["total_results"] >= 2


def test_mcp_search_error(ids):
    out = mcp_call("discord_search_messages", guild_id=ids["guild_id"], has="bogus")
    assert out["code"] == 50035


def test_mcp_reactions(ids):
    posted = mcp_call("discord_send_message", channel_id=ids["general_channel_id"],
                      content="mcp react target")
    mid = posted["id"]
    mcp_call("discord_add_reaction", channel_id=ids["general_channel_id"], message_id=mid,
             emoji="👍")
    reactors = mcp_call("discord_list_reactions", channel_id=ids["general_channel_id"],
                        message_id=mid, emoji="👍")
    assert any(u["id"] == ids["bot_user_id"] for u in reactors)


def test_mcp_pins(ids):
    pins = mcp_call("discord_get_pins", channel_id=ids["incidents_channel_id"])
    assert all(m["pinned"] for m in pins)


# ----------------------------------------------------------------- PARITY (R6.2)
def _norm(x):
    if isinstance(x, str):
        try:
            x = json.loads(x)
        except json.JSONDecodeError:
            return x.strip()
    return json.dumps(x, sort_keys=True)


PARITY = [
    (("users", "me"), "discord_get_self", lambda ids: ((), {})),
    (("users", "guilds"), "discord_list_my_guilds", lambda ids: ((), {})),
    (("users", "get"), "discord_get_user", lambda ids: ((ids["mira_id"],), {"user_id": ids["mira_id"]})),
    (("guilds", "get"), "discord_get_guild", lambda ids: ((ids["guild_id"],), {"guild_id": ids["guild_id"]})),
    (("guilds", "channels"), "discord_get_guild_channels", lambda ids: ((ids["guild_id"],), {"guild_id": ids["guild_id"]})),
    (("guilds", "member"), "discord_get_member", lambda ids: ((ids["guild_id"], ids["mira_id"]), {"guild_id": ids["guild_id"], "user_id": ids["mira_id"]})),
    (("channels", "get"), "discord_get_channel", lambda ids: ((ids["incidents_channel_id"],), {"channel_id": ids["incidents_channel_id"]})),
    (("channels", "message"), "discord_get_message", lambda ids: ((ids["incidents_channel_id"], ids["decision_message_id"]), {"channel_id": ids["incidents_channel_id"], "message_id": ids["decision_message_id"]})),
    (("channels", "pins"), "discord_get_pins", lambda ids: ((ids["incidents_channel_id"],), {"channel_id": ids["incidents_channel_id"]})),
]


@pytest.mark.parametrize("cli_path,mcp_tool,argfn", PARITY)
def test_cli_mcp_parity(ids, cli_path, mcp_tool, argfn):
    cli_args, mcp_args = argfn(ids)
    cli_out = cli_json(*cli_path, *cli_args)
    mcp_out = mcp_call(mcp_tool, **mcp_args)
    assert _norm(cli_out) == _norm(mcp_out), f"{cli_path} vs {mcp_tool} drifted"


def test_cli_mcp_parity_search(ids):
    cli_out = cli_json("guilds", "search", ids["guild_id"], "--content", "PRICING_CACHE_TTL")
    mcp_out = mcp_call("discord_search_messages", guild_id=ids["guild_id"],
                       content="PRICING_CACHE_TTL")
    assert _norm(cli_out) == _norm(mcp_out)


def test_cli_mcp_parity_messages(ids):
    cli_out = cli_json("channels", "messages", ids["incidents_channel_id"], "--limit", 25)
    mcp_out = mcp_call("discord_get_messages", channel_id=ids["incidents_channel_id"], limit=25)
    assert _norm(cli_out) == _norm(mcp_out)


# ----------------------------------------------------------------- ISOLATION (R6.3)
def test_isolation_no_seed_on_disk():
    """In the agent container the corpus DB must not be on disk; the verifier sets
    CLONE_STATE_PATH and asserts it's absent (skipped when unset, e.g. on the host)."""
    import os

    state = os.environ.get("CLONE_STATE_PATH")
    if not state:
        pytest.skip("set CLONE_STATE_PATH to assert isolation in the agent container")
    assert not os.path.exists(state), f"LEAK: {state} present — agent could read the answer key"


def test_world_building_absent_from_agent_path():
    """The seed/world-building entrypoint is NOT an agent capability; assert no
    standalone seed binary is on PATH (offline `discord seed` lives in the gateway)."""
    import shutil

    for op in ("discord-seed", "discord-import", "hydrate"):
        assert shutil.which(op) is None, f"world-building tool '{op}' on PATH"
