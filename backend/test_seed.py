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


@pytest.mark.skipif(not have_clone, reason="needs clone checkout")
def test_overlay_editor_add_remove_export_and_base_protection():
    client.post("/api/slack/load", json={"base_id": f"dir:{os.path.abspath(TINY)}"})
    # add an overlay channel + message
    assert client.post("/api/slack/overlay/container/add", json={"name": "launch-room"}).status_code == 200
    m = client.post("/api/slack/overlay/message/add",
                    json={"container": "launch-room", "author": "robin.vega", "text": "ship at 6pm"})
    assert m.status_code == 200 and m.json()["origin"] == "overlay"
    # export reflects the edit, in write_export shape
    exp = client.get("/api/slack/overlay/export").json()
    assert exp["messages"] and exp["messages"][0]["content"] == "ship at 6pm"
    assert exp["messages"][0]["channel"] == "launch-room"

    # base data is protected: deleting a base message / base channel is refused
    base = client.get("/api/slack/messages", params={"container": "all-worldsdatatest", "limit": 1}).json()[0]
    assert base["origin"] == "base"
    r = client.post("/api/slack/overlay/message/remove",
                    json={"container_id": base["channel_id"], "ts": base["ts"]})
    assert r.status_code == 400 and "base data" in r.json()["detail"]
    assert client.post("/api/slack/overlay/container/remove",
                       json={"container_id": "all-worldsdatatest"}).status_code == 400

    # deleting the overlay message + channel works
    om = client.get("/api/slack/messages", params={"container": "launch-room"}).json()[0]
    assert client.post("/api/slack/overlay/message/remove",
                       json={"container_id": om["channel_id"], "ts": om["ts"]}).status_code == 200
    assert client.post("/api/slack/overlay/container/remove",
                       json={"container_id": "launch-room"}).status_code == 200
    assert not client.get("/api/slack/overlay/export").json()["messages"]


@pytest.mark.skipif(not have_clone, reason="needs clone checkout")
def test_overlay_export_zip_is_a_named_export_directory():
    import io
    import zipfile

    client.post("/api/slack/load", json={"base_id": f"dir:{os.path.abspath(TINY)}"})
    client.post("/api/slack/overlay/container/add", json={"name": "launch-room"})
    client.post("/api/slack/overlay/message/add",
                json={"container": "launch-room", "author": "robin.vega", "text": "ship at 6pm",
                      "timestamp": "2026-06-17T18:00:00"})
    r = client.get("/api/slack/overlay/export.zip", params={"name": "my overlay/.."})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    # name is sanitized (no spaces / path traversal) into the filename + the top-level dir
    assert 'filename="my_overlay.zip"' in r.headers["content-disposition"]
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert any(n.startswith("my_overlay/") and n.endswith("channels.json") for n in names)
    assert any("/launch-room/" in n for n in names)


@pytest.mark.skipif(not have_clone, reason="needs clone checkout")
def test_add_message_as_existing_user_reuses_their_id():
    client.post("/api/slack/load", json={"base_id": f"dir:{os.path.abspath(TINY)}"})
    before = client.get("/api/slack/entities").json()
    existing = before[0]  # tiny has one user
    m = client.post("/api/slack/overlay/message/add",
                    json={"container": "all-worldsdatatest", "author": existing["name"],
                          "text": "as an existing user"}).json()
    assert m["user"] == existing["id"]  # attributed to the existing user, not a fresh one
    after = client.get("/api/slack/entities").json()
    assert len(after) == len(before)  # no new user created


def test_editor_unsupported_on_echo_is_clean_400():
    client.post("/api/echo/load", json={"base_id": "fixture"})
    r = client.post("/api/echo/overlay/container/add", json={"name": "x"})
    assert r.status_code == 400 and "not support" in r.json()["detail"]


@pytest.mark.skipif(not (have_clone and have_overlay), reason="needs clone + arrival overlay")
def test_load_upload_reconstructs_overlay_from_files():
    # Mimic the browser folder picker: post each overlay file with a webkitRelativePath-style path.
    import glob as _glob

    files, paths = [], []
    for f in _glob.glob(os.path.join(OVERLAY, "**", "*.json"), recursive=True):
        rel = "overlay/" + os.path.relpath(f, OVERLAY)  # leading folder is stripped server-side
        paths.append(rel)
        files.append(("files", (os.path.basename(f), open(f, "rb"), "application/json")))
    r = client.post(
        "/api/slack/load_upload",
        data={"base_id": f"dir:{os.path.abspath(TINY)}", "paths": __import__("json").dumps(paths)},
        files=files,
    )
    assert r.status_code == 200, r.text
    assert r.json()["stats"].get("overlay", {}).get("messages") == 1
    msgs = client.get("/api/slack/messages", params={"container": "engineering"}).json()
    assert any(m["origin"] == "overlay" for m in msgs)


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
