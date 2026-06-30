"""R6.2 — CLI <-> MCP parity.

For each CLI group, drive the agent's TWO surfaces against the same live forge and
assert they return the SAME underlying records:

  * the CLI  (`ghc … --json`, via Typer's CliRunner — the exact bytes an agent gets)
  * the MCP tool (`ghclone.mcp.server.<tool>(...)` — directly callable functions)

Both are thin clients of the one `ForgejoClient`, so parity is structural; this
test pins it. It is live (a real Forgejo round-trip) and is skipped unless
GHC_HOST + GHC_TOKEN are set — exactly like test_integration.py. Run it from a
cold `docker compose up` with those env vars pointing at the gateway.

Covered groups: repo, issue, pr, label, milestone, workflow/run, api. (≥1 row per
CLI group, per the audit action item.)
"""

from __future__ import annotations

import base64
import json
import os
import time

import pytest

from typer.testing import CliRunner

from ghclone.cli.main import app
from ghclone.config import resolve
from ghclone.forge import ForgejoClient, ForgejoError
from ghclone.mcp import server as mcp

pytestmark = pytest.mark.skipif(
    not (os.getenv("GHC_HOST") and os.getenv("GHC_TOKEN")),
    reason="set GHC_HOST + GHC_TOKEN to run live CLI<->MCP parity tests",
)

runner = CliRunner()


def _cli_json(*args: str):
    """Invoke `ghc … --json <fields>` and parse the JSON the agent would see."""
    res = runner.invoke(app, list(args))
    assert res.exit_code == 0, f"CLI {args} failed: {res.stdout}"
    return json.loads(res.stdout)


def _ids(records, key):
    """Stable identity set across both surfaces (ignores field-name casing)."""
    return {r[key] for r in records}


@pytest.fixture(scope="module")
def client():
    return ForgejoClient(resolve())


@pytest.fixture(scope="module")
def repo(client):
    """A freshly built repo with one issue, one label, one milestone and one PR,
    so every group has a record to compare. Torn down at the end."""
    me = client.whoami()["login"]
    name = f"paritytest-{os.getpid()}"
    try:
        client.delete_repo(me, name)
    except ForgejoError:
        pass
    client.create_repo(name=name, description="parity", auto_init=True)
    slug = f"{me}/{name}"

    client.create_issue(me, name, title="parity bug", body="boom")
    client.create_label(me, name, name="parity-label", color="#00ff00", description="x")
    client.create_milestone(me, name, title="parity-ms")

    # a PR so pr_list/pr_view have a record
    client.create_branch(me, name, new_branch="feat", old_branch="main")
    client.put_file(me, name, "f.txt", content_b64=base64.b64encode(b"hi\n").decode(),
                    message="add f", branch="feat")
    client.create_pr(me, name, title="parity pr", head="feat", base="main")

    yield me, name, slug
    try:
        client.delete_repo(me, name)
    except ForgejoError:
        pass


def test_parity_repo_view(repo):
    _, _, slug = repo
    cli = _cli_json("repo", "view", slug, "--json", "name,owner")
    tool = mcp.repo_view(slug)
    assert cli["name"] == tool["name"]
    assert cli["owner"]["login"] == tool["owner"]["login"]


def test_parity_issue_list(repo):
    _, _, slug = repo
    cli = _cli_json("issue", "list", "-R", slug, "--state", "all", "--json", "number,title")
    tool = mcp.issue_list(repo=slug, state="all")
    assert _ids(cli, "number") == _ids(tool, "number")
    assert _ids(cli, "title") == _ids(tool, "title")


def test_parity_pr_list(repo):
    _, _, slug = repo
    cli = _cli_json("pr", "list", "-R", slug, "--state", "all", "--json", "number,title")
    tool = mcp.pr_list(repo=slug, state="all")
    assert _ids(cli, "number") == _ids(tool, "number")


def test_parity_label_list(repo):
    _, _, slug = repo
    cli = _cli_json("label", "list", "-R", slug, "--json", "name")
    tool = mcp.label_list(repo=slug)
    assert _ids(cli, "name") == _ids(tool, "name")
    assert "parity-label" in _ids(tool, "name")


def test_parity_milestone_list(repo):
    _, _, slug = repo
    cli = _cli_json("milestone", "list", "-R", slug, "--json", "title")
    tool = mcp.milestone_list(repo=slug)
    assert _ids(cli, "title") == _ids(tool, "title")


def test_parity_workflow_list(repo, client):
    me, name, slug = repo
    wf = b"name: CI\non: [push]\njobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"
    client.put_file(me, name, ".forgejo/workflows/ci.yml",
                    content_b64=base64.b64encode(wf).decode(), message="wf", branch="main")
    for _ in range(10):
        if any(w["name"] == "ci.yml" for w in client.list_workflows(me, name)):
            break
        time.sleep(0.5)
    cli = _cli_json("workflow", "list", "-R", slug, "--json", "name")
    tool = mcp.workflow_list(repo=slug)
    assert _ids(cli, "name") == _ids(tool, "name")


def test_parity_api_escape_hatch(repo):
    """The raw `api` path is reachable from both surfaces and returns the same record."""
    _, _, slug = repo
    cli = _cli_json("api", f"repos/{slug}")
    tool = mcp.api(endpoint=f"repos/{slug}")
    assert cli["full_name"] == tool["full_name"]
