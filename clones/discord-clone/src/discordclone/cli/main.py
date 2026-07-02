"""``discord`` — a thin HTTP client over the Discord-clone REST API, + offline ``seed``.

Every client command maps 1:1 onto a ``DiscordClient`` method (the shared client),
so the CLI and the MCP server can't drift — they call the same seam. Commands hit
the running gateway at ``$DISCORD_API_URL`` with the bot token
(``$DISCORD_BOT_TOKEN``). Output is JSON. ``seed`` builds a SQLite db locally (no
server needed) — an OFFLINE operator path, not an agent capability.
"""

from __future__ import annotations

import json
from typing import Any

import typer

from ..client import DiscordAPIError, DiscordClient

app = typer.Typer(no_args_is_help=True, help="Discord REST API command-line tool")
guilds_app = typer.Typer(no_args_is_help=True, help="guilds: get / channels / members / member / search")
channels_app = typer.Typer(no_args_is_help=True, help="channels: get / messages / message / send / pins")
users_app = typer.Typer(no_args_is_help=True, help="users: me / guilds / get")
reactions_app = typer.Typer(no_args_is_help=True, help="reactions: add / list")
seed_app = typer.Typer(no_args_is_help=True, help="seed: generate / load (OFFLINE operator only)")
app.add_typer(guilds_app, name="guilds")
app.add_typer(channels_app, name="channels")
app.add_typer(users_app, name="users")
app.add_typer(reactions_app, name="reactions")
app.add_typer(seed_app, name="seed")


def _client() -> DiscordClient:
    return DiscordClient()


def _emit(obj: Any) -> None:
    typer.echo(json.dumps(obj, indent=2))


def _run(fn) -> None:
    try:
        _emit(fn())
    except DiscordAPIError as e:
        body = e.body if isinstance(e.body, dict) else {"message": str(e.body)}
        typer.secho(f"error: {body.get('code', e.status)}: {body.get('message', '')}",
                    fg="red", err=True)
        raise typer.Exit(1)


# --------------------------------------------------------------- users
@users_app.command("me")
def users_me() -> None:
    """Retrieve the bot/integration user (GET /users/@me)."""
    _run(lambda: _client().me())


@users_app.command("guilds")
def users_guilds() -> None:
    """List the guilds the bot is a member of (GET /users/@me/guilds)."""
    _run(lambda: _client().my_guilds())


@users_app.command("get")
def users_get(user_id: str) -> None:
    """Retrieve a user by id (GET /users/{id})."""
    _run(lambda: _client().get_user(user_id))


# --------------------------------------------------------------- guilds
@guilds_app.command("get")
def guilds_get(guild_id: str) -> None:
    """Retrieve a guild object (GET /guilds/{id})."""
    _run(lambda: _client().get_guild(guild_id))


@guilds_app.command("channels")
def guilds_channels(guild_id: str) -> None:
    """List a guild's channels (GET /guilds/{id}/channels)."""
    _run(lambda: _client().get_guild_channels(guild_id))


@guilds_app.command("members")
def guilds_members(guild_id: str, limit: int = typer.Option(None, "--limit"),
                   after: str = typer.Option(None, "--after")) -> None:
    """List guild members (GET /guilds/{id}/members)."""
    _run(lambda: _client().list_members(guild_id, limit=limit, after=after))


@guilds_app.command("member")
def guilds_member(guild_id: str, user_id: str) -> None:
    """Retrieve one guild member (GET /guilds/{id}/members/{user})."""
    _run(lambda: _client().get_member(guild_id, user_id))


