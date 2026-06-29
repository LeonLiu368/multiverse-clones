"""MCP server exposing gh-compatible repo/issue/PR operations as tools so an agent
can drive the forge offline without a shell. Mirrors the CLI; both call the same
ForgejoClient, so parity is structural.

Run:  ghc-mcp   (stdio transport)
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from ghclone import config
from ghclone.forge import ForgejoClient
from ghclone.forge import actions_overlay as actions

mcp = FastMCP("ghc")


def _c() -> ForgejoClient:
    return ForgejoClient(config.resolve())


def _s(repo: str) -> tuple[str, str]:
    o, n = repo.split("/", 1)
    return o, n


def _ov(owner: str, repo: str):
    """The seeded Actions overlay if it covers OWNER/REPO, else None (mirrors the CLI)."""
    ov = actions.ActionsOverlay.load()
    return ov if (ov and ov.has(owner, repo)) else None


# ---- repos ----
@mcp.tool()
def repo_list(owner: str | None = None, limit: int = 30) -> list[dict]:
    """List repositories (optionally for a given owner/org)."""
    return _c().list_repos(owner=owner, limit=limit)


@mcp.tool()
def repo_view(repo: str) -> dict:
    """View a repository (OWNER/REPO)."""
    return _c().get_repo(*_s(repo))


@mcp.tool()
def repo_create(name: str, private: bool = False, description: str = "", org: str | None = None) -> dict:
    """Create a repository under the user (or org)."""
    return _c().create_repo(name=name, private=private, description=description, owner=org)


@mcp.tool()
def repo_edit(repo: str, description: str | None = None, private: bool | None = None,
              topics: list[str] | None = None) -> str:
    """Edit a repo's description/visibility/topics."""
    c = _c(); o, n = _s(repo)
    fields = {k: v for k, v in (("description", description), ("private", private)) if v is not None}
    if fields:
        c.edit_repo(o, n, **fields)
    if topics is not None:
        c.set_topics(o, n, topics)
    return f"updated {repo}"


# ---- issues ----
@mcp.tool()
def issue_list(repo: str, state: str = "open", label: str | None = None, limit: int = 30) -> list[dict]:
    """List issues for OWNER/REPO (state: open|closed|all)."""
    return _c().list_issues(*_s(repo), state=state, labels=label, limit=limit)


@mcp.tool()
def issue_view(repo: str, number: int) -> dict:
    """View issue #number on OWNER/REPO."""
    return _c().get_issue(*_s(repo), number)


@mcp.tool()
def issue_create(repo: str, title: str, body: str = "") -> dict:
    """Open an issue on OWNER/REPO."""
    return _c().create_issue(*_s(repo), title=title, body=body)


@mcp.tool()
def issue_comment(repo: str, number: int, body: str) -> dict:
    """Comment on issue/PR #number in OWNER/REPO."""
    return _c().comment(*_s(repo), number, body)


@mcp.tool()
def issue_set_state(repo: str, number: int, state: str) -> dict:
    """Close or reopen an issue (state: open|closed)."""
    return _c().edit_issue(*_s(repo), number, state=state)


# ---- pull requests ----
@mcp.tool()
def pr_list(repo: str, state: str = "open", limit: int = 30) -> list[dict]:
    """List pull requests for OWNER/REPO."""
    return _c().list_prs(*_s(repo), state=state, limit=limit)


@mcp.tool()
def pr_view(repo: str, number: int) -> dict:
    """View PR #number on OWNER/REPO."""
    return _c().get_pr(*_s(repo), number)


@mcp.tool()
def pr_diff(repo: str, number: int) -> str:
    """Unified diff for PR #number."""
    return _c().pr_diff(*_s(repo), number)


@mcp.tool()
def pr_create(repo: str, title: str, head: str, base: str = "main", body: str = "") -> dict:
    """Open a pull request on OWNER/REPO from head into base."""
    return _c().create_pr(*_s(repo), title=title, head=head, base=base, body=body)


