"""Archetype diversity + build harness + batch farm (no network)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spoink.pipeline import archetypes as A          # noqa: E402
from spoink.pipeline import discover as D            # noqa: E402
from spoink.pipeline import farm as F                # noqa: E402
from spoink.pipeline import harness                  # noqa: E402


def test_classify_routes_to_diverse_archetypes():
    cases = {
        ("github_revert", "fix: null deref in api_keys"): ("code_fix", "pytest_pr"),
        ("github_revert", "perf: cache the N+1 query"): ("optimization", "metric"),
        ("github_ci", "Modal Deploy red"): ("deployment", "build_check"),
        ("logfire_anomaly", "asyncpg InternalClientError"): ("incident_response", "readback"),
        ("linear_sev", "SEV1 prod outage"): ("incident_response", "readback"),
    }
    seen = set()
    for (feed, title), (name, vk) in cases.items():
        a = A.classify({"feed": feed, "title": title})
        assert a.name == name and a.verifier_kind == vk, (feed, title, a.name)
        seen.add(a.name)
    assert len(seen) == 4                              # genuine diversity, not one shape


def _bundle(tmp_path, files: dict) -> str:
    r = tmp_path / "repo"; r.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    for k, v in (("user.email", "a@b"), ("user.name", "a")):
        subprocess.run(["git", "-C", str(r), "config", k, v], check=True)
    for name, content in files.items():
        (r / name).parent.mkdir(parents=True, exist_ok=True)
        (r / name).write_text(content)
    subprocess.run(["git", "-C", str(r), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(r), "commit", "-qm", "x"], check=True)
    b = tmp_path / "code.bundle"
    subprocess.run(["git", "-C", str(r), "bundle", "create", str(b), "--all"], check=True)
    return str(b)


def test_harness_probe_detects_build_system(tmp_path):
    good = _bundle(tmp_path / "a", {"pyproject.toml": "[project]\nname='x'\n",
                                    "tests/test_x.py": "def test(): assert 1\n"})
    r = harness.probe_sut(good, changed_tests=["tests/test_x.py"], build=False)
    assert r["ok"] and r["build_system"] == "pip-e" and r["has_test_target"] is True
    plain = _bundle(tmp_path / "b", {"README.md": "hi\n"})
    assert harness.probe_sut(plain, build=False)["build_system"] == "unknown"


def test_farm_emits_ranked_diverse_bank(tmp_path, monkeypatch):
    """A github_revert feed with a bugfix + a perf PR farms into code_fix + optimization tasks."""
    def _fake(token, org, **kw):
        mk = lambda i, t: D.Candidate(id=f"c{i}", feed="github_revert", t="2026-06-01T00:00:00Z",
                                      title=t, summary="s", required_data={"github": {}},
                                      resolution={"repo": "o/r", "pr": i, "has_tests": i == 1})
        return [mk(1, "fix: crash on empty input"), mk(2, "perf: speed up the hot loop")]
    monkeypatch.setitem(D.FEEDS, "github_revert", _fake)

    m = F.farm("github_revert", "acme", token="t", limit=5, out_dir=str(tmp_path / "bank"))
    assert m["count"] == 2
    assert m["by_archetype"] == {"code_fix": 1, "optimization": 1}      # diversity in one feed
    assert (tmp_path / "bank" / "task-bank.json").exists()
    # ranked (bugfix-with-tests outranks the perf one lacking a shipped verifier)
    assert m["tasks"][0]["archetype"] == "code_fix" and m["tasks"][0]["has_own_verifier"]
