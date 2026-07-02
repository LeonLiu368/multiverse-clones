"""Validation-gate tests — the quality bar for generated tasks (no network)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spoink.pipeline import validate as V  # noqa: E402


def _git(*a, cwd):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True)


def _repo_with_fix(tmp_path):
    """A repo with base (pre-fix) and head (the fix) commits; returns (dir, base_sha, head_sha)."""
    r = tmp_path / "repo"; r.mkdir()
    _git("init", "-q", cwd=r); _git("config", "user.email", "a@b", cwd=r); _git("config", "user.name", "a", cwd=r)
    (r / "app.py").write_text("x = 1\n")
    _git("add", "-A", cwd=r); _git("commit", "-qm", "base", cwd=r)
    base = _git("rev-parse", "HEAD", cwd=r).stdout.strip()
    (r / "app.py").write_text("x = 2  # THE FIX\n")
    _git("commit", "-aqm", "fix the bug", cwd=r)
    head = _git("rev-parse", "HEAD", cwd=r).stdout.strip()
    return r, base, head


def test_code_cut_catches_unsliced_fix(tmp_path):
    r, base, head = _repo_with_fix(tmp_path)
    full = tmp_path / "full.bundle"
    _git("bundle", "create", str(full), "--all", cwd=r)
    # the FULL bundle contains the fix -> must FAIL
    assert V.code_cut(str(full), head).status == "fail"
    # a bundle sliced to base excludes the fix -> must PASS
    _git("branch", "-f", "tip", base, cwd=r)
    sliced = tmp_path / "sliced.bundle"
    _git("bundle", "create", str(sliced), "tip", cwd=r)
    g = V.code_cut(str(sliced), head)
    assert g.status == "pass", g.detail


def test_surface_leakage_planted_vs_clean(tmp_path):
    res = {"pr": 468, "head_sha": "ca9687c10246aa"}
    clean = tmp_path / "clean"; clean.mkdir()
    (clean / "slack.json").write_text("prod is throwing 500s on api keys, investigating")
    assert V.surface_leakage([str(clean)], res, ["backend/models.py"], "fix db mappers").status == "pass"
    planted = tmp_path / "planted"; planted.mkdir()
    (planted / "slack.json").write_text("robin: fixed in #468, it was the mappers change")
    g = V.surface_leakage([str(planted)], res, ["backend/models.py"], "fix db mappers")
    assert g.status == "fail" and any("#468" in e for e in g.evidence)


def test_contract_lint_flags_missing_pieces(tmp_path):
    root = tmp_path / "task"; (root / "environment").mkdir(parents=True)
    (root / "tests").mkdir(); (root / "solution").mkdir()
    (root / "task.toml").write_text('name = "x"\n')                  # missing custom_docker_compose
    (root / "environment" / "docker-compose.yaml").write_text("services:\n  main:\n    image: x\n")  # no amd64/healthcheck
    (root / "tests" / "test.sh").write_text("echo hi\n")             # never writes reward.txt
    (root / "solution" / "solve.sh").write_text("echo fix\n")
    g = V.contract_lint(str(root))
    assert g.status == "fail"
    joined = " ".join(g.evidence)
    assert "custom_docker_compose" in joined and "linux/amd64" in joined and "reward.txt" in joined


def test_promote_compose_guards_without_docker(tmp_path):
    """compose-promote short-circuits without touching docker for unrunnable tasks."""
    from spoink.pipeline import promote as P
    t = tmp_path / "t"; (t / "environment").mkdir(parents=True)
    assert P.promote_compose(str(t))["status"] == "errored"                 # no compose
    (t / "environment" / "docker-compose.yaml").write_text("services:\n  slack:\n    image: x:TODO-bake\n")
    assert P.promote_compose(str(t))["status"] == "skipped"                 # placeholder image


def test_promote_guards_without_docker(tmp_path):
    """promote() short-circuits cleanly (no docker) for non-runnable tasks."""
    from spoink.pipeline import promote as P
    # missing manifest/bundle -> errored
    assert P.promote(str(tmp_path)).get("status") == "errored"
    # a module_check task (no F2P tests) -> skipped, never touches docker
    task = tmp_path / "t"; (task / "environment").mkdir(parents=True)
    (task / "environment" / "codebase.bundle").write_text("x")
    (task / ".promote.json").write_text('{"verifier":"module_check","f2p":[]}')
    assert P.promote(str(task)).get("status") == "skipped"


def test_queue_refresh_updates_anchor_keeps_triage(tmp_path):
    """Re-discovering refreshes stale fields (e.g. the fixed anchor T) but keeps attachments."""
    from spoink.pipeline import discover as D
    q = D.CandidateQueue(str(tmp_path / "cq.json"))

    def cand(t):
        return D.Candidate(id="github_revert-abc", feed="github_revert", t=t,
                           title="x", summary="s", required_data={"github": {}},
                           resolution={"repo": "o/r", "pr": 1})
    q.merge([cand("2026-01-01T10:08:00Z")])          # stale created_at anchor
    q.update("github_revert-abc", snapshots={"github": "run1"}, status="attached")
    q.merge([cand("2026-07-01T09:21:00Z")])          # re-discover with the corrected merge anchor
    c = q.get("github_revert-abc")
    assert c["t"] == "2026-07-01T09:21:00Z"           # anchor refreshed
    assert c["snapshots"] == {"github": "run1"} and c["status"] == "attached"   # triage preserved


def test_report_accepts_only_when_critical_gates_pass(tmp_path):
    # a report whose only failing gate is non-critical (verifier) is still accepted
    rep = V.Report(gates=[V.Gate("contract", "pass"), V.Gate("code_cut", "pass"),
                          V.Gate("surface_leakage", "pass"), V.Gate("verifier", "warn")])
    assert rep.accepted
    rep.gates[1] = V.Gate("code_cut", "fail")     # a critical failure
    assert not rep.accepted
