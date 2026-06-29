"""Offline tests: config, CLI wiring, hydration planning/provenance, MCP tools.
Live integration (against a running Forgejo) lives in test_integration.py."""

from __future__ import annotations

from typer.testing import CliRunner

from ghclone import config
from ghclone.cli.main import app
from ghclone.cli.admin import app as admin_app
from ghclone.hydrate import apply as hap

runner = CliRunner()


def test_cli_help_lists_all_groups():
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    for group in ("auth", "repo", "issue", "pr", "api",
                  "label", "run", "workflow"):
        assert group in res.stdout
    assert "milestone" not in res.stdout


def test_agent_cli_has_no_operator_commands():
    """Hydration/migration must NOT be reachable from the agent-facing `ghc`."""
    res = runner.invoke(app, ["--help"])
    assert "hydrate" not in res.stdout
    # `gh repo migrate` must be gone too
    rres = runner.invoke(app, ["repo", "--help"])
    assert "migrate" not in rres.stdout


def test_operator_cli_has_hydration():
    res = runner.invoke(admin_app, ["--help"])
    assert res.exit_code == 0
    for cmd in ("migrate", "snapshot", "apply", "verify"):
        assert cmd in res.stdout


def test_pr_subcommands_present():
    res = runner.invoke(app, ["pr", "--help"])
    for cmd in ("create", "view", "diff", "checkout", "merge", "review", "close", "reopen"):
        assert cmd in res.stdout


def test_config_defaults(monkeypatch):
    monkeypatch.delenv("GHC_HOST", raising=False)
    monkeypatch.delenv("GHC_TOKEN", raising=False)
    cfg = config.resolve()
    assert cfg.host == config.DEFAULT_HOST
    assert cfg.api_base.endswith("/api/v1")


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("GHC_HOST", "http://forge.local:9000")
    monkeypatch.setenv("GHC_TOKEN", "tok123")
    cfg = config.resolve()
    assert cfg.host == "http://forge.local:9000"
    assert cfg.token == "tok123"


def test_api_graphql_guard():
    res = runner.invoke(app, ["api", "graphql"])
    assert res.exit_code == 2


def test_hydrate_apply_dry_run_plan(tmp_path):
    (tmp_path / "issues").mkdir()
    (tmp_path / "issues" / "000001.json").write_text("{}")
    res = hap.apply(str(tmp_path), "o/r", dry_run=True)
    assert res["dry_run"] is True
    assert any("create repo" in s for s in res["steps"])


def test_provenance_prefix():
    out = hap._provenance("hello", {"login": "alice"}, "2024-01-01")
    assert out.startswith("> _originally by @alice on 2024-01-01_")
    assert "hello" in out


def test_temporal_state_reconstruction():
    from ghclone.hydrate import temporal
    cutoff = temporal.parse_cutoff("2024-02-01T00:00:00Z")
    issue = {"title": "renamed bug", "state": "closed", "created_at": "2024-01-15T00:00:00Z"}
    timeline = [
        {"event": "labeled", "label": {"name": "bug"}, "created_at": "2024-01-16T00:00:00Z"},
        {"event": "closed", "created_at": "2024-03-01T00:00:00Z"},   # after cutoff
        {"event": "renamed", "rename": {"from": "early bug"}, "created_at": "2024-03-01T00:00:00Z"},
    ]
    s = temporal.state_at(issue, timeline, cutoff)
    assert s["state"] == "open"            # closed happened after cutoff
    assert s["title"] == "early bug"        # walked back the rename
    assert "bug" in s["labels"]             # labeled before cutoff
    assert temporal.included_at(issue, cutoff) is True
    late = {"created_at": "2024-05-01T00:00:00Z"}
    assert temporal.included_at(late, cutoff) is False


def test_mcp_tools_registered():
    from ghclone.mcp import server
    for tool in ("repo_create", "issue_create", "pr_merge", "api",
                 "label_create", "milestone_list", "issue_react",
                 "workflow_list", "run_list"):
        assert hasattr(server, tool)
    # operator tools must NOT be exposed to the agent via MCP
    for tool in ("repo_migrate", "hydrate_apply", "hydrate_verify"):
        assert not hasattr(server, tool)
