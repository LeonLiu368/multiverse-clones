"""Round-trip proof for each no-admin real-data importer (source-pluggable seeding).

For EACH adapter we craft a small synthetic sample **in that exact real-source
format**, import it → normalize → load into a temp SQLite engine → boot the gateway
in-process → and assert the Discord API reads it back (guild, channels, message
history newest-first, messages/search). This proves every source converges on the
canonical seed seam and reuses the one load path. Plus an anonymize test asserting no
real user handle/id survives.

None of these sources needs server admin (no Manage Server, no bot install).
"""

from __future__ import annotations

import csv
import json
import os
import socket
import tempfile
import threading
import time

import httpx
import pytest
import uvicorn

from discordclone.api.app import create_app
from discordclone.seed import importers
from discordclone.seed.load import load_seed


# --------------------------------------------------------------- in-process gateway
def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Gateway:
    """A booted in-process gateway + a token-authed httpx client over HTTP."""

    def __init__(self, seed: dict) -> None:
        self.db = tempfile.mktemp(suffix=".db")
        load_seed(seed, self.db)
        self.port = _free_port()
        app = create_app(self.db)
        self._cfg = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="error")
        self._srv = uvicorn.Server(self._cfg)
        self._thread = threading.Thread(target=self._srv.run, daemon=True)
        self._thread.start()
        base = f"http://127.0.0.1:{self.port}"
        for _ in range(100):
            try:
                if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                    break
            except Exception:
                time.sleep(0.05)
        else:
            raise RuntimeError("gateway did not become healthy")
        self.client = httpx.Client(base_url=base, headers={"Authorization": "Bot t"})

    def close(self) -> None:
        self.client.close()
        self._srv.should_exit = True
        self._thread.join(timeout=5)


def _roundtrip_assertions(gw: Gateway, *, guild_name: str, channel_names: set[str],
                          search_token: str, search_channel: str | None = None):
    guilds = gw.client.get("/users/@me/guilds").json()
    assert any(g["name"] == guild_name for g in guilds), guilds
    gid = next(g["id"] for g in guilds if g["name"] == guild_name)

    channels = gw.client.get(f"/guilds/{gid}/channels").json()
    names = {c["name"] for c in channels}
    assert channel_names <= names, names

    # message history newest-first in the search channel (or the first channel)
    cid = None
    if search_channel:
        cid = next((c["id"] for c in channels if c["name"] == search_channel), None)
    cid = cid or channels[0]["id"]
    msgs = gw.client.get(f"/channels/{cid}/messages", params={"limit": 100}).json()
    assert msgs, "no messages read back"
    assert [m["id"] for m in msgs] == sorted((m["id"] for m in msgs), key=int, reverse=True)
    for m in msgs:  # real envelope fields
        assert {"id", "channel_id", "author", "content", "timestamp", "reactions", "type"} <= set(m)

    # search finds the buried token, each hit marked
    body = gw.client.get(f"/guilds/{gid}/messages/search", params={"content": search_token}).json()
    assert body["total_results"] >= 1
    assert all(hit[0].get("hit") is True for hit in body["messages"])
    return gid


