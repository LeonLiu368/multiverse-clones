"""CLI e2e tests for the seeded Actions overlay — `gh run` / `gh workflow` /
`gh pr checks` rendered from a seed file, with NO Forgejo and NO live client.

The overlay is selected purely by GH_ACTIONS_SEED pointing at a seed file, so
these run fully offline and assert on gh's exact piped output shapes.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

import ghclone.cli.main as m

runner = CliRunner()

SEED = {
    "repos": {
        "acme/payments": {
            "workflows": [
                {"id": 7, "name": "CI", "path": ".github/workflows/ci.yml"},
                {"id": 8, "name": "Deploy", "path": ".github/workflows/deploy.yml"},
            ],
            "runs": [
                {
                    "id": 9002, "number": 42, "workflow": "CI", "title": "fix race",
                    "event": "pull_request", "branch": "fix/race", "sha": "bbbbbbbcccc",
                    "actor": "dev", "started_at": "2026-06-01T00:00:00Z",
                    "updated_at": "2026-06-01T00:01:18Z",
                    "url": "https://example.test/acme/payments/actions/runs/9002",
                    "annotations": [{"level": "failure", "message": "Process completed with exit code 1.",
                                     "job": "test", "path": ".github", "line": 1}],
                    "jobs": [
                        {"id": 10, "name": "build", "conclusion": "success",
                         "started_at": "2026-06-01T00:00:02Z", "completed_at": "2026-06-01T00:00:34Z",
                         "steps": [{"name": "Set up job", "conclusion": "success"}]},
                        {"id": 11, "name": "test", "required": True,
                         "started_at": "2026-06-01T00:00:02Z", "completed_at": "2026-06-01T00:01:20Z",
                         "steps": [
                             {"name": "Set up job", "conclusion": "success"},
                             {"name": "Run tests", "conclusion": "failure", "log": "FAIL test_a\nFAIL test_b\n"},
                         ]},
                    ],
                },
                {
                    "id": 9001, "number": 41, "workflow": "CI", "title": "green run",
                    "event": "push", "status": "completed", "conclusion": "success",
                    "branch": "main", "sha": "aaaaaaa",
                    "jobs": [{"id": 1, "name": "test", "conclusion": "success"}],
                },
            ],
        }
    }
}


@pytest.fixture
def seed(tmp_path, monkeypatch):
    p = tmp_path / "actions-seed.json"
    p.write_text(json.dumps(SEED), encoding="utf-8")
    monkeypatch.setenv("GH_ACTIONS_SEED", str(p))
    # Make sure any forge fallback would blow up loudly rather than pass silently.
    monkeypatch.setattr(m, "client", lambda: (_ for _ in ()).throw(AssertionError("forge should not be called")))
    return p


def test_run_list_piped_tsv(seed):
    res = runner.invoke(m.app, ["run", "list", "-R", "acme/payments"])
    assert res.exit_code == 0
    lines = res.stdout.strip().splitlines()
    # newest first; status+conclusion split; gh column order
    first = lines[0].split("\t")
    assert first[0] == "completed" and first[1] == "failure"
    assert first[2] == "fix race" and first[3] == "CI"
    assert first[4] == "fix/race" and first[5] == "pull_request" and first[6] == "9002"
    assert lines[1].split("\t")[6] == "9001"


def test_run_list_json_fields(seed):
    res = runner.invoke(m.app, ["run", "list", "-R", "acme/payments", "--json", "databaseId,conclusion,headBranch"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data[0] == {"databaseId": 9002, "conclusion": "failure", "headBranch": "fix/race"}


def test_run_view_summary_and_jobs(seed):
    res = runner.invoke(m.app, ["run", "view", "42", "-R", "acme/payments"])
    assert res.exit_code == 0
    out = res.stdout
    assert "X CI · 9002" in out
    assert "JOBS" in out
    assert "✓ build in 32s (ID 10)" in out
    assert "X test in 1m18s (ID 11)" in out
    assert "ANNOTATIONS" in out and "Process completed with exit code 1." in out
    assert "To see what failed, try: gh run view 9002 --log-failed" in out
    assert "View this run on GitHub: https://example.test/acme/payments/actions/runs/9002" in out


def test_run_view_verbose_shows_steps(seed):
    res = runner.invoke(m.app, ["run", "view", "42", "-R", "acme/payments", "-v"])
    assert res.exit_code == 0
    assert "  X Run tests" in res.stdout
    assert "  ✓ Set up job" in res.stdout


def test_run_view_log_failed_only_failed_steps(seed):
    res = runner.invoke(m.app, ["run", "view", "42", "-R", "acme/payments", "--log-failed"])
    assert res.exit_code == 0
    lines = res.stdout.strip().splitlines()
    assert lines == ["test\tRun tests\tFAIL test_a", "test\tRun tests\tFAIL test_b"]


def test_run_view_log_full_includes_passing(seed):
    res = runner.invoke(m.app, ["run", "view", "42", "-R", "acme/payments", "--log", "--job", "11"])
    assert res.exit_code == 0
    # job-scoped full log: the failing step's lines, prefixed jobName\tstepName
    assert "test\tRun tests\tFAIL test_a" in res.stdout


def test_run_view_exit_status(seed):
    assert runner.invoke(m.app, ["run", "view", "42", "-R", "acme/payments", "--exit-status"]).exit_code == 1
    assert runner.invoke(m.app, ["run", "view", "41", "-R", "acme/payments", "--exit-status"]).exit_code == 0


def test_run_view_json_jobs(seed):
    res = runner.invoke(m.app, ["run", "view", "42", "-R", "acme/payments", "--json", "databaseId,jobs"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["databaseId"] == 9002
    test_job = next(j for j in data["jobs"] if j["name"] == "test")
    assert test_job["conclusion"] == "failure"
    assert [s["name"] for s in test_job["steps"]] == ["Set up job", "Run tests"]


def test_pr_checks_by_branch_exit_and_rows(seed):
    res = runner.invoke(m.app, ["pr", "checks", "fix/race", "-R", "acme/payments"])
    assert res.exit_code == 1  # a failing check
    rows = [ln.split("\t") for ln in res.stdout.strip().splitlines()]
    by_name = {r[0]: r for r in rows}
    assert by_name["build"][1] == "pass"
    assert by_name["test"][1] == "fail"


def test_pr_checks_json_bucket(seed):
    res = runner.invoke(m.app, ["pr", "checks", "fix/race", "-R", "acme/payments",
                                "--json", "name,bucket,state"])
    assert res.exit_code == 0  # --json suppresses the failing exit code, like gh
    data = {d["name"]: d for d in json.loads(res.stdout)}
    assert data["test"] == {"name": "test", "bucket": "fail", "state": "FAILURE"}


def test_pr_checks_required_only(seed):
    res = runner.invoke(m.app, ["pr", "checks", "fix/race", "-R", "acme/payments", "--required"])
    rows = [ln.split("\t")[0] for ln in res.stdout.strip().splitlines()]
    assert rows == ["test"]  # only the required job


def test_workflow_list_and_view(seed):
    lst = runner.invoke(m.app, ["workflow", "list", "-R", "acme/payments"])
    assert lst.exit_code == 0
    assert "CI\tactive\t7" in lst.stdout

    view = runner.invoke(m.app, ["workflow", "view", "CI", "-R", "acme/payments"])
    assert view.exit_code == 0
    assert "CI - .github/workflows/ci.yml" in view.stdout
    assert "ID: 7" in view.stdout
    assert "Total runs 2" in view.stdout
    assert "gh run list --workflow ci.yml" in view.stdout
