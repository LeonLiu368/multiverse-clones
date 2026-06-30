"""``notion-cli`` — a thin HTTP client over the Notion-clone API, + offline ``seed``.

Every client command maps 1:1 onto a ``NotionClient`` method (the shared client),
so the CLI and the MCP server can't drift — they call the same seam. Commands hit
the running service at ``$NOTION_API_URL`` with the integration token
(``$NOTION_TOKEN``). Output is JSON by default. ``seed`` builds a SQLite db
locally (no server needed) — an OFFLINE operator path, not an agent capability.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import typer

from ..client import NotionAPIError, NotionClient, rich_text

app = typer.Typer(no_args_is_help=True, help="Notion-clone CLI")
pages_app = typer.Typer(no_args_is_help=True, help="pages: get / create / update / archive")
blocks_app = typer.Typer(no_args_is_help=True, help="blocks: children / append")
db_app = typer.Typer(no_args_is_help=True, help="databases: get / query")
comments_app = typer.Typer(no_args_is_help=True, help="comments: list / add")
users_app = typer.Typer(no_args_is_help=True, help="users: list / get / me")
seed_app = typer.Typer(no_args_is_help=True, help="seed: generate / load (OFFLINE operator only)")
app.add_typer(pages_app, name="pages")
app.add_typer(blocks_app, name="blocks")
app.add_typer(db_app, name="databases")
app.add_typer(comments_app, name="comments")
app.add_typer(users_app, name="users")
app.add_typer(seed_app, name="seed")


def _client() -> NotionClient:
    return NotionClient()


def _emit(obj: Any) -> None:
    typer.echo(json.dumps(obj, indent=2))


def _run(fn) -> None:
    try:
        _emit(fn())
    except NotionAPIError as e:
        body = e.body if isinstance(e.body, dict) else {"message": str(e.body)}
        typer.secho(f"error: {body.get('code', e.status)}: {body.get('message', '')}",
                    fg="red", err=True)
        raise typer.Exit(1)


def _parse_json(value: str | None, what: str) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        typer.secho(f"error: {what} must be valid JSON", fg="red", err=True)
        raise typer.Exit(2)


# --------------------------------------------------------------- pages
@pages_app.command("get")
def pages_get(page_id: str) -> None:
    """Retrieve a page object."""
    _run(lambda: _client().get_page(page_id))


@pages_app.command("create")
def pages_create(parent: str = typer.Option(..., "--parent", help="JSON parent, e.g. '{\"database_id\":\"…\"}'"),
                 properties: str = typer.Option(..., "--properties", help="JSON properties map")) -> None:
    """Create a page under a database or page parent."""
    par = _parse_json(parent, "--parent")
    props = _parse_json(properties, "--properties")
    _run(lambda: _client().create_page(par, props))


@pages_app.command("update")
def pages_update(page_id: str,
                 properties: str = typer.Option(None, "--properties", help="JSON properties patch")) -> None:
    """Update a page's properties."""
    props = _parse_json(properties, "--properties")
    _run(lambda: _client().update_page(page_id, properties=props))


@pages_app.command("archive")
def pages_archive(page_id: str, restore: bool = typer.Option(False, "--restore")) -> None:
    """Archive (or --restore) a page."""
    _run(lambda: _client().update_page(page_id, archived=not restore))


# --------------------------------------------------------------- blocks
@blocks_app.command("children")
def blocks_children(block_id: str, page_size: int = typer.Option(None, "--page-size"),
                    start_cursor: str = typer.Option(None, "--start-cursor")) -> None:
    """List a page's or block's child blocks."""
    _run(lambda: _client().get_block_children(block_id, page_size=page_size, start_cursor=start_cursor))


