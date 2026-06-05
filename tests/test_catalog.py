import os
import tempfile

import pytest

from slackclone.api.app import create_app
from slackclone.seed import catalog

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACES = os.path.join(REPO_ROOT, "workspaces")

EXPECTED = {"acme-incident", "globex-staging", "hooli-decisions"}


def test_list_workspaces_finds_catalog():
    names = set(catalog.list_workspaces(WORKSPACES))
    assert EXPECTED <= names


def test_workspace_path_resolves_and_misses():
    assert catalog.workspace_path("acme-incident", WORKSPACES).endswith("acme-incident.json")
    assert catalog.workspace_path("does-not-exist", WORKSPACES) is None


def test_read_workspace_unknown_raises():
    with pytest.raises(KeyError):
        catalog.read_workspace("nope", WORKSPACES)


def test_catalog_root_env_override(monkeypatch):
    monkeypatch.setenv("SLACK_WORKSPACE_DIR", WORKSPACES)
    assert catalog.catalog_root() == WORKSPACES
    assert "acme-incident" in catalog.list_workspaces()


def test_load_named_hydrates_db(monkeypatch):
    monkeypatch.setenv("SLACK_WORKSPACE_DIR", WORKSPACES)
    db = tempfile.mktemp(suffix=".db")
    counts = catalog.load_named("acme-incident", db)
    assert counts == {"users": 4, "channels": 2, "messages": 6}
    client = create_app(db)
    from fastapi.testclient import TestClient

    c = TestClient(client)
    names = {ch["name"] for ch in c.post("/api/conversations.list").json()["channels"]}
    assert names == {"general", "incidents"}
