"""`figma-cli` — thin HTTP client over the Figma-clone API, plus `seed` subcommands.

Client commands (files / nodes / tree / node / text / search / comments /
components / styles / versions / images / projects) call the running service at
``$FIGMA_API_URL`` (default http://localhost:3000) with an ``X-Figma-Token``
header (``$FIGMA_TOKEN``, default ``figma-clone-token``). The derived read-only
helpers (``tree``/``node``/``text``/``search``) fetch the file once and walk the
node tree locally — the real Figma API has no such endpoints, so we keep the API
faithful and put the convenience in the client. ``seed`` commands build a SQLite
db locally (synthetic generate / import a real file dump / load canonical json).
Output is JSON by default; ``--format markdown`` renders readable summaries.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import httpx
import typer

from ..store import find_node, iter_nodes

app = typer.Typer(no_args_is_help=True, help="Figma-clone CLI")
files_app = typer.Typer(no_args_is_help=True, help="files: get / nodes")
comments_app = typer.Typer(no_args_is_help=True, help="comments: list / add / delete")
components_app = typer.Typer(no_args_is_help=True, help="components / component-sets")
styles_app = typer.Typer(no_args_is_help=True, help="styles: list")
seed_app = typer.Typer(no_args_is_help=True, help="seed: generate / import-file / load")
app.add_typer(files_app, name="files")
app.add_typer(comments_app, name="comments")
app.add_typer(components_app, name="components")
app.add_typer(styles_app, name="styles")
app.add_typer(seed_app, name="seed")


def _api() -> str:
    return os.environ.get("FIGMA_API_URL", "http://localhost:3000").rstrip("/")


def _token() -> str:
    return os.environ.get("FIGMA_TOKEN", "figma-clone-token")


def _request(method: str, path: str, *, params: dict | None = None, json_body: dict | None = None) -> dict:
    headers = {"X-Figma-Token": _token()}
    clean = {k: v for k, v in (params or {}).items() if v is not None}
    try:
        r = httpx.request(method, f"{_api()}{path}", params=clean, json=json_body, headers=headers, timeout=30)
    except httpx.HTTPError as e:
        typer.secho(f"error: {e}", fg="red", err=True)
        raise typer.Exit(1)
    try:
        data = r.json()
    except Exception:
        typer.secho(f"error: HTTP {r.status_code}", fg="red", err=True)
        raise typer.Exit(1)
    if r.status_code >= 400 or (isinstance(data, dict) and data.get("err")):
        typer.secho(f"error: {data.get('err', f'HTTP {r.status_code}')}", fg="red", err=True)
        raise typer.Exit(1)
    return data


def get(path: str, **params: Any) -> dict:
    return _request("GET", path, params=params)


def _emit(obj: Any) -> None:
    typer.echo(json.dumps(obj, indent=2))


def _fetch_document(key: str) -> dict:
    return get(f"/v1/files/{key}").get("document", {})


# --------------------------------------------------------------- files
@files_app.command("get")
def files_get(key: str, ids: str = typer.Option(None, "--ids"), depth: int = typer.Option(None, "--depth"),
              fmt: str = typer.Option("json", "--format")) -> None:
    """Fetch a file (full document tree, components, styles)."""
    data = get(f"/v1/files/{key}", ids=ids, depth=depth)
    if fmt == "markdown":
        typer.echo(f"# {data.get('name')}  (v{data.get('version')}, {data.get('lastModified')})")
        typer.echo(f"components: {len(data.get('components', {}))}  styles: {len(data.get('styles', {}))}")
        typer.echo(_render_tree(data.get("document", {}), max_depth=2))
    else:
        _emit(data)


@files_app.command("nodes")
def files_nodes(key: str, ids: str = typer.Option(..., "--ids"), depth: int = typer.Option(None, "--depth")) -> None:
    """Fetch specific node subtrees by id (comma-separated)."""
    _emit(get(f"/v1/files/{key}/nodes", ids=ids, depth=depth))


# --------------------------------------------------------------- derived (client-side walk)
@app.command()
def tree(key: str, depth: int = typer.Option(4, "--depth")) -> None:
    """Print the node tree (id, type, name) to a given depth."""
    typer.echo(_render_tree(_fetch_document(key), max_depth=depth))


@app.command()
def node(key: str, node_id: str) -> None:
    """Inspect a single node: type, fills, style, characters, layout, bbox."""
    n = find_node(_fetch_document(key), node_id)
    if n is None:
        typer.secho(f"error: node {node_id} not found", fg="red", err=True)
        raise typer.Exit(1)
    keep = ("id", "name", "type", "characters", "fills", "strokes", "style", "cornerRadius",
            "layoutMode", "itemSpacing", "paddingLeft", "paddingRight", "paddingTop", "paddingBottom",
            "primaryAxisAlignItems", "counterAxisAlignItems", "absoluteBoundingBox")
    _emit({k: n[k] for k in keep if k in n})


@app.command()
def text(key: str, fmt: str = typer.Option("json", "--format")) -> None:
    """Extract every TEXT node's characters (id, name, text)."""
    out = [{"id": n.get("id"), "name": n.get("name"), "characters": n.get("characters", "")}
           for n in iter_nodes(_fetch_document(key)) if n.get("type") == "TEXT"]
    if fmt == "markdown":
        for t in out:
            typer.echo(f"[{t['id']}] {t['name']}: {t['characters']}")
    else:
        _emit(out)


@app.command()
def search(key: str, query: str) -> None:
    """Find nodes whose name or text contains the query (case-insensitive)."""
    q = query.lower()
    out = []
    for n in iter_nodes(_fetch_document(key)):
        name = str(n.get("name", ""))
        chars = str(n.get("characters", ""))
        if q in name.lower() or q in chars.lower():
            out.append({"id": n.get("id"), "type": n.get("type"), "name": name,
                        "characters": chars or None})
    _emit(out)


