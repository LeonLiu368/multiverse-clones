"""`gws-cli` — thin HTTP client over the gworkspace API, plus `seed` verbs.

Client commands (drive / docs) call ``$GWS_API_URL`` (default http://localhost:8080)
with an ``Authorization: Bearer $GWS_TOKEN`` header. The derived ``docs text`` /
``docs search`` walk the document body locally (the real Docs API has no such
endpoints), reusing ``store`` helpers. ``seed`` builds a SQLite db offline.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
import typer

from ..store import document_text, iter_paragraphs

app = typer.Typer(no_args_is_help=True, help="Google Workspace clone CLI")
drive_app = typer.Typer(no_args_is_help=True, help="drive: ls / get")
docs_app = typer.Typer(no_args_is_help=True, help="docs: get / text / search")
seed_app = typer.Typer(no_args_is_help=True, help="seed: load / import-real")
app.add_typer(drive_app, name="drive")
app.add_typer(docs_app, name="docs")
app.add_typer(seed_app, name="seed")


def _api() -> str:
    return os.environ.get("GWS_API_URL", "http://localhost:8080").rstrip("/")


def _token() -> str:
    return os.environ.get("GWS_TOKEN", "gws-clone-token")


def get(path: str, **params: Any) -> dict:
    clean = {k: v for k, v in params.items() if v is not None}
    try:
        r = httpx.get(f"{_api()}{path}", params=clean,
                      headers={"Authorization": f"Bearer {_token()}"}, timeout=30)
        data = r.json()
    except Exception as e:
        typer.secho(f"error: {e}", fg="red", err=True); raise typer.Exit(1)
    if r.status_code >= 400 or (isinstance(data, dict) and "error" in data):
        msg = data.get("error", {}).get("message", f"HTTP {r.status_code}") if isinstance(data, dict) else r.status_code
        typer.secho(f"error: {msg}", fg="red", err=True); raise typer.Exit(1)
    return data


def _emit(o: Any) -> None:
    typer.echo(json.dumps(o, indent=2))


# ---------------- drive ----------------
@drive_app.command("ls")
def drive_ls(query: str = typer.Option(None, "--query", "-q", help="Drive q, e.g. \"name contains 'plan'\""),
             fmt: str = typer.Option("json", "--format")) -> None:
    data = get("/drive/v3/files", q=query)
    if fmt == "markdown":
        for f in data["files"]:
            typer.echo(f"{f['id']}  {f['mimeType'].split('.')[-1]:<14} {f['name']}")
    else:
        _emit(data)


@drive_app.command("get")
def drive_get(file_id: str) -> None:
    _emit(get(f"/drive/v3/files/{file_id}"))


# ---------------- docs ----------------
@docs_app.command("get")
def docs_get(document_id: str) -> None:
    _emit(get(f"/v1/documents/{document_id}"))


@docs_app.command("text")
def docs_text(document_id: str) -> None:
    """Extract the document's plain text (derived, client-side)."""
    body = get(f"/v1/documents/{document_id}").get("body", {})
    typer.echo(document_text(body))


@docs_app.command("search")
def docs_search(document_id: str, query: str) -> None:
    """Find paragraphs containing the query (case-insensitive)."""
    body = get(f"/v1/documents/{document_id}").get("body", {})
    q = query.lower()
    out = [{"style": st, "text": t.strip()} for st, t in iter_paragraphs(body) if q in t.lower()]
    _emit(out)


# ---------------- seed (offline) ----------------
@seed_app.command("load")
def seed_load(fixture_json: str, out: str = typer.Option("gws.db", "--out")) -> None:
    from ..seed.load import load_seed
    counts = load_seed(json.load(open(fixture_json)), out)
    typer.echo(json.dumps({"db": out, **counts}))


@seed_app.command("import-real")
def seed_import_real(out: str = typer.Option("gws.db", "--out"),
                     drive: str = typer.Option(None, "--drive", help="Drive files.list dump"),
                     doc: list[str] = typer.Option(None, "--doc", help="documents.get dump (repeatable)"),
                     emit: str = typer.Option(None, "--emit")) -> None:
    from ..seed import schema
    from ..seed.import_real import import_real
    from ..seed.load import load_seed
    sd = import_real(drive_list_path=drive, document_paths=list(doc or []))
    counts = load_seed(sd, out)
    if emit:
        open(emit, "w").write(schema.to_json(sd))
    typer.echo(json.dumps({"db": out, **counts}))


@seed_app.command("gen-corpus")
def seed_gen_corpus(out: str = typer.Option("gws.db", "--out"),
                    seed: int = typer.Option(42, "--seed"),
                    filler: int = typer.Option(24, "--filler"),
                    emit: str = typer.Option(None, "--emit", help="also write the corpus JSON")) -> None:
    """Build the deterministic prod corpus (needle + decoys + filler) into a db."""
    from ..seed import schema
    from ..seed.corpus import build_corpus
    from ..seed.load import load_seed
    sd = build_corpus(seed=seed, filler=filler)
    counts = load_seed(sd, out)
    if emit:
        open(emit, "w").write(schema.to_json(sd))
    typer.echo(json.dumps({"db": out, "seed": seed, **counts}))


if __name__ == "__main__":
    app()
