"""Hydration unit tests: temporal reconstruction edge cases, apply planning,
and verify count logic (no live forge / no GitHub)."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from ghclone.hydrate import apply as hap
from ghclone.hydrate import snapshot as hsnap
from ghclone.hydrate import temporal
from ghclone.hydrate import verify as hver


def test_get_retries_transient_disconnect():
    """_get() rides out 'Server disconnected' drops on long snapshots of big repos."""
    calls = {"n": 0}
    ok = httpx.Response(200, json={"ok": True})

    class C:
        def get(self, path, params=None):
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
            return ok

    r = hsnap._get(C(), "/repos/x/y", tries=6)
    assert r.status_code == 200 and calls["n"] == 3


def test_get_gives_up_after_tries():
    class C:
        def get(self, path, params=None):
            raise httpx.ReadError("boom")
    try:
        hsnap._get(C(), "/x", tries=2)
        assert False, "should have raised"
    except httpx.ReadError:
        pass

T0 = "2024-01-01T00:00:00Z"
CUT = temporal.parse_cutoff("2024-02-01T00:00:00Z")


def issue(**kw):
    base = {"title": "t", "state": "open", "created_at": T0}
    base.update(kw)
    return base


def test_included_at_boundary():
    assert temporal.included_at(issue(created_at="2024-02-01T00:00:00Z"), CUT) is True
    assert temporal.included_at(issue(created_at="2024-02-01T00:00:01Z"), CUT) is False


def test_closed_after_cutoff_is_open():
    tl = [{"event": "closed", "created_at": "2024-03-01T00:00:00Z"}]
    assert temporal.state_at(issue(state="closed"), tl, CUT)["state"] == "open"


def test_closed_before_cutoff_is_closed():
    tl = [{"event": "closed", "created_at": "2024-01-15T00:00:00Z"}]
    assert temporal.state_at(issue(state="open"), tl, CUT)["state"] == "closed"


def test_reopen_sequence():
    tl = [
        {"event": "closed", "created_at": "2024-01-10T00:00:00Z"},
        {"event": "reopened", "created_at": "2024-01-20T00:00:00Z"},
        {"event": "closed", "created_at": "2024-03-01T00:00:00Z"},  # after cut
    ]
    assert temporal.state_at(issue(), tl, CUT)["state"] == "open"


def test_label_add_remove():
    tl = [
        {"event": "labeled", "label": {"name": "bug"}, "created_at": "2024-01-05T00:00:00Z"},
        {"event": "labeled", "label": {"name": "p1"}, "created_at": "2024-01-06T00:00:00Z"},
        {"event": "unlabeled", "label": {"name": "bug"}, "created_at": "2024-01-07T00:00:00Z"},
        {"event": "labeled", "label": {"name": "late"}, "created_at": "2024-03-01T00:00:00Z"},  # after cut
    ]
    labels = temporal.state_at(issue(), tl, CUT)["labels"]
    assert labels == ["p1"]


def test_title_walks_back_renames():
    tl = [{"event": "renamed", "rename": {"from": "old title"}, "created_at": "2024-03-01T00:00:00Z"}]
    assert temporal.state_at(issue(title="new title"), tl, CUT)["title"] == "old title"


def test_pr_merged_event():
    tl = [{"event": "merged", "created_at": "2024-01-20T00:00:00Z"}]
    s = temporal.state_at(issue(), tl, CUT, is_pr=True)
    assert s["merged"] is True and s["state"] == "closed"


def test_apply_plan_mentions_as_of(tmp_path):
    (tmp_path / "issues").mkdir()
    plan = hap.plan_apply(str(tmp_path), "o/r", as_of="abc123")
    assert any("abc123" in s for s in plan)


def test_provenance_format():
    out = hap._provenance("body", {"login": "bob"}, "2024-01-01")
    assert out.startswith("> _originally by @bob on 2024-01-01_")


def test_verify_flags_drop(tmp_path):
    (tmp_path / "issues").mkdir()
    for n in (1, 2, 3):
        (tmp_path / "issues" / f"{n:06d}.json").write_text('{"issue":{"number":%d,"title":"t","state":"open"}}' % n)
    (tmp_path / "MANIFEST.json").write_text('{"source":"o/r"}')
    c = MagicMock()
    c.list_issues.return_value = [{"number": 1}]   # only 1 landed of 3 -> drop
    c.list_prs.return_value = []
    rep = hver.verify(str(tmp_path), "o/r", client=c, sample=3)
    assert rep["ok"] is False and rep["drops"]


def test_verify_ok_when_complete(tmp_path):
    (tmp_path / "issues").mkdir()
    (tmp_path / "issues" / "000001.json").write_text('{"issue":{"number":1,"title":"t","state":"open"}}')
    (tmp_path / "MANIFEST.json").write_text('{"source":"o/r"}')
    c = MagicMock()
    c.list_issues.side_effect = lambda *a, **k: [{"number": 1}]
    c.list_prs.return_value = []
    c.get_issue.return_value = {"number": 1, "title": "t", "state": "open"}
    rep = hver.verify(str(tmp_path), "o/r", client=c, sample=1)
    assert rep["ok"] is True


def test_bundle_create_relative_paths(tmp_path, monkeypatch):
    """Regression: `git -C <mirror> bundle create <path>` resolves <path> against the
    mirror, so a *relative* out path (callers like spoink use runs/<id>/...) must be
    absolutized or git writes inside _mirror.git and dies with exit 128."""
    import subprocess

    from ghclone.forge import gitutil

    src = tmp_path / "src"
    subprocess.run(["git", "init", "-q", str(src)], check=True)
    for k, v in (("user.email", "a@b"), ("user.name", "a")):
        subprocess.run(["git", "-C", str(src), "config", k, v], check=True)
    subprocess.run(["git", "-C", str(src), "commit", "-q", "--allow-empty", "-m", "one"], check=True)

    work = tmp_path / "runs" / "abc" / "snap"
    work.mkdir(parents=True)
    subprocess.run(["git", "clone", "-q", "--mirror", str(src), str(work / "_mirror.git")], check=True)

    # run from a different cwd, passing RELATIVE paths (the shape that used to crash)
    monkeypatch.chdir(tmp_path)
    gitutil.bundle_create("runs/abc/snap/_mirror.git", "runs/abc/snap/git.bundle")
    assert (work / "git.bundle").exists()
    # and NOT written inside the mirror
    assert not (work / "_mirror.git" / "runs").exists()