@blocks_app.command("append")
def blocks_append(block_id: str,
                  children: str = typer.Option(None, "--children", help="JSON array of block objects"),
                  text: str = typer.Option(None, "--text", help="shorthand: append one paragraph")) -> None:
    """Append child blocks to a page or block."""
    if children:
        kids = _parse_json(children, "--children")
    elif text:
        kids = [{"type": "paragraph", "paragraph": {"rich_text": rich_text(text)}}]
    else:
        typer.secho("error: provide --children or --text", fg="red", err=True)
        raise typer.Exit(2)
    _run(lambda: _client().append_block_children(block_id, kids))


# --------------------------------------------------------------- databases
@db_app.command("get")
def db_get(database_id: str) -> None:
    """Retrieve a database (its property schema)."""
    _run(lambda: _client().get_database(database_id))


@db_app.command("query")
def db_query(database_id: str,
             filter_json: str = typer.Option(None, "--filter", help="JSON filter object"),
             sorts_json: str = typer.Option(None, "--sorts", help="JSON sorts array"),
             page_size: int = typer.Option(None, "--page-size"),
             start_cursor: str = typer.Option(None, "--start-cursor")) -> None:
    """Query a database with a filter and/or sorts (the T2 query grammar)."""
    flt = _parse_json(filter_json, "--filter")
    sorts = _parse_json(sorts_json, "--sorts")
    _run(lambda: _client().query_database(database_id, filter_obj=flt, sorts=sorts,
                                          page_size=page_size, start_cursor=start_cursor))


# --------------------------------------------------------------- search
@app.command()
def search(query: str = typer.Argument(""),
           object_type: str = typer.Option(None, "--type", help="page | database"),
           direction: str = typer.Option(None, "--direction", help="ascending | descending"),
           page_size: int = typer.Option(None, "--page-size")) -> None:
    """Search pages and databases by title."""
    _run(lambda: _client().search(query, object_type=object_type, sort_direction=direction,
                                  page_size=page_size))


# --------------------------------------------------------------- comments
@comments_app.command("list")
def comments_list(block_id: str) -> None:
    """List comments on a page (block_id = page id)."""
    _run(lambda: _client().list_comments(block_id))


@comments_app.command("add")
def comments_add(page_id: str, message: str = typer.Option(..., "-m", "--message")) -> None:
    """Add a comment to a page."""
    _run(lambda: _client().create_comment(page_id, rich_text(message)))


# --------------------------------------------------------------- users
@users_app.command("list")
def users_list(page_size: int = typer.Option(None, "--page-size")) -> None:
    """List workspace users."""
    _run(lambda: _client().list_users(page_size=page_size))


@users_app.command("get")
def users_get(user_id: str) -> None:
    """Retrieve a user by id."""
    _run(lambda: _client().get_user(user_id))


@users_app.command("me")
def users_me() -> None:
    """Retrieve the bot/integration user."""
    _run(lambda: _client().me())


# --------------------------------------------------------------- seed (offline)
@seed_app.command("generate")
def seed_generate(out: str = typer.Option("notion.db", "--out"),
                  workspace: str = typer.Option("Acme Engineering", "--workspace"),
                  seed: int = typer.Option(0, "--seed"),
                  emit: str = typer.Option(None, "--emit", help="also write the canonical seed JSON here")) -> None:
    """Generate a deterministic synthetic Notion workspace into a SQLite db."""
    from ..seed import schema
    from ..seed.generator import generate
    from ..seed.load import load_seed

    sd = generate(workspace=workspace, seed=seed)
    counts = load_seed(sd, out)
    if emit:
        open(emit, "w").write(schema.to_json(sd))
    typer.echo(json.dumps({"db": out, **counts}))


@seed_app.command("load")
def seed_load(fixture_json: str, out: str = typer.Option("notion.db", "--out")) -> None:
    """Load a hand-authored canonical seed JSON into a SQLite db."""
    from ..seed.load import load_seed

    sd = json.load(open(fixture_json))
    counts = load_seed(sd, out)
    typer.echo(json.dumps({"db": out, **counts}))


if __name__ == "__main__":
    app()
