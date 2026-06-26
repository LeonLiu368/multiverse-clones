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
    assert set(by_id) == {"slack", "linear", "logfire"}
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


def test_slice_guards(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert c.post("/api/slice", json={"run_id": "missing"}).status_code == 400
