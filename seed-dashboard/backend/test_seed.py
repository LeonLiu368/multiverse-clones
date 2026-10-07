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
# Overlay tests need the published prod gateway image; opt in by pointing this at an overlay dir,
# e.g. experiments/slack-prod-overlay/tasks/arrival-time/environment/data/overlay
OVERLAY = os.environ.get("SLACK_OVERLAY_DIR", "")
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
def test_overlay_editor_add_remove_export():
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

    # deleting a base message is now allowed and recorded as a patch op (channels stay protected)
    base = client.get("/api/slack/messages", params={"container": "all-worldsdatatest", "limit": 1}).json()[0]
    assert base["origin"] == "base"
    assert client.post("/api/slack/overlay/message/remove",
                       json={"container_id": base["channel_id"], "ts": base["ts"]}).status_code == 200
    assert any(o["op"] == "delete" and o["entity"] == "message"
               for o in client.get("/api/slack/overlay/patch").json()["ops"])
    assert client.post("/api/slack/overlay/container/remove",
                       json={"container_id": "all-worldsdatatest"}).status_code == 400  # base channel

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


@pytest.mark.skipif(not have_clone, reason="needs clone checkout")
def test_slack_edit_delete_message_patch_roundtrip():
    import json
    import sys
    import tempfile

    client.post("/api/slack/load", json={"base_id": f"dir:{os.path.abspath(TINY)}"})
    msgs = client.get("/api/slack/messages", params={"container": "all-worldsdatatest", "limit": 10}).json()
    assert len(msgs) >= 2 and all(m["origin"] == "base" for m in msgs)
    edit_ts, del_ts = msgs[0]["ts"], msgs[1]["ts"]

    def op(name, payload):
        return client.post("/api/slack/overlay/op", json={"op": name, "payload": payload})

    assert op("edit_message", {"channel": "all-worldsdatatest", "ts": edit_ts, "text": "[redacted]"}).status_code == 200
    assert op("delete_message", {"channel": "all-worldsdatatest", "ts": del_ts}).status_code == 200

    after = client.get("/api/slack/messages", params={"container": "all-worldsdatatest", "limit": 10}).json()
    assert any(m["ts"] == edit_ts and m["edited"] and m["text"] == "[redacted]" for m in after)
    assert not any(m["ts"] == del_ts for m in after)

    patch = client.get("/api/slack/overlay/patch").json()
    assert {(o["op"], o["entity"]) for o in patch["ops"]} >= {("update", "message"), ("delete", "message")}

    # The multiverse abundant-slack-clone dropped import_export.apply_patch, so the patch op-list is
    # a seed-dashboard artifact; apply it onto a fresh clone-imported DB the way a task would
    # (update text / delete row) to prove the op-list round-trips.
    if CLONE not in sys.path:
        sys.path.insert(0, CLONE)
    from slackgw.store import Store  # type: ignore
    import import_export  # type: ignore

    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "slack.db")
        st = Store(db)
        import_export.import_export(st, os.path.abspath(TINY), None, None, None, overlay=False)
        st.commit()
        cid = st.channel_by_ref("all-worldsdatatest")["id"]
        for o in patch["ops"]:
            if o["entity"] != "message":
                continue
            if o["op"] == "update":
                st.conn.execute("UPDATE messages SET text=? WHERE channel_id=? AND ts=?",
                                (o["set"]["text"], cid, o["match"]["ts"]))
            elif o["op"] == "delete":
                st.conn.execute("DELETE FROM messages WHERE channel_id=? AND ts=?",
                                (cid, o["match"]["ts"]))
        st.commit()
        rows = st.history(cid, limit=10)
        texts = {m["ts"]: m["text"] for m in rows}
        assert texts.get(edit_ts) == "[redacted]" and del_ts not in texts


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


@pytest.mark.skipif(not have_clone, reason="needs SLACK_CLONE_BASE clone checkout")
def test_reply_count_derived_from_thread_children(tmp_path):
    """A parent message whose source omits reply_count is still shown as a thread: the adapter
    derives the count from the thread_ts children present in the corpus, and thread() returns the
    replies. (Scraped/adapted exports routinely carry replies without a parent reply_count.)"""
    import json

    exp = tmp_path / "export"
    (exp / "general").mkdir(parents=True)
    (exp / "channels.json").write_text(json.dumps(
        [{"id": "C1", "name": "general", "created": 1, "creator": "U1", "members": ["U1", "U2"]}]))
    (exp / "users.json").write_text(json.dumps([
        {"id": "U1", "name": "ada", "real_name": "Ada"},
        {"id": "U2", "name": "bo", "real_name": "Bo"},
    ]))
    # parent has NO reply_count; two replies point at it via thread_ts
    (exp / "general" / "2026-01-01.json").write_text(json.dumps([
        {"type": "message", "user": "U1", "text": "deploy is failing", "ts": "100.000100"},
        {"type": "message", "user": "U2", "text": "looking now", "ts": "100.000200",
         "thread_ts": "100.000100"},
        {"type": "message", "user": "U1", "text": "fixed it", "ts": "100.000300",
         "thread_ts": "100.000100"},
        {"type": "message", "user": "U2", "text": "unrelated later message", "ts": "200.000000"},
    ]))

    r = client.post("/api/slack/load", json={"base_id": f"dir:{exp}"})
    assert r.status_code == 200, r.text

    msgs = client.get("/api/slack/messages", params={"container": "general"}).json()
    # history excludes the replies (only the 2 top-level messages show)
    by_ts = {m["ts"]: m for m in msgs}
    assert set(by_ts) == {"100.000100", "200.000000"}
    # the parent's reply_count was derived from its two children
    assert by_ts["100.000100"]["reply_count"] == 2
    assert by_ts["200.000000"].get("reply_count", 0) == 0

    # thread() returns the parent + both replies, in order
    thread = client.get("/api/slack/thread",
                        params={"container": "general", "root_ts": "100.000100"}).json()
    assert [m["text"] for m in thread] == ["deploy is failing", "looking now", "fixed it"]