# --------------------------------------------------------------- comments
@comments_app.command("list")
def comments_list(key: str, fmt: str = typer.Option("json", "--format")) -> None:
    data = get(f"/v1/files/{key}/comments")
    if fmt == "markdown":
        for c in data["comments"]:
            who = (c.get("user") or {}).get("handle", "?")
            node_id = (c.get("client_meta") or {}).get("node_id", "")
            at = f" @{node_id}" if node_id else ""
            typer.echo(f"[{c['id']}]{at} {who}: {c['message']}")
    else:
        _emit(data)


@comments_app.command("add")
def comments_add(key: str, message: str = typer.Option(..., "-m", "--message"),
                 node: str = typer.Option(None, "--node"),
                 reply_to: str = typer.Option(None, "--reply-to")) -> None:
    """Post a comment, optionally anchored to a node (--node) or as a reply (--reply-to)."""
    body: dict[str, Any] = {"message": message}
    if node:
        body["client_meta"] = {"node_id": node}
    if reply_to:
        body["comment_id"] = reply_to
    _emit(_request("POST", f"/v1/files/{key}/comments", json_body=body))


@comments_app.command("delete")
def comments_delete(key: str, comment_id: str) -> None:
    _emit(_request("DELETE", f"/v1/files/{key}/comments/{comment_id}"))


# --------------------------------------------------------------- components / styles / versions / images
@components_app.command("list")
def components_list(key: str) -> None:
    _emit(get(f"/v1/files/{key}/components"))


@components_app.command("sets")
def component_sets(key: str) -> None:
    _emit(get(f"/v1/files/{key}/component_sets"))


@styles_app.command("list")
def styles_list(key: str, fmt: str = typer.Option("json", "--format")) -> None:
    data = get(f"/v1/files/{key}/styles")
    if fmt == "markdown":
        for st in data["meta"]["styles"]:
            typer.echo(f"[{st['node_id']}] {st['style_type']}: {st['name']} — {st['description']}")
    else:
        _emit(data)


@app.command()
def versions(key: str) -> None:
    _emit(get(f"/v1/files/{key}/versions"))


@app.command()
def images(key: str, ids: str = typer.Option(..., "--ids"), format: str = typer.Option("png", "--img-format"),
           scale: float = typer.Option(None, "--scale")) -> None:
    """Get rendered image URLs for node ids."""
    _emit(get(f"/v1/images/{key}", ids=ids, format=format, scale=scale))


# --------------------------------------------------------------- teams / projects
@app.command()
def projects(team_id: str) -> None:
    _emit(get(f"/v1/teams/{team_id}/projects"))


@app.command("project-files")
def project_files(project_id: str) -> None:
    _emit(get(f"/v1/projects/{project_id}/files"))


@app.command()
def me() -> None:
    _emit(get("/v1/me"))


# --------------------------------------------------------------- rendering helpers
def _render_tree(node: dict, *, max_depth: int = 4, _depth: int = 0, _prefix: str = "") -> str:
    if not node:
        return ""
    label = f"{node.get('id','?')} {node.get('type','')} \"{node.get('name','')}\""
    chars = node.get("characters")
    if chars:
        label += f"  = {chars!r}"
    lines = [_prefix + label]
    if _depth >= max_depth:
        kids = node.get("children") or []
        if kids:
            lines.append(_prefix + f"  … {len(kids)} more")
        return "\n".join(lines)
    for c in node.get("children", []) or []:
        lines.append(_render_tree(c, max_depth=max_depth, _depth=_depth + 1, _prefix=_prefix + "  "))
    return "\n".join(lines)


# --------------------------------------------------------------- seed (offline)
@seed_app.command("generate")
def seed_generate(out: str = typer.Option("figma.db", "--out"),
                  name: str = typer.Option("Design System", "--name"),
                  seed: int = typer.Option(0, "--seed"),
                  emit: str = typer.Option(None, "--emit", help="also write the canonical seed JSON here")) -> None:
    """Generate a deterministic synthetic Figma file into a SQLite db."""
    from ..seed import schema
    from ..seed.generator import generate
    from ..seed.load import load_seed

    sd = generate(file_name=name, seed=seed)
    counts = load_seed(sd, out)
    if emit:
        open(emit, "w").write(schema.to_json(sd))
    typer.echo(json.dumps({"db": out, **counts}))


@seed_app.command("import-file")
def seed_import_file(file_dump: str, out: str = typer.Option("figma.db", "--out"),
                     comments: str = typer.Option(None, "--comments"),
                     versions: str = typer.Option(None, "--versions"),
                     key: str = typer.Option(None, "--key"),
                     emit: str = typer.Option(None, "--emit")) -> None:
    """Import a real `GET /v1/files/:key` JSON dump into a SQLite db."""
    from ..seed import schema
    from ..seed.import_file import import_file
    from ..seed.load import load_seed

    sd = import_file(file_dump, file_key=key, comments_path=comments, versions_path=versions)
    counts = load_seed(sd, out)
    if emit:
        open(emit, "w").write(schema.to_json(sd))
    typer.echo(json.dumps({"db": out, **counts}))


@seed_app.command("load")
def seed_load(fixture_json: str, out: str = typer.Option("figma.db", "--out")) -> None:
    """Load a hand-authored canonical seed JSON into a SQLite db."""
    from ..seed.load import load_seed

    sd = json.load(open(fixture_json))
    counts = load_seed(sd, out)
    typer.echo(json.dumps({"db": out, **counts}))


if __name__ == "__main__":
    app()
