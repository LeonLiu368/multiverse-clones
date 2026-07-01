from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("SPOINK_SKIP_DOTENV", "1")   # isolate from the real .env
    monkeypatch.setenv("SPOINK_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("SLACK_USER_TOKEN", "xoxp-test")
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)   # exercise the missing-key path
    monkeypatch.setenv("LOGFIRE_READ_TOKEN", "pylf_v1_test")
    # reimport so module-level JobStore picks up the tmp runs dir
    for m in list(sys.modules):
        if m.startswith("spoink.dashboard"):
            del sys.modules[m]
    server = importlib.import_module("spoink.dashboard.server")
    return TestClient(server.app)


def test_sources_reflect_env(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    body = c.get("/api/sources").json()
    by_id = {s["id"]: s for s in body["sources"]}
    assert set(by_id) == {"slack", "linear", "logfire", "github"}
    assert by_id["slack"]["has_key"] is True            # SLACK_USER_TOKEN set
    assert by_id["linear"]["has_key"] is False           # LINEAR_API_KEY unset
    assert by_id["logfire"]["has_key"] is True
    # capture/slice classification
    assert by_id["slack"]["can_slice"] and by_id["linear"]["can_slice"]
    assert by_id["logfire"]["can_slice"] is False        # captured as-of-T
    assert body["default_t"] == "2026-06-25T00:34:00Z"
    # the credential VALUE is never leaked, only presence
    assert "xoxp-test" not in c.get("/api/sources").text


def test_runs_empty_and_static(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert c.get("/api/runs").json() == {"runs": []}
    assert c.get("/").status_code == 200
    assert c.get("/static/app.js").status_code == 200
    assert c.get("/static/style.css").status_code == 200


def test_capture_guards(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert c.post("/api/capture", json={"source": "nope"}).status_code == 404
    # linear key is unset -> capture refused with a clear 400
    r = c.post("/api/capture", json={"source": "linear", "params": {}})
    assert r.status_code == 400 and "LINEAR_API_KEY" in r.json()["detail"]


def test_rename_delete_guards(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert c.post("/api/runs/missing/rename", json={"name": "x"}).status_code == 404
    assert c.delete("/api/runs/missing").status_code == 404
    assert c.get("/api/published").json() == {"published": []}


def test_github_org_is_suggestion_combo(tmp_path, monkeypatch):
    """The org field is a discover-backed combo (suggests your orgs, still free-text)."""
    _client(tmp_path, monkeypatch)
    from spoink.dashboard.sources import SOURCES
    org = next(p for p in SOURCES["github"].params if p.name == "org")
    assert org.kind == "combo" and org.discover == "orgs" and org.required


def test_task_creator_flow(tmp_path, monkeypatch):
    """Discover (mocked feed) -> queue -> guards -> the Tasks list starts empty."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    c = _client(tmp_path, monkeypatch)
    from spoink.pipeline import discover as disc

    # a fake feed so the test never hits the live GitHub API
    def _fake(token, org, **kw):
        return [disc.Candidate(
            id="github_revert-deadbeef00", feed="github_revert", t="2026-06-01T00:00:00Z",
            title="revert: broke widgets (acme/x#7)", summary="...",
            required_data={"github": {"org": "acme", "repos": ["x"], "as_of": "2026-06-01T00:00:00Z"}},
            resolution={"repo": "acme/x", "pr": 7, "base_sha": "b", "head_sha": "h", "has_tests": True},
            score=6, signals=["revert", "has_tests"])]
    monkeypatch.setitem(disc.FEEDS, "github_revert", _fake)

    r = c.post("/api/candidates/discover", json={"feed": "github_revert", "org": "acme"})
    assert r.status_code == 200 and r.json()["added"] == 1
    cid = r.json()["candidates"][0]["id"]
    assert c.get("/api/candidates").json()["candidates"][0]["title"].startswith("revert")

    # generate with nothing attached -> clear 400 (not a 500)
    assert c.post(f"/api/candidates/{cid}/generate").status_code == 400
    # attach a nonexistent run -> 400
    assert c.post(f"/api/candidates/{cid}/attach",
                  json={"snapshots": {"github": "nope"}}).status_code == 400
    assert c.get("/api/tasks").json() == {"tasks": []}
    assert c.delete(f"/api/candidates/{cid}").status_code == 200
    assert c.get("/api/candidates").json()["candidates"] == []


def test_ghc_hydrate_cmd_resolution(tmp_path, monkeypatch):
    """github capture resolves the snapshot CLI: explicit bin > PATH > importable package."""
    _client(tmp_path, monkeypatch)
    from spoink.dashboard import sources as S

    monkeypatch.setenv("GHC_HYDRATE_BIN", "/opt/ghc-hydrate")
    assert S._ghc_hydrate_cmd() == ["/opt/ghc-hydrate"]
    # a launcher with args is split
    monkeypatch.setenv("GHC_HYDRATE_BIN", "python -m ghclone.cli.admin")
    assert S._ghc_hydrate_cmd() == ["python", "-m", "ghclone.cli.admin"]
    # none available -> a clear, actionable CaptureError (not a stale message)
    monkeypatch.delenv("GHC_HYDRATE_BIN", raising=False)
    monkeypatch.setattr(S.shutil, "which", lambda _n: None)
    monkeypatch.setattr(S.importlib.util, "find_spec", lambda _n: None)
    with pytest.raises(S.CaptureError, match="gh-cli-clone not available"):
        S._ghc_hydrate_cmd()


def test_github_is_publishable_via_forge_bake(tmp_path, monkeypatch):
    """GitHub bakes a ghc-service Forgejo image (boot->hydrate->commit), forwarding as_of."""
    _client(tmp_path, monkeypatch)   # ensure modules import with the tmp env
    from spoink.dashboard import publish as pub
    from spoink.dashboard.sources import PUBLISHABLE

    assert "github" in PUBLISHABLE
    # image suggestion targets the forge service image, not a *-gateway
    assert pub.suggest_image("github", "june snap").startswith("ghcr.io/abundant-ai/ghc-service:")
    # bake drives build_forge.sh with the snapshots dir + the captured as_of (the real fix:
    # as_of must reach `apply --as-of`, not just sit in the manifest)
    cmd = pub._bake_cmd("github", "/runs/r1", "ghcr.io/abundant-ai/ghc-service:t",
                        {"as_of": "2026-06-25T00:34:00Z", "org": "acme"})
    assert cmd[0] == "bash" and cmd[1].endswith("gateway/build_forge.sh")
    assert cmd[2].endswith("/snapshots")
    assert "2026-06-25T00:34:00Z" in cmd
    assert Path(cmd[1]).exists()    # the bake script is shipped


def test_github_multi_repo_capture(tmp_path, monkeypatch):
    """The whole point: snapshot MANY repos in one run (loop over ghc-hydrate snapshot)."""
    import json as _json
    monkeypatch.setenv("SPOINK_SKIP_DOTENV", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    fake = tmp_path / "ghc"                       # stand in for ghc-hydrate snapshot
    fake.write_text("#!/usr/bin/env python3\n"
                    "import sys, os\n"
                    "a = sys.argv; out = a[a.index('--out') + 1]\n"
                    "os.makedirs(out, exist_ok=True)\n"
                    "open(os.path.join(out, 'repo.json'), 'w').write('{}')\n")
    fake.chmod(0o755)
    monkeypatch.setenv("GHC_HYDRATE_BIN", str(fake))
    for m in list(sys.modules):
        if m.startswith("spoink.dashboard"):
            del sys.modules[m]
    from spoink.dashboard import sources
    run = tmp_path / "run"; run.mkdir()
    rep = sources._capture_github(str(run), {"org": "acme", "repos": ["a", "b", "acme/c"]})
    assert rep["repos"] == 3 and rep["failed"] == 0
    man = _json.loads((run / "snapshots" / "manifest.json").read_text())
    assert man["org"] == "acme" and set(man["repos"]) == {"acme/a", "acme/b", "acme/c"}
    # each repo got its own snapshot dir
    assert (run / "snapshots" / "acme__a" / "repo.json").exists()
