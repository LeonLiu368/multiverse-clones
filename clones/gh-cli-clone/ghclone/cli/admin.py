"""ghc-hydrate — OPERATOR CLI for building/hydrating worlds.

Kept SEPARATE from the agent-facing `ghc` on purpose: hydration, migration, and
point-in-time replay are things the *task author / harness* does to construct a
world, not things the agent under test should be able to call. The `gh` shim and
the agent MCP expose only the gh-parity surface; these live here.
"""

from __future__ import annotations

import json as _json
import os

import typer
from rich.console import Console

from ghclone import config
from ghclone.forge import ForgejoClient, ForgejoError

app = typer.Typer(no_args_is_help=True,
                  help="Operator tools: hydrate GitHub repos into the local host (NOT agent-facing).")
console = Console()
err = Console(stderr=True)


def _client() -> ForgejoClient:
    cfg = config.resolve()
    if not cfg.token:
        err.print("[red]Not authenticated.[/red] Set GHC_TOKEN.")
        raise typer.Exit(4)
    return ForgejoClient(cfg)


def _out(data) -> None:
    console.print_json(_json.dumps(data, default=str))


@app.command("migrate")
def migrate(github_url: str = typer.Argument(..., help="https://github.com/OWNER/REPO(.git)"),
            into: str = typer.Option(None, "--into", help="target OWNER/REPO"),
            token: str = typer.Option(None, "--token", help="GitHub PAT; else $GH_TOKEN"),
            mirror: bool = typer.Option(False, "--mirror")):
    """Engine A: one-call native migrate (git + issues + PRs + labels + milestones + releases)."""
    clone_addr = github_url if github_url.endswith(".git") else github_url + ".git"
    src = clone_addr.rstrip("/").rsplit("/", 1)[-1][:-4]
    c = _client()
    owner, name = ((into.split("/", 1)) if into else (c.cfg.user or c.whoami().get("login"), src))
    data = c.migrate_repo(clone_addr=clone_addr, repo_owner=owner, repo_name=name,
                          auth_token=token or os.getenv("GH_TOKEN"), mirror=mirror)
    console.print(f"[green]✓[/green] migrated → {data['full_name']}  {data['html_url']}")


@app.command("snapshot")
def snapshot(owner_repo: str, out: str = typer.Option(..., "--out"),
             token: str = typer.Option(None, "--token"), resume: bool = False):
    """Engine B stage 1: freeze a GitHub repo to a local snapshot artifact."""
    from ghclone.hydrate import snapshot as snap
    res = snap.snapshot(owner_repo, out, token=token or os.getenv("GH_TOKEN"), resume=resume)
    console.print(f"[green]✓[/green] snapshot → {out}")
    _out(res)


@app.command("apply")
def apply(snapshot_dir: str, into: str = typer.Option(..., "--into"),
          users: str = typer.Option(None, "--users"),
          as_of: str = typer.Option(None, "--as-of",
                                    help="commit SHA or ISO timestamp: hydrate state AT that point"),
          dry_run: bool = typer.Option(False, "--dry-run")):
    """Engine B stage 2: replay a snapshot into Forgejo (offline). --as-of for point-in-time."""
    from ghclone.hydrate import apply as ap
    res = ap.apply(snapshot_dir, into, users_map=users, as_of=as_of, dry_run=dry_run,
                   client=None if dry_run else _client())
    if dry_run:
        console.print("[bold]apply plan:[/bold]")
        for s in res["steps"]:
            console.print(f"  • {s}")
    else:
        _out(res)


@app.command("verify")
def verify(snapshot_dir: str, against: str = typer.Option(..., "--against"),
           sample: int = typer.Option(10, "--sample")):
    """Diff a snapshot against a hydrated repo; non-zero exit on silent drops."""
    from ghclone.hydrate import verify as vf
    report = vf.verify(snapshot_dir, against, client=_client(), sample=sample)
    _out(report)
    raise typer.Exit(0 if report.get("ok") else 1)


def _main():
    try:
        app()
    except ForgejoError as e:
        err.print(f"[red]error:[/red] {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    _main()