@mcp.tool()
def pr_review(repo: str, number: int, event: str, body: str = "") -> dict:
    """Review PR #number (event: APPROVE|REQUEST_CHANGES|COMMENT)."""
    return _c().create_review(*_s(repo), number, event=event, body=body)


@mcp.tool()
def pr_merge(repo: str, number: int, method: str = "merge") -> str:
    """Merge PR #number (method: merge|rebase|rebase-merge|squash)."""
    _c().merge_pr(*_s(repo), number, method=method)
    return f"merged #{number}"


# ---- labels / milestones / reactions (P1) ----
@mcp.tool()
def label_list(repo: str) -> list[dict]:
    """List labels for OWNER/REPO."""
    return _c().list_labels(*_s(repo))


@mcp.tool()
def label_create(repo: str, name: str, color: str = "ededed", description: str = "") -> dict:
    """Create a label."""
    return _c().create_label(*_s(repo), name=name, color="#" + color.lstrip("#"), description=description)


@mcp.tool()
def milestone_list(repo: str, state: str = "all") -> list[dict]:
    """List milestones for OWNER/REPO."""
    return _c().list_milestones(*_s(repo), state=state)


@mcp.tool()
def milestone_close(repo: str, title: str) -> str:
    """Close a milestone by title."""
    c = _c(); o, n = _s(repo)
    ms = {m["title"]: m["id"] for m in c.list_milestones(o, n, state="all")}
    c.edit_milestone(o, n, ms[title], state="closed")
    return f"closed milestone {title}"


@mcp.tool()
def issue_edit(repo: str, number: int, title: str | None = None, body: str | None = None,
               add_label: list[str] | None = None, milestone: str | None = None) -> str:
    """Edit an issue: title/body, add labels (by name), assign a milestone (by title)."""
    c = _c(); o, n = _s(repo)
    fields = {k: v for k, v in (("title", title), ("body", body)) if v is not None}
    if milestone:
        ms = {m["title"]: m["id"] for m in c.list_milestones(o, n, state="all")}
        if milestone in ms:
            fields["milestone"] = ms[milestone]
    if fields:
        c.edit_issue(o, n, number, **fields)
    if add_label:
        ids = {lb["name"]: lb["id"] for lb in c.list_labels(o, n)}
        c.add_issue_labels(o, n, number, [ids[x] for x in add_label if x in ids])
    return f"edited #{number}"


@mcp.tool()
def release_create(repo: str, tag: str, title: str | None = None, notes: str = "") -> dict:
    """Create a release on OWNER/REPO."""
    c = _c(); o, n = _s(repo)
    return c.create_release(o, n, tag_name=tag, name=title or tag, body=notes)


@mcp.tool()
def issue_react(repo: str, number: int, content: str) -> dict:
    """React to issue/PR #number (content: +1,-1,laugh,hooray,confused,heart,rocket,eyes)."""
    return _c().add_reaction(*_s(repo), number, content)


# ---- Actions / Workflows (P1) ----
# When a per-world Actions seed covers the repo, these serve the same GitHub-shaped
# runs/jobs/steps/logs/check-runs the CLI renders (see ghclone/forge/actions_overlay.py);
# otherwise they fall back to the live forge.
@mcp.tool()
def workflow_list(repo: str) -> list[dict]:
    """List workflow files (.github/workflows)."""
    o, n = _s(repo)
    ov = _ov(o, n)
    return ov.workflows(o, n) if ov is not None else _c().list_workflows(o, n)


@mcp.tool()
def run_list(repo: str, limit: int = 20) -> list[dict]:
    """List Actions runs for OWNER/REPO (newest first)."""
    o, n = _s(repo)
    ov = _ov(o, n)
    return ov.runs(o, n)[:limit] if ov is not None else _c().list_runs(o, n, limit=limit)


