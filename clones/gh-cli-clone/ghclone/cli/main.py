"""A gh-compatible CLI for repositories, issues, and pull requests.

Command groups mirror `gh`: auth, repo, issue, pr, label, milestone, run,
workflow, api. Each maps gh semantics onto ForgejoClient. `--repo OWNER/REPO`
mirrors gh's `-R`; `--json` emits raw JSON for scripting parity.

Operator-only world-building (hydrate/migrate) is deliberately NOT here — it
lives in `ghc-hydrate` (ghclone/cli/admin.py) so the agent can't reach it.
"""

from __future__ import annotations

import json as _json
import sys
from pathlib import Path
from urllib.parse import urlparse as _urlparse

import typer
from rich.console import Console

# Typer vendors its own Click fork; usage errors raised under standalone_mode=False
# are that fork's classes, not the top-level `click` package's. Catch the base.
try:
    from typer._click.exceptions import Abort as _Abort, UsageError as _UsageError
except Exception:  # pragma: no cover - fallback for other Typer/Click layouts
    from click.exceptions import Abort as _Abort, UsageError as _UsageError

from ghclone import config
from ghclone.cli import ghfmt, ghjson
from ghclone.forge import ForgejoClient, ForgejoError, gitutil
from ghclone.forge import actions_overlay as actions

# Presented as real gh's version string (gh `--version`) so the surface matches.
GH_VERSION = "2.89.0"
GH_VERSION_DATE = "2026-03-26"

def _typer(**kw) -> typer.Typer:
    # rich_markup_mode=None + pretty_exceptions_enable=False make Typer fall back
    # to Click's PLAIN error/usage output. Real `gh` (a Go/cobra binary) prints
    # plain-text errors, not rich-bordered panels — the boxed `╭─ Error ─╮` style
    # is what tipped one agent off that `gh` was a wrapper. This removes that tell.
    return typer.Typer(no_args_is_help=True, rich_markup_mode=None,
                       pretty_exceptions_enable=False, **kw)


# add_completion=False hides Typer's `--install-completion` / `--show-completion`
# options, which real gh doesn't have and which would expose the framework.
app = _typer(add_completion=False,
             help="Work seamlessly with repositories, issues, and pull requests from the command line.")
console = Console()
err = Console(stderr=True)

auth = _typer(help="Authenticate gh and git with a host.")
repo = _typer(help="Manage repositories.")
issue = _typer(help="Manage issues.")
pr = _typer(help="Manage pull requests.")
label = _typer(help="Manage labels.")
milestone = _typer(help="Manage milestones.")
run = _typer(help="View Actions runs.")
workflow = _typer(help="Manage Actions workflows.")
release = _typer(help="Manage releases.")
# NOTE: hydration/migration are OPERATOR tools and intentionally NOT here — they
# live in the separate `ghc-hydrate` entrypoint (ghclone/cli/admin.py) so the
# agent under test can't call them through the `gh` surface.
# real gh has no top-level `milestone` command, so it's hidden from help listings
# (still callable for tasks that need it — milestones aren't a gh CLI primitive).
_HIDDEN_GROUPS = {"milestone"}
for t, n in [(auth, "auth"), (repo, "repo"), (issue, "issue"), (pr, "pr"),
             (label, "label"), (milestone, "milestone"), (run, "run"),
             (workflow, "workflow"), (release, "release")]:
    app.add_typer(t, name=n, hidden=(n in _HIDDEN_GROUPS))


def client() -> ForgejoClient:
    cfg = config.resolve()
    if not cfg.token:
        err.print("[red]Not authenticated.[/red] Run `gh auth login` or set GH_TOKEN.")
        raise typer.Exit(4)
    return ForgejoClient(cfg)


def gh_table(columns: list[str], rows: list[list]) -> None:
    """Print a list like real gh: borderless. To a TTY, gh shows UPPERCASE headers
    with space-aligned columns; piped, it emits tab-separated values with no
    header. (gh never draws box-borders — rich tables would be a tell.)"""
    rows = [[("" if c is None else str(c)) for c in r] for r in rows]
    if not sys.stdout.isatty():
        for r in rows:
            print("\t".join(r))
        return
    header = [c.upper() for c in columns]
    widths = [max(len(header[i]), *(len(r[i]) for r in rows)) if rows else len(header[i])
              for i in range(len(columns))]
    def line(cells):
        return "  ".join(cells[i].ljust(widths[i]) for i in range(len(columns))).rstrip()
    console.print(line(header), highlight=False)
    for r in rows:
        console.print(line(r), highlight=False)


