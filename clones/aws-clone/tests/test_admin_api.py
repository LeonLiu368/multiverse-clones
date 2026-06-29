from __future__ import annotations

import json

from aws_clone.admin.auth import check_admin_authorization
from aws_clone.admin.state_snapshot import mutation_log, state_snapshot
from aws_clone.seed.load_state import ensure_runtime_state
from tests.helpers import ADMIN_TOKEN, example_state_path


def test_clone_endpoints_are_hidden_when_admin_api_disabled(monkeypatch) -> None:
    monkeypatch.setenv("AWS_CLONE_ENABLE_ADMIN_API", "0")
    monkeypatch.setenv("AWS_CLONE_ADMIN_TOKEN", ADMIN_TOKEN)
    auth = check_admin_authorization(f"Bearer {ADMIN_TOKEN}")
    assert auth.ok is False
    assert auth.status == 404


def test_clone_endpoints_reject_agent_credentials(monkeypatch) -> None:
    monkeypatch.setenv("AWS_CLONE_ENABLE_ADMIN_API", "1")
    monkeypatch.setenv("AWS_CLONE_ADMIN_TOKEN", ADMIN_TOKEN)
    auth = check_admin_authorization("Bearer test")
    assert auth.ok is False
    assert auth.status == 403


def test_admin_token_is_required(monkeypatch) -> None:
    monkeypatch.setenv("AWS_CLONE_ENABLE_ADMIN_API", "1")
    monkeypatch.delenv("AWS_CLONE_ADMIN_TOKEN", raising=False)
    auth = check_admin_authorization("Bearer anything")
    assert auth.ok is False
    assert auth.status == 403


def test_admin_token_can_read_runtime_state(tmp_path, monkeypatch) -> None:
    runtime = tmp_path / "state.json"
    monkeypatch.setenv("AWS_CLONE_STATE_FILE", str(example_state_path()))
    monkeypatch.setenv("AWS_CLONE_RUNTIME_STATE_FILE", str(runtime))
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://127.0.0.1:1")
    ensure_runtime_state(example_state_path(), runtime)

    payload = state_snapshot()
    assert payload["meta"]["region"] == "us-east-1"
    assert payload["s3"]["buckets"][0]["name"] == "acme-payment-exports"
    assert "live_error" in payload["_clone"]
    assert mutation_log() == []