@guilds_app.command("search")
def guilds_search(guild_id: str,
                  content: str = typer.Option(None, "--content"),
                  channel_id: str = typer.Option(None, "--channel"),
                  author_id: str = typer.Option(None, "--author"),
                  mentions: str = typer.Option(None, "--mentions"),
                  has: str = typer.Option(None, "--has"),
                  pinned: str = typer.Option(None, "--pinned"),
                  before: str = typer.Option(None, "--before"),
                  after: str = typer.Option(None, "--after"),
                  limit: int = typer.Option(None, "--limit"),
                  offset: int = typer.Option(None, "--offset")) -> None:
    """Search a guild's messages (GET /guilds/{id}/messages/search — the T2 grammar)."""
    _run(lambda: _client().search_messages(
        guild_id, content=content, channel_id=channel_id, author_id=author_id,
        mentions=mentions, has=has, pinned=pinned, before=before, after=after,
        limit=limit, offset=offset))


# --------------------------------------------------------------- channels
@channels_app.command("get")
def channels_get(channel_id: str) -> None:
    """Retrieve a channel object (GET /channels/{id})."""
    _run(lambda: _client().get_channel(channel_id))


@channels_app.command("messages")
def channels_messages(channel_id: str, limit: int = typer.Option(None, "--limit"),
                      before: str = typer.Option(None, "--before"),
                      after: str = typer.Option(None, "--after"),
                      around: str = typer.Option(None, "--around")) -> None:
    """Read a channel's message history (GET /channels/{id}/messages — newest-first)."""
    _run(lambda: _client().get_messages(channel_id, limit=limit, before=before,
                                        after=after, around=around))


@channels_app.command("message")
def channels_message(channel_id: str, message_id: str) -> None:
    """Retrieve one message (GET /channels/{id}/messages/{message})."""
    _run(lambda: _client().get_message(channel_id, message_id))


@channels_app.command("send")
def channels_send(channel_id: str, content: str = typer.Option(..., "-m", "--content")) -> None:
    """Send a message to a channel (POST /channels/{id}/messages)."""
    _run(lambda: _client().send_message(channel_id, content))


@channels_app.command("pins")
def channels_pins(channel_id: str) -> None:
    """List a channel's pinned messages (GET /channels/{id}/pins)."""
    _run(lambda: _client().get_pins(channel_id))


# --------------------------------------------------------------- reactions
@reactions_app.command("add")
def reactions_add(channel_id: str, message_id: str, emoji: str) -> None:
    """Add the bot's reaction to a message (PUT …/reactions/{emoji}/@me)."""
    _run(lambda: _client().add_reaction(channel_id, message_id, emoji))


@reactions_app.command("list")
def reactions_list(channel_id: str, message_id: str, emoji: str,
                   limit: int = typer.Option(None, "--limit"),
                   after: str = typer.Option(None, "--after")) -> None:
    """List the users who reacted with an emoji (GET …/reactions/{emoji})."""
    _run(lambda: _client().list_reactions(channel_id, message_id, emoji,
                                          limit=limit, after=after))


# --------------------------------------------------------------- seed (offline)
@seed_app.command("generate")
def seed_generate(out: str = typer.Option("discord.db", "--out"),
                  guild: str = typer.Option("Acme Engineering", "--guild"),
                  seed: int = typer.Option(0, "--seed"),
                  emit: str = typer.Option(None, "--emit", help="also write the canonical seed JSON here")) -> None:
    """Generate a deterministic synthetic Discord guild into a SQLite db."""
    from ..seed import schema
    from ..seed.generator import generate
    from ..seed.load import load_seed

    sd = generate(guild=guild, seed=seed)
    counts = load_seed(sd, out)
    if emit:
        open(emit, "w").write(schema.to_json(sd))
    typer.echo(json.dumps({"db": out, **counts}))


@seed_app.command("load")
def seed_load(fixture_json: str, out: str = typer.Option("discord.db", "--out")) -> None:
    """Load a hand-authored canonical seed JSON into a SQLite db."""
    from ..seed.load import load_seed

    sd = json.load(open(fixture_json))
    counts = load_seed(sd, out)
    typer.echo(json.dumps({"db": out, **counts}))


if __name__ == "__main__":
    app()