def _fuzzy_ago(iso: str) -> str:
    """gh's relative time: 'about N hours ago', 'about 1 day ago', etc."""
    if not iso:
        return ""
    from datetime import datetime, timezone
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return iso
    secs = (datetime.now(timezone.utc) - t).total_seconds()
    if secs < 60:
        return "less than a minute ago"
    units = [(60, "minute"), (3600, "hour"), (86400, "day"), (2592000, "month"), (31536000, "year")]
    label, div = "year", 31536000
    for thresh, name in units:
        nxt = {"minute": 3600, "hour": 86400, "day": 2592000, "month": 31536000, "year": 1 << 62}[name]
        if secs < nxt:
            label, div = name, thresh
            break
    n = int(secs // div)
    return f"about {n} {label}{'s' if n != 1 else ''} ago"


def gh_list(summary: str, tty_cols: list[str], tty_rows: list[list],
            piped_rows: list[list]) -> None:
    """Render a list like real gh: piped → TSV (no header); TTY → a
    `Showing N of M … in TARGET` line, a blank line, then UPPERCASE columns."""
    if not sys.stdout.isatty():
        for r in piped_rows:
            print("\t".join("" if c is None else str(c) for c in r))
        return
    if summary:
        console.print(summary, highlight=False)
        console.print("")
    rows = [[("" if c is None else str(c)) for c in r] for r in tty_rows]
    header = [c.upper() for c in tty_cols]
    widths = [max([len(header[i])] + [len(r[i]) for r in rows]) for i in range(len(tty_cols))]
    def line(cells):
        return "  ".join(cells[i].ljust(widths[i]) for i in range(len(tty_cols))).rstrip()
    console.print(line(header), highlight=False)
    for r in rows:
        console.print(line(r), highlight=False)


def gh_view(fields: list[tuple[str, str]], body: str = "") -> None:
    """Render a detail view like real gh's non-TTY format: `key:\\tvalue` lines,
    a `--` separator, then the body. (gh's TTY card is colorized/relative-time;
    the raw format is gh's deterministic piped output.)"""
    for k, v in fields:
        console.print(f"{k}:\t{v}", highlight=False)
    console.print("--", highlight=False)
    if body:
        console.print(body, highlight=False)


def split_repo(value: str) -> tuple[str, str]:
    if not value or "/" not in value:
        err.print("[red]--repo must be OWNER/REPO[/red]")
        raise typer.Exit(2)
    owner, name = value.split("/", 1)
    return owner, name


def out_json(data) -> None:
    console.print_json(_json.dumps(data, default=str))


def gh_url(url: str | None) -> str:
    """Normalize a web URL to GitHub's path shape before showing it.

    The backend serves PR pages at /pulls/<n> (plural); GitHub uses /pull/<n>
    (singular). Rewriting the displayed URL removes that last shape tell. Agents
    drive PRs by number, never by URL, so display-only is safe.
    """
    return (url or "").replace("/pulls/", "/pull/")


def repo_opt():
    return typer.Option(..., "--repo", "-R", help="OWNER/REPO")


# ================= auth =================
@auth.command("login")
def auth_login(host: str = typer.Option(config.DEFAULT_HOST, "--host"),
               token: str = typer.Option(None, "--token", help="API token; else read stdin.")):
    """Store a token for HOST (gh auth login)."""
    token = token or sys.stdin.readline().strip()
    cfg = config.HostConfig(host=host, token=token)
    who = ForgejoClient(cfg).whoami()
    config.save_host(host, token, who.get("login"))
    cfg.user = who.get("login")
    gitutil.ensure_credentials(cfg)  # configure git auth like `gh auth login` does
    err.print(f"[green]✓[/green] Logged in as [bold]{who.get('login')}[/bold]")


@auth.command("status")
def auth_status():
    """Show auth state (gh auth status)."""
    cfg = config.resolve()
    netloc = _urlparse(cfg.host).netloc or cfg.host
    if not cfg.token:
        err.print(f"[bold]{netloc}[/bold]")
        err.print(f"  [red]X[/red] Not logged in to {netloc}")
        raise typer.Exit(1)
    who = ForgejoClient(cfg).whoami()
    # gh's status block, verbatim shape (token masked like `gh auth status`).
    console.print(f"[bold]{netloc}[/bold]")
    console.print(f"  [green]✓[/green] Logged in to {netloc} account [bold]{who.get('login')}[/bold] (GH_TOKEN)")
    console.print("  - Active account: [bold]true[/bold]")
    console.print("  - Git operations protocol: [bold]https[/bold]")
    console.print(f"  - Token: [bold]{'*' * 19}[/bold]")


@auth.command("logout")
def auth_logout(host: str = typer.Option(config.DEFAULT_HOST, "--host")):
    """Forget the stored token for HOST."""
    hosts = config._load_hosts()
    user = (hosts.get(host) or {}).get("user", "")
    netloc = _urlparse(host).netloc or host
    if host in hosts:
        del hosts[host]
        config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config.HOSTS_FILE.write_text(_json.dumps(hosts, indent=2))
    err.print(f"[green]✓[/green] Logged out of {netloc} account {user}".rstrip())


@auth.command("token")
def auth_token():
    """Print the stored token (gh auth token)."""
    cfg = config.resolve()
    if not cfg.token:
        raise typer.Exit(1)
    console.print(cfg.token)


# ================= repo =================
@repo.command("list")
def repo_list(owner: str = typer.Argument(None), limit: int = 30,
              json: str = typer.Option(None, "--json", help="Output JSON with the specified fields"), jq: str = typer.Option(None, "-q", "--jq", help="Query the output using a jq expression")):
    """List repos (gh repo list)."""
    repos = client().list_repos(owner=owner, limit=limit)
    if json:
        return ghjson.export(repos, ghjson.REPO, json, jq)
    n = len(repos)
    who = f"@{owner}" if owner else "you"
    def vis(r):
        return "private" if r["private"] else "public"
    def info(r):
        return "private" if r["private"] else ("public archived" if r.get("archived") else "public")
    gh_list(
        f"Showing {n} of {n} repositories in {who}",
        ["NAME", "DESCRIPTION", "INFO", "UPDATED"],
        [[r["full_name"], r.get("description") or "", info(r), _fuzzy_ago(r.get("updated_at", ""))] for r in repos],
        [[r["full_name"], r.get("description") or "", vis(r), r.get("updated_at", "")] for r in repos])


@repo.command("view")
def repo_view(name: str = typer.Argument(..., help="OWNER/REPO"),
              json: str = typer.Option(None, "--json", help="Output JSON with the specified fields"), jq: str = typer.Option(None, "-q", "--jq", help="Query the output using a jq expression")):
    data = client().get_repo(*split_repo(name))
    if json:
        return ghjson.export(data, ghjson.REPO, json, jq)
    gh_view([
        ("name", data["full_name"]),
        ("description", data.get("description") or ""),
    ], data.get("readme") or "")


@repo.command("create")
def repo_create(name: str, private: bool = typer.Option(False, "--private"),
                description: str = typer.Option("", "--description", "-d"),
                org: str = typer.Option(None, "--org")):
    data = client().create_repo(name=name, private=private, description=description, owner=org)
    host = _urlparse(data["html_url"]).netloc
    console.print(f"[green]✓[/green] Created repository {data['full_name']} on {host}")
    console.print(f"  {data['html_url']}")


@repo.command("delete")
def repo_delete(name: str, yes: bool = typer.Option(False, "--yes", help="skip confirm")):
    owner, r = split_repo(name)
    if not yes:
        typer.confirm(f"Delete {owner}/{r}?", abort=True)
    client().delete_repo(owner, r)
    console.print(f"[green]✓[/green] Deleted repository {owner}/{r}")


@repo.command("clone")
def repo_clone(name: str, dest: str = typer.Argument(None)):
    owner, r = split_repo(name)
    cfg = config.resolve()
    d = gitutil.clone(cfg, owner, r, dest)
    err.print(f"Cloning into '{d}'...", highlight=False)  # gh streams git's own output


@repo.command("fork")
def repo_fork(name: str, org: str = typer.Option(None, "--org")):
    owner, r = split_repo(name)
    data = client().fork_repo(owner, r, organization=org)
    err.print(f"[green]✓[/green] Created fork {data['full_name']}")


@repo.command("rename")
def repo_rename(name: str, new_name: str):
    owner, r = split_repo(name)
    data = client().edit_repo(owner, r, name=new_name)
    full = data.get("full_name", f"{owner}/{new_name}")
    console.print(f"[green]✓[/green] Renamed repository {full}")


@repo.command("edit")
def repo_edit(name: str, description: str = typer.Option(None, "--description", "-d"),
              private: bool = typer.Option(None, "--private/--public"),
              topics: str = typer.Option(None, "--topics", help="comma-separated")):
    owner, r = split_repo(name)
    c = client()
    fields = {}
    if description is not None:
        fields["description"] = description
    if private is not None:
        fields["private"] = private
    if fields:
        c.edit_repo(owner, r, **fields)
    if topics is not None:
        c.set_topics(owner, r, [t.strip() for t in topics.split(",") if t.strip()])
    # gh repo edit prints nothing on success


# ================= issue =================
@issue.command("list")
def issue_list(repo_: str = repo_opt(), state: str = "open", limit: int = 30,
               label: str = typer.Option(None, "--label", "-l"),
               milestone: str = typer.Option(None, "--milestone", "-m"),
               search: str = typer.Option(None, "--search", "-S"),
               json: str = typer.Option(None, "--json", help="Output JSON with the specified fields"), jq: str = typer.Option(None, "-q", "--jq", help="Query the output using a jq expression")):
    owner, r = split_repo(repo_)
    items = client().list_issues(owner, r, state=state, labels=label, milestones=milestone,
                                 q=search, limit=limit)
    if json:
        return ghjson.export(items, ghjson.ISSUE, json, jq)
    n = len(items)
    noun = "issues" if state == "all" else f"{state} issues"
    def labels(i):
        return ", ".join(lb["name"] for lb in i.get("labels", []))
    gh_list(
        f"Showing {n} of {n} {noun} in {owner}/{r}",
        ["ID", "TITLE", "LABELS", "UPDATED"],
        [[f"#{i['number']}", i["title"], labels(i), _fuzzy_ago(i.get("updated_at", ""))] for i in items],
        [[i["number"], str(i.get("state", "")).upper(), i["title"], labels(i), i.get("updated_at", "")] for i in items])


@issue.command("view")
def issue_view(number: int, repo_: str = repo_opt(),
               comments: bool = typer.Option(False, "--comments", "-c"),
               json: str = typer.Option(None, "--json", help="Output JSON with the specified fields"), jq: str = typer.Option(None, "-q", "--jq", help="Query the output using a jq expression")):
    owner, r = split_repo(repo_)
    c = client()
    data = c.get_issue(owner, r, number)
    if json:
        return ghjson.export(data, ghjson.ISSUE, json, jq)
    gh_view([
        ("title", data.get("title", "")),
        ("state", str(data.get("state", "")).upper()),
        ("author", (data.get("user") or {}).get("login", "")),
        ("labels", ", ".join(lb["name"] for lb in data.get("labels") or [])),
        ("comments", str(data.get("comments", 0))),
        ("assignees", ", ".join(a["login"] for a in data.get("assignees") or [])),
        ("milestone", (data.get("milestone") or {}).get("title", "")),
        ("number", str(data.get("number", number))),
    ], data.get("body") or "")
    if comments:
        for cm in c.list_comments(owner, r, number):
            console.print(f"\n{cm['user']['login']}: {cm['body']}", highlight=False)


@issue.command("create")
def issue_create(repo_: str = repo_opt(), title: str = typer.Option(..., "--title", "-t"),
                 body: str = typer.Option("", "--body", "-b")):
    owner, r = split_repo(repo_)
    data = client().create_issue(owner, r, title=title, body=body)
    console.print(gh_url(data["html_url"]))  # gh prints just the new issue URL to stdout


@issue.command("comment")
def issue_comment(number: int, repo_: str = repo_opt(), body: str = typer.Option(..., "--body", "-b")):
    owner, r = split_repo(repo_)
    data = client().comment(owner, r, number, body)
    console.print(gh_url(data.get("html_url", "")))  # gh prints the comment URL to stdout


@issue.command("close")
def issue_close(number: int, repo_: str = repo_opt()):
    owner, r = split_repo(repo_)
    data = client().edit_issue(owner, r, number, state="closed")
    err.print(f"[red]✓[/red] Closed issue {owner}/{r}#{number} ({data.get('title','')})")


@issue.command("reopen")
def issue_reopen(number: int, repo_: str = repo_opt()):
    owner, r = split_repo(repo_)
    data = client().edit_issue(owner, r, number, state="open")
    err.print(f"[green]✓[/green] Reopened issue {owner}/{r}#{number} ({data.get('title','')})")


@issue.command("edit")
def issue_edit(number: int, repo_: str = repo_opt(),
               title: str = typer.Option(None, "--title", "-t"),
               body: str = typer.Option(None, "--body", "-b"),
               add_label: list[str] = typer.Option(None, "--add-label",
                                                   help="label name to add (repeatable)"),
               remove_label: list[str] = typer.Option(None, "--remove-label",
                                                      help="label name to remove (repeatable)"),
               milestone: str = typer.Option(None, "--milestone", "-m",
                                            help="milestone title to assign")):
    """Edit an issue (gh issue edit). Labels/milestone given by name."""
    owner, r = split_repo(repo_)
    c = client()
    fields = {k: v for k, v in (("title", title), ("body", body)) if v is not None}
    if milestone:
        ms = {m["title"]: m["id"] for m in c.list_milestones(owner, r, state="all")}
        if milestone in ms:
            fields["milestone"] = ms[milestone]
    if fields:
        c.edit_issue(owner, r, number, **fields)
    if add_label or remove_label:
        ids = {lb["name"]: lb["id"] for lb in c.list_labels(owner, r)}
        if add_label:
            c.add_issue_labels(owner, r, number, [ids[n] for n in add_label if n in ids])
        for n in (remove_label or []):
            if n in ids:
                c.remove_issue_label(owner, r, number, ids[n])
    data = c.get_issue(owner, r, number)
    console.print(gh_url(data.get("html_url", "")))  # gh issue edit prints the URL to stdout


@issue.command("react", hidden=True)  # not a real gh command — hidden from help
def issue_react(number: int, repo_: str = repo_opt(),
                content: str = typer.Option(..., "--content", "-c",
                                            help="+1, -1, laugh, hooray, confused, heart, rocket, eyes")):
    """Add a reaction to an issue/PR (gh ... reactions)."""
    owner, r = split_repo(repo_)
    client().add_reaction(owner, r, number, content)
    console.print(f"[green]✓[/green] reacted {content} on #{number}")


# ================= pr =================
@pr.command("list")
def pr_list(repo_: str = repo_opt(), state: str = "open", limit: int = 30,
            json: str = typer.Option(None, "--json", help="Output JSON with the specified fields"), jq: str = typer.Option(None, "-q", "--jq", help="Query the output using a jq expression")):
    owner, r = split_repo(repo_)
    items = client().list_prs(owner, r, state=state, limit=limit)
    if json:
        return ghjson.export(items, ghjson.PR, json, jq)
    n = len(items)
    noun = "pull requests" if state == "all" else f"{state} pull requests"
    def pstate(p):
        return "MERGED" if p.get("merged") else str(p.get("state", "")).upper()
    gh_list(
        f"Showing {n} of {n} {noun} in {owner}/{r}",
        ["ID", "TITLE", "BRANCH", "CREATED AT"],
        [[f"#{p['number']}", p["title"], p["head"]["ref"], _fuzzy_ago(p.get("created_at", ""))] for p in items],
        [[p["number"], p["title"], p["head"]["ref"], pstate(p), p.get("updated_at", "")] for p in items])


@pr.command("view")
def pr_view(number: int, repo_: str = repo_opt(), json: str = typer.Option(None, "--json", help="Output JSON with the specified fields"), jq: str = typer.Option(None, "-q", "--jq", help="Query the output using a jq expression")):
    owner, r = split_repo(repo_)
    data = client().get_pr(owner, r, number)
    if json:
        return ghjson.export(data, ghjson.PR, json, jq)
    state = "MERGED" if data.get("merged") else str(data.get("state", "")).upper()
    gh_view([
        ("title", data.get("title", "")),
        ("state", state),
        ("author", (data.get("user") or {}).get("login", "")),
        ("labels", ", ".join(lb["name"] for lb in data.get("labels") or [])),
        ("milestone", (data.get("milestone") or {}).get("title", "")),
        ("number", str(data.get("number", number))),
        ("url", gh_url(data.get("html_url", ""))),
    ], data.get("body") or "")


def _render_pr_checks(checks: list[dict]) -> int:
    """Render `gh pr checks` like real gh and return its exit code (0 ok, 1 any
    failing, 8 any pending)."""
    counts = {"pass": 0, "fail": 0, "pending": 0, "skipping": 0, "cancel": 0}
    for c in checks:
        counts[c.get("bucket", "pending")] = counts.get(c.get("bucket", "pending"), 0) + 1
    if counts["fail"] > 0:
        summary = "Some checks were not successful"
    elif counts["pending"] > 0:
        summary = "Some checks are still pending"
    else:
        summary = "All checks were successful"
    tallies = (f"{counts['cancel']} cancelled, {counts['fail']} failing, {counts['pass']} successful, "
               f"{counts['skipping']} skipped, and {counts['pending']} pending checks")

    def elapsed(c):
        e = c.get("elapsed", "")
        return "" if e in ("", "0s") else e

    if not sys.stdout.isatty():
        for c in checks:
            print("\t".join([c["name"], c.get("bucket", ""), elapsed(c), c.get("link", "")]))
    else:
        print(summary)
        print(tallies)
        print("")
        rows = [[c["icon"], c["name"], elapsed(c), c.get("link", "")] for c in checks]
        if rows:
            widths = [max(len(r[i]) for r in rows) for i in range(4)]
            for r in rows:
                print("  ".join(r[i].ljust(widths[i]) for i in range(4)).rstrip())
    if counts["fail"] > 0:
        return 1
    if counts["pending"] > 0:
        return 8
    return 0


@pr.command("checks")
def pr_checks(arg: str = typer.Argument(None, help="PR number, URL, or branch (default: current branch)"),
              repo_: str = repo_opt(),
              required: bool = typer.Option(False, "--required", help="Only show required checks"),
              json: str = typer.Option(None, "--json", help="Output JSON with the specified fields"),
              jq: str = typer.Option(None, "-q", "--jq", help="Query the output using a jq expression")):
    """Show CI status for a single pull request (gh pr checks)."""
    owner, r = split_repo(repo_)
    ov = _overlay_for(owner, r)
    if ov is not None:
        branch = sha = None
        if arg and str(arg).isdigit():
            try:  # resolve the PR's head from the live forge; fall back to latest run
                head = (client().get_pr(owner, r, int(arg)).get("head") or {})
                branch, sha = head.get("ref"), head.get("sha")
            except (ForgejoError, typer.Exit, Exception):
                pass
        elif arg:
            branch = str(arg)  # gh accepts a branch name directly
        checks = ov.checks_for_ref(owner, r, branch=branch, sha=sha)
        if required:
            checks = [c for c in checks if c.get("required")]
        if json:
            return ghjson.export(checks, ghjson.CHECK, json, jq)
        if not checks:
            err.print(f"no checks reported on the '{branch or 'default'}' branch")
            raise typer.Exit(1)
        code = _render_pr_checks(checks)
        if code:
            raise typer.Exit(code)
        return
    err.print("no checks reported")  # no Actions seed for this repo
    raise typer.Exit(1)


@pr.command("create")
def pr_create(repo_: str = repo_opt(), title: str = typer.Option(..., "--title", "-t"),
              head: str = typer.Option(..., "--head", "-H"),
              base: str = typer.Option("main", "--base", "-B"),
              body: str = typer.Option("", "--body", "-b")):
    owner, r = split_repo(repo_)
    data = client().create_pr(owner, r, title=title, head=head, base=base, body=body)
    console.print(gh_url(data["html_url"]))  # gh prints just the new PR URL to stdout


@pr.command("diff")
def pr_diff(number: int, repo_: str = repo_opt()):
    owner, r = split_repo(repo_)
    console.print(client().pr_diff(owner, r, number), highlight=False)


@pr.command("checkout")
def pr_checkout(number: int, repo_: str = repo_opt()):
    owner, r = split_repo(repo_)
    cfg = config.resolve()
    data = client().get_pr(owner, r, number)
    branch = data["head"]["ref"]
    gitutil.ensure_credentials(cfg)
    remote = gitutil.clean_remote(cfg, owner, r)
    gitutil.run(["git", "fetch", remote, f"{branch}:{branch}"])
    co = gitutil.run(["git", "checkout", branch])
    # gh prints git's own checkout output (e.g. "Switched to branch '...'")
    msg = (co.stderr or co.stdout or "").strip()
    if msg:
        err.print(msg, highlight=False)


_MERGE_ACTION = {"merge": "Merged", "rebase": "Rebased and merged",
                 "rebase-merge": "Rebased and merged", "squash": "Squashed and merged"}


@pr.command("merge")
def pr_merge(number: int, repo_: str = repo_opt(),
             method: str = typer.Option("merge", "--method", help="merge|rebase|rebase-merge|squash")):
    owner, r = split_repo(repo_)
    c = client()
    title = c.get_pr(owner, r, number).get("title", "")
    c.merge_pr(owner, r, number, method=method)
    action = _MERGE_ACTION.get(method, "Merged")
    err.print(f"[magenta]✓[/magenta] {action} pull request {owner}/{r}#{number} ({title})")


@pr.command("close")
def pr_close(number: int, repo_: str = repo_opt()):
    owner, r = split_repo(repo_)
    data = client().edit_pr(owner, r, number, state="closed")
    err.print(f"[red]✓[/red] Closed pull request {owner}/{r}#{number} ({data.get('title','')})")


@pr.command("reopen")
def pr_reopen(number: int, repo_: str = repo_opt()):
    owner, r = split_repo(repo_)
    data = client().edit_pr(owner, r, number, state="open")
    err.print(f"[green]✓[/green] Reopened pull request {owner}/{r}#{number} ({data.get('title','')})")


@pr.command("review")
def pr_review(number: int, repo_: str = repo_opt(),
              approve: bool = typer.Option(False, "--approve", "-a"),
              request_changes: bool = typer.Option(False, "--request-changes", "-r"),
              comment: bool = typer.Option(False, "--comment", "-c"),
              body: str = typer.Option("", "--body", "-b")):
    owner, r = split_repo(repo_)
    event = ("APPROVE" if approve else "REQUEST_CHANGES" if request_changes
             else "COMMENT" if comment else None)
    if event is None:
        err.print("[red]pick one of --approve/--request-changes/--comment[/red]")
        raise typer.Exit(2)
    client().create_review(owner, r, number, event=event, body=body)
    full = f"{owner}/{r}#{number}"
    if event == "APPROVE":
        err.print(f"[green]✓[/green] Approved pull request {full}")
    elif event == "REQUEST_CHANGES":
        err.print(f"[red]+[/red] Requested changes to pull request {full}")
    else:
        err.print(f"[dim]-[/dim] Reviewed pull request {full}")


# ================= label =================
@label.command("list")
def label_list(repo_: str = repo_opt(), json: str = typer.Option(None, "--json", help="Output JSON with the specified fields"), jq: str = typer.Option(None, "-q", "--jq", help="Query the output using a jq expression")):
    owner, r = split_repo(repo_)
    items = client().list_labels(owner, r)
    if json:
        return ghjson.export(items, ghjson.LABEL, json, jq)
    gh_table(["id", "name", "color", "description"],
             [[lb["id"], lb["name"], lb.get("color", ""), lb.get("description") or ""]
              for lb in items])


@label.command("create")
def label_create(repo_: str = repo_opt(), name: str = typer.Option(..., "--name", "-n"),
                 color: str = typer.Option("ededed", "--color", "-c"),
                 description: str = typer.Option("", "--description", "-d")):
    owner, r = split_repo(repo_)
    lb = client().create_label(owner, r, name=name, color="#" + color.lstrip("#"), description=description)
    console.print(f"[green]✓[/green] Label \"{lb['name']}\" created in {owner}/{r}")


@label.command("delete")
def label_delete(label_id: int, repo_: str = repo_opt()):
    owner, r = split_repo(repo_)
    c = client()
    name = next((lb["name"] for lb in c.list_labels(owner, r) if lb["id"] == label_id), str(label_id))
    c.delete_label(owner, r, label_id)
    console.print(f"[green]✓[/green] Label \"{name}\" deleted from {owner}/{r}")


# ================= milestone =================
@milestone.command("list")
def milestone_list(repo_: str = repo_opt(), state: str = "all",
                   json: str = typer.Option(None, "--json", help="Output JSON with the specified fields"), jq: str = typer.Option(None, "-q", "--jq", help="Query the output using a jq expression")):
    owner, r = split_repo(repo_)
    items = client().list_milestones(owner, r, state=state)
    if json:
        return out_json(items)
    gh_table(["id", "title", "state", "open/closed"],
             [[m["id"], m["title"], m["state"],
               f"{m.get('open_issues',0)}/{m.get('closed_issues',0)}"] for m in items])


@milestone.command("create")
def milestone_create(repo_: str = repo_opt(), title: str = typer.Option(..., "--title", "-t"),
                     description: str = typer.Option("", "--description", "-d")):
    owner, r = split_repo(repo_)
    m = client().create_milestone(owner, r, title=title, description=description)
    console.print(f"[green]✓[/green] created milestone '{m['title']}' (id {m['id']})")


@milestone.command("close")
def milestone_close(title: str = typer.Argument(..., help="milestone title"),
                    repo_: str = repo_opt()):
    """Close a milestone by title (gh milestone close)."""
    owner, r = split_repo(repo_)
    c = client()
    ms = {m["title"]: m["id"] for m in c.list_milestones(owner, r, state="all")}
    if title not in ms:
        err.print(f"[red]no milestone titled '{title}'[/red]")
        raise typer.Exit(1)
    c.edit_milestone(owner, r, ms[title], state="closed")
    console.print(f"[green]✓[/green] closed milestone '{title}'")


# ================= release =================
@release.command("create")
def release_create(tag: str = typer.Argument(..., help="tag name, e.g. v1.0"),
                   repo_: str = repo_opt(),
                   title: str = typer.Option(None, "--title", "-t"),
                   notes: str = typer.Option("", "--notes", "-n"),
                   target: str = typer.Option(None, "--target", help="branch/commit")):
    """Create a release (gh release create)."""
    owner, r = split_repo(repo_)
    rel = client().create_release(owner, r, tag_name=tag, name=title or tag, body=notes, target=target)
    console.print(gh_url(rel.get("html_url", "")))  # gh prints just the release URL to stdout


@release.command("list")
def release_list(repo_: str = repo_opt(), json: str = typer.Option(None, "--json", help="Output JSON with the specified fields"), jq: str = typer.Option(None, "-q", "--jq", help="Query the output using a jq expression")):
    owner, r = split_repo(repo_)
    items = client().list_releases(owner, r)
    if json:
        return ghjson.export(items, ghjson.RELEASE, json, jq)
    seen_latest = {"v": False}
    def rtype(rel):
        if rel.get("draft"):
            return "Draft"
        if rel.get("prerelease"):
            return "Pre-release"
        if not seen_latest["v"]:  # only the newest stable release is "Latest"
            seen_latest["v"] = True
            return "Latest"
        return ""
    rows = [(rel.get("name") or rel["tag_name"], rtype(rel), rel["tag_name"], rel.get("published_at", "")) for rel in items]
    gh_list("", ["TITLE", "TYPE", "TAG NAME", "PUBLISHED"],
            [[t, ty, tag, _fuzzy_ago(pub)] for t, ty, tag, pub in rows],
            [[t, ty, tag, pub] for t, ty, tag, pub in rows])


# ================= run / workflow (Actions) =================
# Forgejo's Actions REST surface can't serve GitHub-shaped runs/jobs/steps/logs
# (see ghclone/forge/actions_overlay.py). When a per-world seed exists for the
# repo we render `gh run`/`gh workflow`/`gh pr checks` from it, byte-for-byte like
# real gh; otherwise we fall back to the live forge for the few execution-driven
# commands (watch/download/dispatch).

_FAIL_CONCL = {"failure", "timed_out", "startup_failure", "action_required", "stale"}


def _overlay_for(owner: str, repo: str):
    """Return the seeded Actions overlay if it covers OWNER/REPO, else None."""
    ov = actions.ActionsOverlay.load()
    return ov if (ov and ov.has(owner, repo)) else None


def _render_run_view(run: dict, *, verbose: bool, job_filter: int | None) -> None:
    """Render `gh run view` exactly like real gh: header, JOBS (steps if -v or a
    single --job is selected), ANNOTATIONS, then the contextual footer."""
    # Plain builtin print() (not rich console) so output is byte-exact and never
    # soft-wrapped at the 80-col default when piped — gh keeps these on one line.
    jobs = run["jobs"]
    if job_filter is not None:
        jobs = [j for j in jobs if str(j["id"]) == str(job_filter)]
    print("")
    if job_filter is not None and jobs:
        job = jobs[0]
        print(f"{actions.status_icon(job['status'], job['conclusion'])} {job['name']} · {run['id']}")
    else:
        print(f"{actions.status_icon(run['status'], run['conclusion'])} {run['name']} · {run['id']}")
    print(f"Triggered via {run['event']} {_fuzzy_ago(run.get('run_started_at') or run.get('created_at',''))}")

    if jobs:
        print("")
        print("JOBS")
        show_steps = verbose or job_filter is not None
        for job in jobs:
            dur = actions.job_duration(job)
            tail = f" in {dur}" if dur != "0s" else ""
            print(f"{actions.status_icon(job['status'], job['conclusion'])} {job['name']}{tail} (ID {job['id']})")
            if show_steps:
                for step in job["steps"]:
                    print(f"  {actions.status_icon(step['status'], step['conclusion'])} {step['name']}")

    annotations = run.get("annotations") or []
    if annotations:
        print("")
        print("ANNOTATIONS")
        for a in annotations:
            icon = "X" if (a.get("level", "failure") == "failure") else "!"
            print(f"{icon} {a.get('message','')}")
            loc = a.get("path", "")
            if loc:
                print(f"{a.get('job','')}: {loc}#{a.get('line', 1)}")
            print("")

    print("")
    failed = (run.get("conclusion") in _FAIL_CONCL)
    if job_filter is None:
        if failed:
            print(f"To see what failed, try: gh run view {run['id']} --log-failed")
        else:
            print("For more information about a job, try: gh run view --job=<job-id>")
    if run.get("url"):
        print(f"View this run on GitHub: {gh_url(run['url'])}")


def _render_run_log(run: dict, *, only_failed: bool, job_filter: int | None) -> None:
    """Emit `gh run view --log[-failed]`: one `jobName\\tstepName\\tlogline` per line."""
    for job in run["jobs"]:
        if job_filter is not None and str(job["id"]) != str(job_filter):
            continue
        for step in job["steps"]:
            if only_failed and step["conclusion"] != "failure":
                continue
            prefix = f"{job['name']}\t{step['name']}\t"
            for line in (step.get("log") or "").splitlines():
                print(f"{prefix}{line}")


@run.command("list")
def run_list(repo_: str = repo_opt(),
             limit: int = typer.Option(20, "-L", "--limit", help="Maximum number of runs to fetch"),
             json: str = typer.Option(None, "--json", help="Output JSON with the specified fields"),
             jq: str = typer.Option(None, "-q", "--jq", help="Query the output using a jq expression")):
    """List recent workflow runs (gh run list)."""
    owner, r = split_repo(repo_)
    ov = _overlay_for(owner, r)
    if ov is not None:
        items = ov.runs(owner, r)[:limit]
        if json:
            return ghjson.export(items, ghjson.RUN, json, jq)
        if not items:
            err.print("no runs found")
            return
        # gh: TTY → aligned STATUS/TITLE/WORKFLOW/BRANCH/EVENT/ID/ELAPSED/AGE with an
        # icon for STATUS; piped → TSV with status+conclusion split and an ISO age.
        if not sys.stdout.isatty():
            for x in items:
                started = x.get("run_started_at") or x.get("created_at", "")
                print("\t".join(str(c) for c in [
                    x["status"], x.get("conclusion") or "", x["display_title"], x["name"],
                    x["head_branch"], x["event"], x["id"], actions.run_duration(x), started]))
            return
        rows = [[actions.status_icon(x["status"], x["conclusion"]), x["display_title"], x["name"],
                 x["head_branch"], x["event"], str(x["id"]), actions.run_duration(x),
                 _fuzzy_ago(x.get("run_started_at") or x.get("created_at", ""))] for x in items]
        gh_table(["STATUS", "TITLE", "WORKFLOW", "BRANCH", "EVENT", "ID", "ELAPSED", "AGE"], rows)
        return

    items = client().list_runs(owner, r, limit=limit)
    if json:
        return ghjson.export(items, ghjson.RUN, json, jq)
    if not items:
        err.print("no runs found")  # gh's empty-state message
        return
    gh_table(["STATUS", "TITLE", "WORKFLOW", "BRANCH", "ID"],
             [[x.get("conclusion") or x.get("status", ""), x.get("display_title", x.get("name", "")),
               x.get("name", x.get("workflow_id", "")), x.get("head_branch", ""),
               x.get("id", "")] for x in items])


@run.command("view")
def run_view(run_arg: str = typer.Argument(None, help="run ID or number (default: latest)"),
             repo_: str = repo_opt(),
             verbose: bool = typer.Option(False, "-v", "--verbose", help="Show job steps"),
             log: bool = typer.Option(False, "--log", help="View full log for a run or job"),
             log_failed: bool = typer.Option(False, "--log-failed", help="View the log for any failed steps"),
             job: int = typer.Option(None, "-j", "--job", help="View a specific job ID from a run"),
             exit_status: bool = typer.Option(False, "--exit-status", help="Exit non-zero if the run failed"),
             attempt: int = typer.Option(None, "-a", "--attempt", help="The attempt number of the workflow run"),
             web: bool = typer.Option(False, "-w", "--web", help="Open run in the browser"),
             json: str = typer.Option(None, "--json", help="Output JSON with the specified fields"),
             jq: str = typer.Option(None, "-q", "--jq", help="Query the output using a jq expression")):
    """View a summary of a workflow run (gh run view)."""
    owner, r = split_repo(repo_)
    ov = _overlay_for(owner, r)
    if ov is not None:
        # --job alone, with no run id, still resolves through the run that owns it.
        run = ov.run(owner, r, run_arg) if run_arg else (
            next((x for x in ov.runs(owner, r) for j in x["jobs"] if str(j["id"]) == str(job)), None)
            if job is not None else ov.run(owner, r, None))
        if not run:
            err.print("no run found")
            raise typer.Exit(1)
        if json:
            return ghjson.export(run, ghjson.RUN, json, jq)
        if web:
            err.print(f"Opening {gh_url(run.get('url',''))} in your browser.")
            return
        if log or log_failed:
            _render_run_log(run, only_failed=log_failed, job_filter=job)
        else:
            _render_run_view(run, verbose=verbose, job_filter=job)
        if exit_status and run.get("conclusion") in _FAIL_CONCL:
            raise typer.Exit(1)
        return

    runs = client().list_runs(owner, r, limit=100)
    run = next((x for x in runs if str(x.get("run_number")) == str(run_arg)), None) if run_arg else (runs[0] if runs else None)
    if not run:
        err.print("[yellow]no such run[/yellow]")
        raise typer.Exit(1)
    if json:
        return ghjson.export(run, ghjson.RUN, json, jq)
    gh_view([
        ("title", run.get("name", "")),
        ("status", run.get("status", "")),
        ("conclusion", run.get("conclusion", "")),
        ("branch", run.get("head_branch", "")),
        ("number", str(run.get("run_number", run.get("id", "")))),
    ])


@run.command("watch")
def run_watch(run_arg: int = typer.Argument(None, help="run number (default: latest)"),
              repo_: str = repo_opt(),
              interval: int = typer.Option(5, "--interval", "-i"),
              timeout: int = typer.Option(600, "--timeout")):
    """Wait for a run to finish, then report (gh run watch)."""
    import time
    owner, r = split_repo(repo_)
    c = client()
    deadline = timeout
    term = {"success", "failure", "cancelled", "error", "skipped"}
    while deadline > 0:
        runs = c.list_runs(owner, r, limit=100)
        run = next((x for x in runs if str(x.get("run_number")) == str(run_arg)), None) if run_arg else (runs[0] if runs else None)
        st = (run or {}).get("status", "")
        if st in term:
            wf = (run or {}).get("name", "")
            rid = (run or {}).get("id", (run or {}).get("run_number", ""))
            concl = (run or {}).get("conclusion", st)
            icon = "[green]✓[/green]" if st == "success" else "[red]X[/red]"
            console.print(f"{icon} Run {wf} ({rid}) completed with '{concl}'")
            raise typer.Exit(0 if st == "success" else 1)
        time.sleep(interval)
        deadline -= interval
    err.print("[yellow]timed out waiting for run[/yellow]")
    raise typer.Exit(1)


@run.command("download")
def run_download(run_arg: int = typer.Argument(None, help="run number (default: latest)"),
                 repo_: str = repo_opt(),
                 name: str = typer.Option(None, "--name", "-n", help="only this artifact"),
                 dir_: str = typer.Option(".", "--dir", "-D", help="destination directory")):
    """Download a run's artifacts and extract them (gh run download)."""
    import io
    import pathlib
    import zipfile
    owner, r = split_repo(repo_)
    c = client()
    rn = c.resolve_run_number(owner, r, run_arg)
    arts = c.list_run_artifacts(owner, r, rn)
    if name:
        arts = [a for a in arts if a.get("name") == name]
    if not arts:
        err.print(f"[yellow]no artifacts for run {rn}[/yellow]")
        raise typer.Exit(1)
    for a in arts:
        data = c.download_artifact(owner, r, rn, a["name"])
        dest = pathlib.Path(dir_) / a["name"]
        dest.mkdir(parents=True, exist_ok=True)
        zipfile.ZipFile(io.BytesIO(data)).extractall(dest)
        # gh run download is silent on success


@run.command("artifacts", hidden=True)  # gh has no `run artifacts` — hidden from help
def run_artifacts(run_arg: int = typer.Argument(None), repo_: str = repo_opt(),
                  json: str = typer.Option(None, "--json", help="Output JSON with the specified fields"), jq: str = typer.Option(None, "-q", "--jq", help="Query the output using a jq expression")):
    """List a run's artifacts."""
    owner, r = split_repo(repo_)
    c = client()
    rn = c.resolve_run_number(owner, r, run_arg)
    arts = c.list_run_artifacts(owner, r, rn)
    if json:
        return out_json(arts)
    if not arts:
        console.print(f"[dim]no artifacts for run {rn}[/dim]")
        return
    gh_table(["name", "size", "status"],
             [[a.get("name", ""), a.get("size", ""), a.get("status", "")] for a in arts])


@workflow.command("list")
def workflow_list(repo_: str = repo_opt(),
                  limit: int = typer.Option(50, "-L", "--limit", help="Maximum number of workflows to fetch"),
                  json: str = typer.Option(None, "--json", help="Output JSON with the specified fields"),
                  jq: str = typer.Option(None, "-q", "--jq", help="Query the output using a jq expression")):
    """List workflow files (gh workflow list)."""
    owner, r = split_repo(repo_)
    ov = _overlay_for(owner, r)
    items = ov.workflows(owner, r)[:limit] if ov is not None else client().list_workflows(owner, r)
    if json:
        return ghjson.export(items, ghjson.WORKFLOW, json, jq)
    if not items:
        err.print("no workflows found")  # gh's empty-state message
        return
    gh_table(["NAME", "STATE", "ID"],
             [[w.get("name", w["path"]), w.get("state", "active"), w.get("id", "")] for w in items])


@workflow.command("view")
def workflow_view(selector: str = typer.Argument(None, help="workflow ID, name, or filename"),
                  repo_: str = repo_opt(),
                  yaml: bool = typer.Option(False, "-y", "--yaml", help="View the workflow yaml file"),
                  json: str = typer.Option(None, "--json", help="Output JSON with the specified fields"),
                  jq: str = typer.Option(None, "-q", "--jq", help="Query the output using a jq expression")):
    """View the summary of a workflow (gh workflow view)."""
    owner, r = split_repo(repo_)
    ov = _overlay_for(owner, r)
    if ov is None:
        err.print("no workflows found")
        raise typer.Exit(1)
    wfs = ov.workflows(owner, r)
    sel = str(selector) if selector is not None else None
    wf = next((w for w in wfs if sel in (str(w["id"]), w["name"], w["path"], Path(w["path"]).name)), None) if sel else (wfs[0] if wfs else None)
    if not wf:
        err.print("could not find any workflows named %s" % sel)
        raise typer.Exit(1)
    if json:
        return ghjson.export(wf, ghjson.WORKFLOW, json, jq)
    if yaml:
        body = wf.get("yaml") or ""
        if not body:
            err.print("no YAML seeded for this workflow")
            raise typer.Exit(1)
        print(body)
        return
    runs = [x for x in ov.runs(owner, r) if x["name"] == wf["name"]]
    print(f"{wf['name']} - {wf['path']}")
    print(f"ID: {wf['id']}")
    print("")
    print(f"Total runs {len(runs)}")
    if runs:
        print("Recent runs")
        rows = [[actions.status_icon(x["status"], x["conclusion"]), x["display_title"],
                 x["head_branch"], x["event"], str(x["id"])] for x in runs]
        widths = [max(len(r[i]) for r in rows) for i in range(5)]
        for r_ in rows:
            print("  ".join(r_[i].ljust(widths[i]) for i in range(5)).rstrip())
    print("")
    print(f"To see more runs for this workflow, try: gh run list --workflow {Path(wf['path']).name}")
    print(f"To see the YAML for this workflow, try: gh workflow view {wf['name']} --yaml")


@workflow.command("run")
def workflow_run(name: str, repo_: str = repo_opt(), ref: str = typer.Option("main", "--ref")):
    """Dispatch a workflow (gh workflow run). `name` is the workflow file name."""
    owner, r = split_repo(repo_)
    client().dispatch_workflow(owner, r, name, ref=ref)
    err.print(f"[green]✓[/green] Created workflow_dispatch event for {name} at {ref}")


# ================= api (escape hatch) =================
@app.command("api")
def api(endpoint: str = typer.Argument(..., help="REST path, e.g. repos/owner/repo"),
        method: str = typer.Option("GET", "-X", "--method"),
        field: list[str] = typer.Option(None, "-f", "--field", help="key=value (repeatable)"),
        jq: str = typer.Option(None, "-q", "--jq", help="Query response using a jq expression"),
        paginate: bool = typer.Option(False, "--paginate")):
    """Make an authenticated HTTP request to the API and print the response. GraphQL is not supported."""
    if endpoint.strip().lower() == "graphql":
        err.print("[red]GraphQL is not supported on this host.[/red] Use a REST path instead.")
        raise typer.Exit(2)
    c = client()
    body = None
    if field:
        body = {}
        for f in field:
            k, _, v = f.partition("=")
            body[k] = v
    if paginate and method.upper() == "GET":
        data = c.paginate(endpoint.lstrip("/"))
    else:
        data = c.raw_api(method.upper(), endpoint, json_body=body)
    if jq:
        return ghjson.print_jq(data, jq)
    out_json(data)


# Hydration/migration are operator-only — see ghclone/cli/admin.py (`ghc-hydrate`).


def _main():
    # Present exactly like real gh (a Go/cobra binary): gh-format help, version,
    # and cobra-phrased usage errors. ghfmt handles --help / no-args groups and
    # error reformatting so Click/Typer's native output never shows.
    argv = sys.argv[1:]
    if argv and argv[0] in ("--version",):
        print(f"gh version {GH_VERSION} ({GH_VERSION_DATE})")
        print(f"https://github.com/cli/cli/releases/tag/v{GH_VERSION}")
        return
    cli = typer.main.get_command(app)
    if ghfmt.try_help(cli, argv):
        return
    try:
        # standalone_mode=False makes Click RETURN a command's exit code (from
        # `typer.Exit(n)`) instead of calling sys.exit itself, so we must honor it
        # here — otherwise `gh pr checks` / `gh run view --exit-status` (and any
        # `raise typer.Exit(n)`) would always report success to the shell.
        rv = app(prog_name="gh", standalone_mode=False)
        if isinstance(rv, int) and rv != 0:
            sys.exit(rv)
    except _UsageError as e:
        ghfmt.print_usage_error(e)
        sys.exit(1)
    except _Abort:
        print("gh: operation cancelled", file=sys.stderr)
        sys.exit(1)
    except ForgejoError as e:
        # Match real gh's `gh: <message> (HTTP NNN)` to stderr, plain text — never
        # the upstream API URL/path, which would reveal the backend's shape.
        print(f"gh: {e.message} (HTTP {e.status})", file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        if isinstance(e, (SystemExit, KeyboardInterrupt)):
            raise
        print(f"gh: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _main()
