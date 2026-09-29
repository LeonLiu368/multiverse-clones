"""`slack-cli` — thin HTTP client over the Slack-clone API, plus `seed` subcommands.

Client commands (channels/thread/users/search/post/react/pin) call the running
service at ``$SLACK_API_URL`` (default http://localhost:3000). ``seed`` commands
build a SQLite db locally (synthetic generate / real import-export / load json).
Output is JSON by default; ``--format markdown`` renders readable transcripts.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import httpx
import typer

app = typer.Typer(no_args_is_help=True, help="Slack-clone CLI")
channels_app = typer.Typer(no_args_is_help=True, help="channels: list / history / info")
users_app = typer.Typer(no_args_is_help=True, help="users: list / info")
seed_app = typer.Typer(no_args_is_help=True, help="seed: generate / import-export / load")
app.add_typer(channels_app, name="channels")
app.add_typer(users_app, name="users")
app.add_typer(seed_app, name="seed")


def _api() -> str:
    return os.environ.get("SLACK_API_URL", "http://localhost:3000").rstrip("/")


def call(method: str, **kw: Any) -> dict:
    params = {k: v for k, v in kw.items() if v is not None}
    r = httpx.post(f"{_api()}/api/{method}", data=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        typer.secho(f"error: {data.get('error', 'unknown')}", fg="red", err=True)
        raise typer.Exit(1)
    return data


def _emit(obj: Any) -> None:
    typer.echo(json.dumps(obj, indent=2))


def _user_map() -> dict[str, str]:
    try:
        members = call("users.list", limit=1000).get("members", [])
        return {u["id"]: (u.get("name") or u["id"]) for u in members}
    except Exception:
        return {}


def _render_messages(messages: list[dict], names: dict[str, str]) -> str:
    lines = []
    for m in messages:
        who = names.get(m.get("user", ""), m.get("user", "?"))
        ts = m.get("ts", "")
        text = m.get("text", "")
        prefix = "  ↳ " if m.get("thread_ts") and m.get("thread_ts") != ts else ""
        line = f"{prefix}[{ts}] @{who}: {text}"
        rx = m.get("reactions")
        if rx:
            line += "   " + " ".join(f":{r['name']}:×{r['count']}" for r in rx)
        if m.get("reply_count"):
            line += f"   ({m['reply_count']} replies)"
        lines.append(line)
    return "\n".join(lines)


# --------------------------------------------------------------- channels
@channels_app.command("list")
def channels_list(fmt: str = typer.Option("json", "--format")) -> None:
    data = call("conversations.list", limit=1000)
    if fmt == "markdown":
        for c in data["channels"]:
            typer.echo(f"#{c['name']} ({c['id']}) — {c['topic']['value']}  [{c['num_members']} members]")
    else:
        _emit(data)


@channels_app.command("history")
def channels_history(
    channel: str,
    limit: int = typer.Option(50, "--limit"),
    oldest: str = typer.Option(None, "--oldest"),
    latest: str = typer.Option(None, "--latest"),
    fmt: str = typer.Option("json", "--format"),
) -> None:
    data = call("conversations.history", channel=channel, limit=limit, oldest=oldest, latest=latest)
    if fmt == "markdown":
        typer.echo(_render_messages(data["messages"], _user_map()))
    else:
        _emit(data)


@channels_app.command("info")
def channels_info(channel: str) -> None:
    _emit(call("conversations.info", channel=channel))


# --------------------------------------------------------------- thread / users / search
@app.command()
def thread(channel: str, ts: str, fmt: str = typer.Option("json", "--format")) -> None:
    """Fetch a thread (conversations.replies)."""
    data = call("conversations.replies", channel=channel, ts=ts)
    if fmt == "markdown":
        typer.echo(_render_messages(data["messages"], _user_map()))
    else:
        _emit(data)


@users_app.command("list")
def users_list(fmt: str = typer.Option("json", "--format")) -> None:
    data = call("users.list", limit=1000)
    if fmt == "markdown":
        for u in data["members"]:
            bot = " [bot]" if u.get("is_bot") else ""
            typer.echo(f"@{u['name']} ({u['id']}) — {u['real_name']}{bot}")
    else:
        _emit(data)


@users_app.command("info")
def users_info(user: str) -> None:
    _emit(call("users.info", user=user))


@app.command()
def search(query: str, count: int = typer.Option(20, "--count"), fmt: str = typer.Option("json", "--format")) -> None:
    """Search messages (supports `in:#channel` and `from:@user` modifiers)."""
    data = call("search.messages", query=query, count=count)
    if fmt == "markdown":
        for m in data["messages"]["matches"]:
            ch = m.get("channel", {}).get("name", "")
            typer.echo(f"#{ch} [{m['ts']}] @{m.get('user','?')}: {m['text']}")
    else:
        _emit(data)


# --------------------------------------------------------------- writes
@app.command()
def post(channel: str, text: str, thread: str = typer.Option(None, "--thread"),
         user: str = typer.Option(None, "--user")) -> None:
    """Post a message (optionally as a thread reply with --thread <ts>)."""
    _emit(call("chat.postMessage", channel=channel, text=text, thread_ts=thread, user=user))


@app.command()
def react(channel: str, ts: str, emoji: str, user: str = typer.Option(None, "--user")) -> None:
    """Add an emoji reaction to a message."""
    _emit(call("reactions.add", channel=channel, timestamp=ts, name=emoji, user=user))


@app.command()
def pin(channel: str, ts: str, user: str = typer.Option(None, "--user")) -> None:
    """Pin a message to a channel."""
    _emit(call("pins.add", channel=channel, timestamp=ts, user=user))


# --------------------------------------------------------------- seed
@seed_app.command("generate")
def seed_generate(
    out: str = typer.Option("slack.db", "--out"),
    users: int = typer.Option(12, "--users"),
    channels: int = typer.Option(6, "--channels"),
    days: int = typer.Option(14, "--days"),
    threads: float = typer.Option(0.3, "--threads"),
    reactions: float = typer.Option(0.4, "--reactions"),
    seed: int = typer.Option(0, "--seed"),
    emit: str = typer.Option(None, "--emit", help="also write the canonical seed JSON here"),
) -> None:
    """Generate a deterministic synthetic workspace into a SQLite db."""
    from ..seed.generator import generate
    from ..seed.load import load_seed
    from ..seed import schema

    sd = generate(users=users, channels=channels, days=days, threads=threads,
                  reactions=reactions, seed=seed)
    counts = load_seed(sd, out)
    if emit:
        open(emit, "w").write(schema.to_json(sd))
    typer.echo(json.dumps({"db": out, **counts}))


@seed_app.command("import-export")
def seed_import_export(
    path: str,
    out: str = typer.Option("slack.db", "--out"),
    emit: str = typer.Option(None, "--emit"),
) -> None:
    """Import a real Slack export (dir or .zip) into a SQLite db."""
    from ..seed.export_importer import import_export
    from ..seed.load import load_seed
    from ..seed import schema

    sd = import_export(path)
    counts = load_seed(sd, out)
    if emit:
        open(emit, "w").write(schema.to_json(sd))
    typer.echo(json.dumps({"db": out, **counts}))


@seed_app.command("load")
def seed_load(workspace_json: str, out: str = typer.Option("slack.db", "--out")) -> None:
    """Load a hand-authored canonical seed JSON into a SQLite db."""
    from ..seed.load import load_seed

    sd = json.load(open(workspace_json))
    counts = load_seed(sd, out)
    typer.echo(json.dumps({"db": out, **counts}))


if __name__ == "__main__":
    app()
