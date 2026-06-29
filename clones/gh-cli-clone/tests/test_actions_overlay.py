"""Unit tests for the seeded GitHub Actions overlay (ghclone/forge/actions_overlay.py).

These exercise the data layer in isolation — normalization, derivation, icons,
durations, run/check lookup — with no CLI, no Forgejo, and no seed file on disk.
"""

from __future__ import annotations

import json

from ghclone.forge import actions_overlay as ao
from ghclone.forge.actions_overlay import ActionsOverlay

# A minimal world: one CI workflow, one failing run whose `test` job fails on one
# step. Status/conclusion are intentionally OMITTED in places to test derivation.
SEED = {
    "repos": {
        "acme/payments": {
            "workflows": [{"id": 7, "name": "CI", "path": ".github/workflows/ci.yml"}],
            "runs": [
                {
                    "id": 9001, "number": 41, "workflow": "CI", "title": "older", "event": "push",
                    "status": "completed", "conclusion": "success", "branch": "main", "sha": "aaaaaaa",
                    "jobs": [{"id": 1, "name": "test", "conclusion": "success"}],
                },
                {
                    "id": 9002, "number": 42, "workflow": "CI", "title": "fix race", "event": "pull_request",
                    "branch": "fix/race", "sha": "bbbbbbbcccccccc",
                    "started_at": "2026-06-01T00:00:00Z", "updated_at": "2026-06-01T00:01:18Z",
                    "jobs": [
                        {"id": 10, "name": "build", "conclusion": "success",
                         "started_at": "2026-06-01T00:00:02Z", "completed_at": "2026-06-01T00:00:34Z"},
                        {"id": 11, "name": "test", "required": True,
                         "started_at": "2026-06-01T00:00:02Z", "completed_at": "2026-06-01T00:01:20Z",
                         "steps": [
                             {"name": "Set up job", "conclusion": "success"},
                             {"name": "Run tests", "conclusion": "failure", "log": "FAIL a\nFAIL b\n"},
                             {"name": "Coverage", "conclusion": "skipped"},
                         ]},
                    ],
                },
            ],
        }
    }
}


def overlay() -> ActionsOverlay:
    return ActionsOverlay(SEED)


def test_has_and_workflows_defaults():
    ov = overlay()
    assert ov.has("acme", "payments")
    assert not ov.has("acme", "other")
    wf = ov.workflows("acme", "payments")[0]
    assert wf == {"id": 7, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active"}


def test_runs_sorted_newest_first():
    ov = overlay()
    runs = ov.runs("acme", "payments")
    assert [r["run_number"] for r in runs] == [42, 41]


def test_run_lookup_by_number_id_and_latest():
    ov = overlay()
    assert ov.run("acme", "payments", 41)["id"] == 9001
    assert ov.run("acme", "payments", 9002)["run_number"] == 42  # by database id
    assert ov.run("acme", "payments", None)["run_number"] == 42  # latest
    assert ov.run("acme", "payments", 999) is None


def test_run_conclusion_derived_from_jobs_when_omitted():
    # run 42 omits status/conclusion; one job fails -> completed/failure.
    run = overlay().run("acme", "payments", 42)
    assert run["status"] == "completed"
    assert run["conclusion"] == "failure"


def test_job_conclusion_derived_from_steps_when_omitted():
    test_job = next(j for j in overlay().run("acme", "payments", 42)["jobs"] if j["name"] == "test")
    assert test_job["status"] == "completed"
    assert test_job["conclusion"] == "failure"  # a failing step
    assert [s["number"] for s in test_job["steps"]] == [1, 2, 3]  # auto-numbered


def test_icons_match_gh_symbols():
    assert ao._icon("completed", "success") == ao.ICON_SUCCESS == "✓"
    assert ao._icon("completed", "failure") == ao.ICON_FAILURE == "X"
    assert ao._icon("completed", "timed_out") == "X"
    assert ao._icon("completed", "cancelled") == ao.ICON_SKIPPED == "-"
    assert ao._icon("completed", "skipped") == "-"
    assert ao._icon("in_progress", None) == ao.ICON_PROGRESS == "*"
    assert ao._icon("queued", None) == "*"


def test_bucket_categories():
    assert ao._bucket("completed", "success") == "pass"
    assert ao._bucket("completed", "failure") == "fail"
    assert ao._bucket("completed", "cancelled") == "cancel"
    assert ao._bucket("completed", "skipped") == "skipping"
    assert ao._bucket("in_progress", None) == "pending"


def test_duration_go_shape():
    assert ao._duration("2026-06-01T00:00:00Z", "2026-06-01T00:00:32Z") == "32s"
    assert ao._duration("2026-06-01T00:00:00Z", "2026-06-01T00:01:18Z") == "1m18s"
    assert ao._duration("2026-06-01T00:00:00Z", "2026-06-01T01:02:03Z") == "1h2m3s"
    assert ao._duration(None, None) == "0s"


def test_checks_match_by_sha_prefix():
    checks = overlay().checks_for_ref("acme", "payments", sha="bbbbbbb")
    names = {c["name"]: c for c in checks}
    assert set(names) == {"build", "test"}
    assert names["build"]["bucket"] == "pass" and names["build"]["state"] == "SUCCESS"
    assert names["test"]["bucket"] == "fail" and names["test"]["required"] is True
    assert names["test"]["icon"] == "X"
    assert names["build"]["elapsed"] == "32s"


def test_checks_match_by_branch_then_fallback_latest():
    ov = overlay()
    assert ov.checks_for_ref("acme", "payments", branch="main")[0]["workflow"] == "CI"
    # No match -> falls back to the most recent run (number 42).
    fallback = ov.checks_for_ref("acme", "payments", branch="does-not-exist")
    assert {c["name"] for c in fallback} == {"build", "test"}


def test_load_from_env(tmp_path, monkeypatch):
    p = tmp_path / "seed.json"
    p.write_text(json.dumps(SEED), encoding="utf-8")
    monkeypatch.setenv("GH_ACTIONS_SEED", str(p))
    ov = ActionsOverlay.load()
    assert ov is not None and ov.has("acme", "payments")
    assert ov.source == str(p)


def test_load_returns_none_without_seed(monkeypatch):
    monkeypatch.delenv("GH_ACTIONS_SEED", raising=False)
    monkeypatch.delenv("GHC_ACTIONS_SEED", raising=False)
    monkeypatch.setattr(ActionsOverlay, "seed_path", classmethod(lambda cls: None))
    assert ActionsOverlay.load() is None