@mcp.tool()
def run_view(repo: str, run: str | None = None) -> dict:
    """View one Actions run with its jobs and steps (run = run number or ID; default latest)."""
    o, n = _s(repo)
    ov = _ov(o, n)
    if ov is not None:
        found = ov.run(o, n, run)
        if not found:
            raise ValueError("no run found")
        return found
    runs = _c().list_runs(o, n, limit=100)
    found = next((x for x in runs if str(x.get("run_number")) == str(run)), None) if run else (runs[0] if runs else None)
    if not found:
        raise ValueError("no run found")
    return found


@mcp.tool()
def run_log(repo: str, run: str | None = None, only_failed: bool = False,
            job: int | None = None) -> str:
    """Full log for a run (gh run view --log[-failed]); one `job\\tstep\\tline` per line. Seed-backed."""
    o, n = _s(repo)
    ov = _ov(o, n)
    if ov is None:
        raise ValueError("no Actions seed for this repo")
    found = ov.run(o, n, run)
    if not found:
        raise ValueError("no run found")
    lines = []
    for j in found["jobs"]:
        if job is not None and str(j["id"]) != str(job):
            continue
        for step in j["steps"]:
            if only_failed and step["conclusion"] != "failure":
                continue
            for line in (step.get("log") or "").splitlines():
                lines.append(f"{j['name']}\t{step['name']}\t{line}")
    return "\n".join(lines)


@mcp.tool()
def pr_checks(repo: str, ref: str | None = None) -> list[dict]:
    """CI check runs for a PR's head (gh pr checks). `ref` = PR number or branch; default latest run. Seed-backed."""
    o, n = _s(repo)
    ov = _ov(o, n)
    if ov is None:
        raise ValueError("no Actions seed for this repo")
    branch = sha = None
    if ref and str(ref).isdigit():
        try:
            head = (_c().get_pr(o, n, int(ref)).get("head") or {})
            branch, sha = head.get("ref"), head.get("sha")
        except Exception:
            pass
    elif ref:
        branch = str(ref)
    return ov.checks_for_ref(o, n, branch=branch, sha=sha)


@mcp.tool()
def workflow_run(repo: str, name: str, ref: str = "main") -> str:
    """Dispatch a workflow file `name` on `ref`."""
    _c().dispatch_workflow(*_s(repo), name, ref=ref)
    return f"dispatched {name}"


@mcp.tool()
def run_artifacts(repo: str, run: int | None = None) -> list[dict]:
    """List a run's artifacts (run = run_number; default latest)."""
    c = _c(); o, n = _s(repo)
    return c.list_run_artifacts(o, n, c.resolve_run_number(o, n, run))


@mcp.tool()
def run_download(repo: str, run: int | None = None, name: str | None = None,
                 dir: str = ".") -> list[str]:
    """Download + extract a run's artifacts (gh run download). Returns extracted dirs."""
    import io
    import pathlib
    import zipfile
    c = _c(); o, n = _s(repo)
    rn = c.resolve_run_number(o, n, run)
    arts = c.list_run_artifacts(o, n, rn)
    if name:
        arts = [a for a in arts if a.get("name") == name]
    out = []
    for a in arts:
        data = c.download_artifact(o, n, rn, a["name"])
        dest = pathlib.Path(dir) / a["name"]
        dest.mkdir(parents=True, exist_ok=True)
        zipfile.ZipFile(io.BytesIO(data)).extractall(dest)
        out.append(str(dest))
    return out


# ---- api escape hatch ----
@mcp.tool()
def api(endpoint: str, method: str = "GET", fields: dict | None = None) -> object:
    """Authenticated REST API request. GraphQL is not supported."""
    if endpoint.strip().lower() == "graphql":
        raise ValueError("GraphQL is not supported on this host; use a REST path.")
    return _c().raw_api(method.upper(), endpoint, json_body=fields)


# NOTE: hydration/migration are operator-only and intentionally NOT exposed as
# agent MCP tools. The harness runs them via the `ghc-hydrate` CLI before handing
# the world to the agent.


def main():
    mcp.run()


if __name__ == "__main__":
    main()
