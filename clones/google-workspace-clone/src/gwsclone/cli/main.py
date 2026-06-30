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
cal_app = typer.Typer(no_args_is_help=True, help="calendar: events / get")
gmail_app = typer.Typer(no_args_is_help=True, help="gmail: search / get / thread")
seed_app = typer.Typer(no_args_is_help=True, help="seed: load / import-real")
app.add_typer(drive_app, name="drive")
app.add_typer(docs_app, name="docs")
app.add_typer(cal_app, name="calendar")
app.add_typer(gmail_app, name="gmail")
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


def post(path: str, body: dict) -> dict:
    try:
        r = httpx.post(f"{_api()}{path}", json=body,
                       headers={"Authorization": f"Bearer {_token()}"}, timeout=30)
        data = r.json()
    except Exception as e:
        typer.secho(f"error: {e}", fg="red", err=True); raise typer.Exit(1)
    if r.status_code >= 400 or (isinstance(data, dict) and "error" in data):
        msg = data.get("error", {}).get("message", f"HTTP {r.status_code}") if isinstance(data, dict) else r.status_code
        typer.secho(f"error: {msg}", fg="red", err=True); raise typer.Exit(1)
    return data


def get_text(path: str, **params: Any) -> str:
    """GET an endpoint that returns plain text (e.g. files.export)."""
    clean = {k: v for k, v in params.items() if v is not None}
    try:
        r = httpx.get(f"{_api()}{path}", params=clean,
                      headers={"Authorization": f"Bearer {_token()}"}, timeout=30)
    except Exception as e:
        typer.secho(f"error: {e}", fg="red", err=True); raise typer.Exit(1)
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {}).get("message", f"HTTP {r.status_code}")
        except Exception:
            msg = f"HTTP {r.status_code}"
        typer.secho(f"error: {msg}", fg="red", err=True); raise typer.Exit(1)
    return r.text


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


@drive_app.command("export")
def drive_export(file_id: str) -> None:
    """Print a file's text content (works for Docs, .docx/.pptx, .txt/.html, PDFs)."""
    typer.echo(get_text(f"/drive/v3/files/{file_id}/export"))


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


# ---------------- calendar ----------------
@cal_app.command("events")
def cal_events(calendar: str = typer.Option("primary", "--calendar", "-c"),
               query: str = typer.Option(None, "--query", "-q", help="free-text over summary/desc/location"),
               time_min: str = typer.Option(None, "--time-min", help="RFC-3339 lower bound on start"),
               time_max: str = typer.Option(None, "--time-max", help="RFC-3339 upper bound on start"),
               fmt: str = typer.Option("json", "--format")) -> None:
    data = get(f"/calendar/v3/calendars/{calendar}/events", q=query, timeMin=time_min, timeMax=time_max)
    if fmt == "markdown":
        for e in data["items"]:
            when = e["start"].get("dateTime") or e["start"].get("date") or "?"
            typer.echo(f"{e['id']}  {when}  {e['summary']}")
    else:
        _emit(data)


@cal_app.command("get")
def cal_get(event_id: str, calendar: str = typer.Option("primary", "--calendar", "-c")) -> None:
    _emit(get(f"/calendar/v3/calendars/{calendar}/events/{event_id}"))


@cal_app.command("create")
def cal_create(summary: str = typer.Option(..., "--summary", "-s", help="event title"),
               start: str = typer.Option(..., "--start", help="RFC-3339 dateTime or YYYY-MM-DD"),
               end: str = typer.Option(..., "--end", help="RFC-3339 dateTime or YYYY-MM-DD"),
               calendar: str = typer.Option("primary", "--calendar", "-c"),
               location: str = typer.Option(None, "--location"),
               description: str = typer.Option(None, "--description")) -> None:
    """Create a Calendar event (events.insert). Prints the created event resource."""
    body: dict = {"summary": summary, "start": start, "end": end}
    if location is not None:
        body["location"] = location
    if description is not None:
        body["description"] = description
    _emit(post(f"/calendar/v3/calendars/{calendar}/events", body))


# ---------------- gmail ----------------
@gmail_app.command("search")
def gmail_search(query: str = typer.Argument(None, help="Gmail query, e.g. \"from:bob subject:launch\""),
                 user: str = typer.Option("me", "--user", "-u"),
                 fmt: str = typer.Option("json", "--format")) -> None:
    data = get(f"/gmail/v1/users/{user}/messages", q=query)
    if fmt == "markdown":
        for r in data["messages"]:
            typer.echo(f"{r['id']}  thread={r['threadId']}")
    else:
        _emit(data)


@gmail_app.command("get")
def gmail_get(message_id: str, user: str = typer.Option("me", "--user", "-u"),
              text: bool = typer.Option(False, "--text", help="print just the decoded body")) -> None:
    data = get(f"/gmail/v1/users/{user}/messages/{message_id}")
    if text:
        typer.echo(_gmail_body_text(data))
    else:
        _emit(data)


@gmail_app.command("thread")
def gmail_thread(thread_id: str, user: str = typer.Option("me", "--user", "-u"),
                 text: bool = typer.Option(False, "--text", help="print each message's headers + body")) -> None:
    data = get(f"/gmail/v1/users/{user}/threads/{thread_id}")
    if text:
        for m in data["messages"]:
            h = {x["name"]: x["value"] for x in m["payload"]["headers"]}
            typer.echo(f"From: {h.get('From','')}\nSubject: {h.get('Subject','')}\nDate: {h.get('Date','')}\n\n{_gmail_body_text(m)}\n{'-'*48}")
    else:
        _emit(data)


def _gmail_body_text(message: dict) -> str:
    import base64
    data = (message.get("payload", {}).get("body", {}) or {}).get("data", "")
    if not data:
        return message.get("snippet", "")
    return base64.urlsafe_b64decode(data.encode()).decode(errors="replace")


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


@seed_app.command("import-takeout")
def seed_import_takeout(out: str = typer.Option("gws.db", "--out"),
                        root: str = typer.Option(None, "--root", help="unzipped Takeout/ dir (auto-discovers Mail/Calendar/Drive)"),
                        mbox: str = typer.Option(None, "--mbox", help="a single .mbox export"),
                        ics: str = typer.Option(None, "--ics", help="a single .ics export"),
                        drive: str = typer.Option(None, "--drive", help="a Drive export dir"),
                        limit: int = typer.Option(None, "--limit", help="cap items per surface"),
                        emit: str = typer.Option(None, "--emit", help="also write the seed JSON")) -> None:
    """Ingest a Google Takeout export (Gmail .mbox / Calendar .ics / Drive tree)."""
    from ..seed import schema
    from ..seed.load import load_seed
    from ..seed.takeout import import_takeout
    sd = import_takeout(root=root, mbox=mbox, ics=ics, drive_dir=drive, limit=limit)
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
