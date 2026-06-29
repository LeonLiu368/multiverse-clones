"""CLI unit tests with a mocked client (no live forge). Covers argument shaping,
output, and exit codes for the agent-facing commands."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

import ghclone.cli.main as m

runner = CliRunner()


@pytest.fixture
def fake_client(monkeypatch):
    c = MagicMock()
    c.cfg.user = "me"
    monkeypatch.setattr(m, "client", lambda: c)
    return c


def test_repo_bad_slug_exits_2(fake_client):
    res = runner.invoke(m.app, ["issue", "list", "-R", "noslash"])
    assert res.exit_code == 2


def test_api_graphql_guard(fake_client):
    # the guard rejects graphql with exit code 2 (message goes to stderr)
    res = runner.invoke(m.app, ["api", "graphql"])
    assert res.exit_code == 2


def test_issue_list_renders(fake_client):
    fake_client.list_issues.return_value = [
        {"number": 1, "title": "bug", "state": "open", "labels": [{"name": "p1"}]},
    ]
    res = runner.invoke(m.app, ["issue", "list", "-R", "o/r"])
    assert res.exit_code == 0
    assert "bug" in res.stdout and "p1" in res.stdout
    fake_client.list_issues.assert_called_once()


def test_issue_create_passthrough(fake_client):
    fake_client.create_issue.return_value = {"number": 7, "html_url": "u"}
    res = runner.invoke(m.app, ["issue", "create", "-R", "o/r", "-t", "T", "-b", "B"])
    assert res.exit_code == 0 and res.stdout == "u\n"
    _, kw = fake_client.create_issue.call_args
    assert kw == {"title": "T", "body": "B"}


def test_issue_close(fake_client):
    res = runner.invoke(m.app, ["issue", "close", "3", "-R", "o/r"])
    assert res.exit_code == 0
    fake_client.edit_issue.assert_called_with("o", "r", 3, state="closed")


def test_pr_merge_method(fake_client):
    res = runner.invoke(m.app, ["pr", "merge", "4", "-R", "o/r", "--method", "rebase"])
    assert res.exit_code == 0
    fake_client.merge_pr.assert_called_with("o", "r", 4, method="rebase")


def test_pr_review_requires_a_mode(fake_client):
    res = runner.invoke(m.app, ["pr", "review", "1", "-R", "o/r"])
    assert res.exit_code == 2  # must pick approve/request-changes/comment


def test_pr_review_approve(fake_client):
    res = runner.invoke(m.app, ["pr", "review", "1", "-R", "o/r", "--approve", "-b", "ok"])
    assert res.exit_code == 0
    _, kw = fake_client.create_review.call_args
    assert kw["event"] == "APPROVE"


def test_label_create(fake_client):
    fake_client.create_label.return_value = {"name": "bug", "id": 2}
    res = runner.invoke(m.app, ["label", "create", "-R", "o/r", "-n", "bug", "-c", "d73a4a"])
    assert res.exit_code == 0
    _, kw = fake_client.create_label.call_args
    assert kw["name"] == "bug" and kw["color"] == "#d73a4a"


def test_issue_react(fake_client):
    res = runner.invoke(m.app, ["issue", "react", "1", "-R", "o/r", "-c", "rocket"])
    assert res.exit_code == 0
    fake_client.add_reaction.assert_called_with("o", "r", 1, "rocket")


def test_workflow_run_dispatch(fake_client):
    res = runner.invoke(m.app, ["workflow", "run", "ci.yml", "-R", "o/r", "--ref", "dev"])
    assert res.exit_code == 0
    fake_client.dispatch_workflow.assert_called_with("o", "r", "ci.yml", ref="dev")


def test_json_output(fake_client):
    fake_client.get_repo.return_value = {"full_name": "o/r", "private": False}
    res = runner.invoke(m.app, ["repo", "view", "o/r", "--json", "nameWithOwner,isPrivate"])
    assert res.exit_code == 0 and '"nameWithOwner"' in res.stdout
