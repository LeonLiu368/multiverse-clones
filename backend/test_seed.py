"""Backend tests. The merge-parity tests need the clone checkout (SLACK_CLONE_BASE) and the local
`slack-gateway:prod-v1` image; they skip gracefully if either is missing so CI on a bare box still
runs the adapter-contract + scalability checks."""
import os

import pytest
from fastapi.testclient import TestClient

import dockerutil
from clone_bridge import slack_clone_base
from app import app

CLONE = slack_clone_base()
TINY = os.path.join(CLONE, "..", "seeds", "tiny", "export")
OVERLAY = (
    "/Users/leonliu/projects/experiments-slack-mcp-oss/experiments/slack-prod-overlay/"
    "tasks/arrival-time/environment/data/overlay"
)
PROD_IMG = "ghcr.io/abundant-ai/slack-gateway:prod-v1"
SIDECAR_IMG = "ghcr.io/abundant-ai/slack-gateway:testing-smoke"

client = TestClient(app)
have_clone = os.path.isdir(CLONE)
have_overlay = os.path.isdir(OVERLAY)


def test_apps_registry_lists_slack_and_echo():
    apps = {a["id"]: a for a in client.get("/api/apps").json()}
    assert apps["slack"]["status"] == "active" and apps["slack"]["ui_module"] == "slack"
    assert "echo" in apps  # scalability: a second adapter shows up with no route changes


def test_echo_adapter_renders_through_generic_routes():
    # Proves the extension point: a non-Slack adapter answers the same normalized API.
    assert client.post("/api/echo/load", json={"base_id": "fixture"}).status_code == 200
    chans = client.get("/api/echo/containers").json()
    assert {c["name"] for c in chans} == {"general", "random"}
    msgs = client.get("/api/echo/messages", params={"container": "C1"}).json()
    assert msgs[0]["text"] == "hello from the echo clone"


def test_load_without_session_is_clean_400():
    r = client.get("/api/slack/containers")
    assert r.status_code == 400 and "session" in r.json()["detail"]


@pytest.mark.skipif(not (have_clone and have_overlay), reason="needs clone + arrival overlay")
def test_tiny_base_plus_overlay_merge_and_provenance():
    r = client.post("/api/slack/load", json={"base_id": f"dir:{os.path.abspath(TINY)}",
                                             "overlay_path": OVERLAY})
    assert r.status_code == 200, r.text
    chans = {c["name"]: c for c in client.get("/api/slack/containers").json()}
    # overlay introduced a brand-new #engineering channel (tiny base lacks it)
    assert chans["engineering"]["origin"] == "overlay"
    msgs = client.get("/api/slack/messages", params={"container": "engineering"}).json()
    planted = [m for m in msgs if "coming in at 6pm" in m["text"]]
    assert planted and planted[0]["origin"] == "overlay"
    # search finds the seeded message
    hits = client.get("/api/slack/search", params={"q": "payments hotfix"}).json()
    assert any(m["origin"] == "overlay" for m in hits)


@pytest.mark.skipif(
    not (have_clone and have_overlay and dockerutil.image_exists(PROD_IMG)),
    reason="needs clone + overlay + local prod-v1 image",
)
def test_prod_base_overlay_attaches_by_name_hash():
    r = client.post("/api/slack/load", json={"base_id": PROD_IMG, "overlay_path": OVERLAY})
    assert r.status_code == 200, r.text
    meta = client.get("/api/slack/meta").json()
    assert meta["stats"]["channels"] >= 80  # full prod corpus present
    eng = [c for c in client.get("/api/slack/containers").json() if c["name"] == "engineering"]
    assert eng, "prod corpus should already contain #engineering"
    # the prod channel is origin=base but carries overlay messages (attached by name->id hash)
    assert eng[0]["origin"] == "base" and eng[0]["has_overlay"] is True
    top = client.get("/api/slack/messages", params={"container": "engineering", "limit": 1}).json()
    assert top[0]["origin"] == "overlay"  # planted msg post-dates prod -> newest


@pytest.mark.skipif(
    not (have_clone and dockerutil.image_exists(SIDECAR_IMG)),
    reason="needs clone + local slack-gateway:testing-smoke sidecar image",
)
def test_gateway_sidecar_auto_merges_its_baked_overlay():
    # Loading a sidecar image with NO explicit overlay should still surface the task's seeded data,
    # because the image bakes its overlay at /data/slack-overlay (boot merges it; we mirror that).
    r = client.post("/api/slack/load", json={"base_id": SIDECAR_IMG})
    assert r.status_code == 200, r.text
    assert r.json()["stats"].get("overlay"), "baked overlay should have been detected + merged"
    hits = client.get("/api/slack/search", params={"q": "testing"}).json()
    assert any(m["origin"] == "overlay" for m in hits)
