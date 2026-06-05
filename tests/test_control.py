import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from slackclone.api.app import create_app

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACES = os.path.join(REPO_ROOT, "workspaces")
TOKEN = "s3cret-control-token"


@pytest.fixture(autouse=True)
def _catalog_env(monkeypatch):
    monkeypatch.setenv("SLACK_WORKSPACE_DIR", WORKSPACES)


def _client(monkeypatch, *, token=None, workspace=None):
    if token is not None:
        monkeypatch.setenv("SLACK_CONTROL_TOKEN", token)
    else:
        monkeypatch.delenv("SLACK_CONTROL_TOKEN", raising=False)
    if workspace is not None:
        monkeypatch.setenv("SLACK_WORKSPACE", workspace)
    else:
        monkeypatch.delenv("SLACK_WORKSPACE", raising=False)
    db = tempfile.mktemp(suffix=".db")
    return TestClient(create_app(db))


def test_control_disabled_without_token(monkeypatch):
    c = _client(monkeypatch, token=None)
    assert c.post("/_control/seed", json={"workspace": "acme-incident"}).status_code == 404
    assert c.post("/_control/reset").status_code == 404
    assert c.get("/_control/status").status_code == 404


def test_control_wrong_token_is_404(monkeypatch):
    c = _client(monkeypatch, token=TOKEN)
    r = c.post("/_control/seed", headers={"X-Control-Token": "wrong"}, json={"workspace": "acme-incident"})
    assert r.status_code == 404


def test_control_seed_by_name(monkeypatch):
    c = _client(monkeypatch, token=TOKEN)
    h = {"X-Control-Token": TOKEN}
    # starts empty
    assert c.post("/api/conversations.list").json()["channels"] == []
    r = c.post("/_control/seed", headers=h, json={"workspace": "globex-staging"})
    assert r.status_code == 200 and r.json()["ok"]
    names = {ch["name"] for ch in c.post("/api/conversations.list").json()["channels"]}
    assert names == {"general", "infra", "ask-platform"}


def test_control_seed_inline(monkeypatch):
    c = _client(monkeypatch, token=TOKEN)
    h = {"X-Control-Token": TOKEN}
    seed = {
        "workspace": {"id": "T0X", "name": "X", "domain": "x"},
        "users": [{"id": "UONE", "name": "one"}],
        "channels": [{"id": "CONE", "name": "solo", "type": "public_channel", "members": ["UONE"]}],
        "messages": [{"channel": "CONE", "ts": "1700000000.000001", "user": "UONE", "text": "hi"}],
    }
    r = c.post("/_control/seed", headers=h, json={"seed": seed})
    assert r.status_code == 200
    names = {ch["name"] for ch in c.post("/api/conversations.list").json()["channels"]}
    assert names == {"solo"}


def test_control_seed_unknown_workspace_400(monkeypatch):
    c = _client(monkeypatch, token=TOKEN)
    r = c.post("/_control/seed", headers={"X-Control-Token": TOKEN}, json={"workspace": "nope"})
    assert r.status_code == 400


def test_control_reset_reloads_boot_workspace(monkeypatch):
    c = _client(monkeypatch, token=TOKEN, workspace="acme-incident")
    h = {"X-Control-Token": TOKEN}
    # reseed to something else, then reset should restore the boot workspace
    c.post("/_control/seed", headers=h, json={"workspace": "globex-staging"})
    r = c.post("/_control/reset", headers=h)
    assert r.status_code == 200 and r.json()["workspace"] == "acme-incident"
    names = {ch["name"] for ch in c.post("/api/conversations.list").json()["channels"]}
    assert names == {"general", "incidents"}


def test_control_status_lists_catalog(monkeypatch):
    c = _client(monkeypatch, token=TOKEN, workspace="acme-incident")
    r = c.get("/_control/status", headers={"X-Control-Token": TOKEN})
    body = r.json()
    assert body["workspace"] == "acme-incident"
    assert {"acme-incident", "globex-staging", "hooli-decisions"} <= set(body["available"])