# --------------------------------------------------------------- 1. Data Package
def _make_data_package(root: str) -> str:
    dp = os.path.join(root, "data_package")
    os.makedirs(os.path.join(dp, "account"))
    json.dump({"id": "111111111111111111", "username": "realuser", "global_name": "Real User"},
              open(os.path.join(dp, "account", "user.json"), "w"))
    for cid, cname in [("222222222222222221", "general"), ("222222222222222222", "random")]:
        cdir = os.path.join(dp, "messages", f"c{cid}")
        os.makedirs(cdir)
        json.dump({"id": cid, "type": 0, "guild": {"id": "200000000000000000", "name": "My Server"},
                   "name": cname}, open(os.path.join(cdir, "channel.json"), "w"))
        base = 300000000000000000 if cname == "general" else 400000000000000000
        with open(os.path.join(cdir, "messages.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["ID", "Timestamp", "Contents", "Attachments"])
            for i in range(3):
                text = "general DATAPKGNEEDLE here" if (cname == "general" and i == 1) else f"{cname} msg {i}"
                w.writerow([str(base + i), f"2023-05-0{i + 1}T10:00:00+00:00", text, ""])
    return dp


def test_data_package_roundtrip(tmp_path):
    seed = importers.from_data_package(_make_data_package(str(tmp_path)))
    assert seed["users"][0]["username"] == "realuser"  # single real author
    assert all(m["author_id"] == "111111111111111111" for m in seed["messages"])
    gw = Gateway(seed)
    try:
        _roundtrip_assertions(gw, guild_name="My Server",
                              channel_names={"general", "random"},
                              search_token="DATAPKGNEEDLE", search_channel="general")
    finally:
        gw.close()


# --------------------------------------------------------------- 2. Generic dataset
def _make_dataset(path: str) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["user", "text", "timestamp", "chan", "srv"])
        for r in [
            ("alice", "hello world", "2023-06-01T09:00:00Z", "general", "Data Guild"),
            ("bob", "DATASETNEEDLE buried", "2023-06-01T09:05:00Z", "general", "Data Guild"),
            ("alice", "reply", "2023-06-01T09:10:00Z", "random", "Data Guild"),
            ("carol", "third author", "2023-06-02T09:00:00Z", "general", "Data Guild"),
        ]:
            w.writerow(r)


def test_dataset_roundtrip(tmp_path):
    ds = str(tmp_path / "dataset.csv")
    _make_dataset(ds)
    seed = importers.from_dataset(ds, importers.parse_mapping(
        ["author=user", "content=text", "ts=timestamp", "channel=chan", "guild=srv"]))
    # multi-user: distinct authors -> distinct members/users
    assert {u["global_name"] for u in seed["users"]} == {"alice", "bob", "carol"}
    assert len(seed["members"]) == 3
    gw = Gateway(seed)
    try:
        gid = _roundtrip_assertions(gw, guild_name="Data Guild",
                                    channel_names={"general", "random"},
                                    search_token="DATASETNEEDLE", search_channel="general")
        # author filter works (a synthesized-but-stable user id)
        bob = next(u["id"] for u in seed["users"] if u["global_name"] == "bob")
        body = gw.client.get(f"/guilds/{gid}/messages/search",
                             params={"author_id": bob, "content": "DATASETNEEDLE"}).json()
        assert body["total_results"] == 1
    finally:
        gw.close()


def test_dataset_deterministic(tmp_path):
    ds = str(tmp_path / "d.csv")
    _make_dataset(ds)
    m = importers.parse_mapping(["author=user", "content=text", "ts=timestamp", "channel=chan", "guild=srv"])
    a = importers.from_dataset(ds, m)
    b = importers.from_dataset(ds, m)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# --------------------------------------------------------------- 3. DiscordChatExporter
def _make_dce(path: str) -> None:
    json.dump({
        "guild": {"id": "500000000000000000", "name": "DCE Guild"},
        "channel": {"id": "600000000000000000", "type": "GuildTextChat",
                    "name": "incidents", "topic": "postmortems"},
        "messages": [
            {"id": "700000000000000001", "timestamp": "2023-07-01T08:00:00+00:00",
             "content": "first message",
             "author": {"id": "800000000000000001", "name": "dave", "nickname": "Dave"},
             "reactions": [], "isPinned": False},
            {"id": "700000000000000002", "timestamp": "2023-07-01T08:05:00+00:00",
             "content": "DECISION set X=42 DCENEEDLE",
             "author": {"id": "800000000000000002", "name": "erin"},
             "reactions": [{"emoji": {"name": "✅"}, "count": 2,
                            "users": [{"id": "800000000000000001", "name": "dave"},
                                      {"id": "800000000000000002", "name": "erin"}]}],
             "isPinned": True},
        ],
    }, open(path, "w"))


def test_dce_roundtrip(tmp_path):
    dce = str(tmp_path / "dce.json")
    _make_dce(dce)
    seed = importers.from_dce(dce)
    assert len(seed["users"]) == 2 and len(seed["messages"]) == 2
    # reactions expanded to (emoji,user) rows
    pinned = next(m for m in seed["messages"] if m["pinned"])
    assert len(pinned["reactions"]) == 2
    gw = Gateway(seed)
    try:
        gid = _roundtrip_assertions(gw, guild_name="DCE Guild",
                                    channel_names={"incidents"}, search_token="DCENEEDLE")
        # pinned + reaction rollup read back through the API
        channels = gw.client.get(f"/guilds/{gid}/channels").json()
        cid = channels[0]["id"]
        pins = gw.client.get(f"/channels/{cid}/pins").json()
        assert len(pins) == 1 and "DCENEEDLE" in pins[0]["content"]
        assert pins[0]["reactions"][0]["count"] == 2
    finally:
        gw.close()


# --------------------------------------------------------------- anonymize
def test_anonymize_scrubs_user_pii(tmp_path):
    dce = str(tmp_path / "dce.json")
    _make_dce(dce)
    seed = importers.from_dce(dce)
    anon = importers.anonymize(seed)
    blob = json.dumps(anon)
    # no real user id or handle survives
    for pii in ("800000000000000001", "800000000000000002", "dave", "erin", "Dave"):
        assert pii not in blob, f"PII leaked: {pii}"
    # synthetic handles + structure preserved
    assert {u["username"] for u in anon["users"]} == {"user_0001", "user_0002"}
    assert len(anon["messages"]) == 2
    assert any("DCENEEDLE" in m["content"] for m in anon["messages"])  # content kept
    # reactions still present, remapped
    pinned = next(m for m in anon["messages"] if m["pinned"])
    assert len(pinned["reactions"]) == 2
    # anonymized corpus still boots + reads back
    gw = Gateway(anon)
    try:
        _roundtrip_assertions(gw, guild_name="DCE Guild",
                              channel_names={"incidents"}, search_token="DCENEEDLE")
    finally:
        gw.close()


def test_anonymize_deterministic(tmp_path):
    dce = str(tmp_path / "dce.json")
    _make_dce(dce)
    seed = importers.from_dce(dce)
    a = importers.anonymize(seed)
    b = importers.anonymize(seed)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_anonymize_strip_attachments(tmp_path):
    seed = {
        "bot_user_id": "1", "users": [{"id": "1", "username": "u", "global_name": "U"}],
        "guilds": [{"id": "10", "name": "G", "owner_id": "1"}],
        "channels": [{"id": "20", "type": 0, "guild_id": "10", "name": "c", "position": 0}],
        "members": [{"guild_id": "10", "user_id": "1", "roles": [], "joined_at": ""}],
        "messages": [{"id": "30", "channel_id": "20", "guild_id": "10", "author_id": "1",
                      "content": "see https://cdn.example.com/secret.png now",
                      "timestamp": "2023-01-01T00:00:00+00:00"}],
    }
    anon = importers.anonymize(seed, strip_attachments=True)
    assert "https://cdn.example.com" not in json.dumps(anon)
    assert "[link]" in anon["messages"][0]["content"]


# --------------------------------------------------------------- CLI entry
def test_build_corpus_cli_synthetic_still_works(tmp_path):
    from discordclone.seed.build_corpus import main

    out = str(tmp_path / "syn.db")
    rc = main(["--synthetic", "--out", out])
    assert rc == 0 and os.path.exists(out)


def test_build_corpus_cli_dataset(tmp_path):
    from discordclone.seed.build_corpus import main

    ds = str(tmp_path / "d.csv")
    _make_dataset(ds)
    out = str(tmp_path / "d.db")
    rc = main(["--from-dataset", ds, "--map", "author=user", "content=text",
               "ts=timestamp", "channel=chan", "guild=srv", "--out", out])
    assert rc == 0 and os.path.exists(out)


def test_build_corpus_requires_exactly_one_source(tmp_path):
    from discordclone.seed.build_corpus import main

    with pytest.raises(SystemExit):
        main(["--out", str(tmp_path / "x.db")])  # no source
