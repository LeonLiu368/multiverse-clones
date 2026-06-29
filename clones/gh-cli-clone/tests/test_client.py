"""ForgejoClient unit tests against a mocked HTTP transport (no live forge).

Verifies request shaping (method/path/body/headers), response parsing, pagination,
error mapping, and Sudo impersonation — without touching a real Forgejo.
"""

from __future__ import annotations

import json

import httpx
import pytest

from ghclone.config import HostConfig
from ghclone.forge import ForgejoClient, ForgejoError


def make_client(handler, *, token="tok", sudo=None) -> ForgejoClient:
    cfg = HostConfig(host="http://forge.test", token=token, user="me")
    c = ForgejoClient(cfg, sudo=sudo)
    # swap in a mock transport while preserving base_url + headers
    c._http = httpx.Client(base_url=cfg.api_base, headers=dict(c._http.headers),
                           transport=httpx.MockTransport(handler))
    return c


def json_response(req, obj, status=200):
    return httpx.Response(status, json=obj)


# ---- low-level: auth header, error mapping, 204 ----
def test_auth_header_sent():
    seen = {}

    def h(req):
        seen["auth"] = req.headers.get("authorization")
        return json_response(req, {"login": "me"})

    make_client(h).whoami()
    assert seen["auth"] == "token tok"


def test_sudo_header():
    seen = {}

    def h(req):
        seen["sudo"] = req.headers.get("sudo")
        return json_response(req, {"login": "x"})

    make_client(h, sudo="alice").whoami()
    assert seen["sudo"] == "alice"


def test_error_maps_to_forgejoerror():
    def h(req):
        return httpx.Response(404, json={"message": "not found"})

    with pytest.raises(ForgejoError) as ei:
        make_client(h).get_repo("o", "r")
    assert ei.value.status == 404


def test_204_returns_none():
    def h(req):
        return httpx.Response(204)

    assert make_client(h).delete("/x") is None


# ---- pagination ----
def test_paginate_follows_pages():
    def h(req):
        page = int(req.url.params.get("page", "1"))
        # 50 items on page 1, 3 on page 2, stop
        if page == 1:
            return json_response(req, [{"i": n} for n in range(50)])
        if page == 2:
            return json_response(req, [{"i": n} for n in range(3)])
        return json_response(req, [])

    out = make_client(h).paginate("/items")
    assert len(out) == 53


# ---- repos ----
def test_create_repo_user_vs_org():
    calls = []

    def h(req):
        calls.append((req.method, req.url.path, json.loads(req.content or b"{}")))
        return json_response(req, {"full_name": "x/y", "html_url": "u"})

    c = make_client(h)
    c.create_repo(name="y")
    c.create_repo(name="y", owner="acme")
    assert calls[0][1] == "/api/v1/user/repos"
    assert calls[1][1] == "/api/v1/orgs/acme/repos"
    assert calls[0][2]["name"] == "y"


def test_migrate_repo_body():
    body = {}

    def h(req):
        body.update(json.loads(req.content))
        return json_response(req, {"full_name": "ghc-admin/r", "html_url": "u"})

    make_client(h).migrate_repo(clone_addr="https://github.com/o/r.git",
                                repo_owner="ghc-admin", repo_name="r", auth_token="pat")
    assert body["service"] == "github"
    assert body["issues"] and body["pull_requests"]
    assert body["auth_token"] == "pat"


# ---- issues ----
def test_list_issues_params():
    seen = {}

    def h(req):
        seen.update(dict(req.url.params))
        return json_response(req, [])

    make_client(h).list_issues("o", "r", state="closed", labels="bug", q="boom")
    assert seen["state"] == "closed" and seen["type"] == "issues"
    assert seen["labels"] == "bug" and seen["q"] == "boom"


def test_create_issue_body():
    body = {}

    def h(req):
        body.update(json.loads(req.content))
        return json_response(req, {"number": 5, "html_url": "u"})

    make_client(h).create_issue("o", "r", title="t", body="b", labels=[1], assignees=["a"])
    assert body == {"title": "t", "body": "b", "labels": [1], "assignees": ["a"]}


# ---- pull requests ----
def test_merge_pr_method():
    body = {}

    def h(req):
        body.update(json.loads(req.content))
        return httpx.Response(200)

    make_client(h).merge_pr("o", "r", 3, method="squash")
    assert body["Do"] == "squash"


def test_pr_diff_raw():
    def h(req):
        assert req.url.path.endswith("/pulls/2.diff")
        return httpx.Response(200, text="diff --git a/x b/x")

    assert "diff --git" in make_client(h).pr_diff("o", "r", 2)


def test_create_review_event():
    body = {}

    def h(req):
        body.update(json.loads(req.content))
        return json_response(req, {"id": 1})

    make_client(h).create_review("o", "r", 1, event="APPROVE", body="lgtm")
    assert body["event"] == "APPROVE"


# ---- labels / reactions / actions ----
def test_reaction_post():
    def h(req):
        assert req.url.path == "/api/v1/repos/o/r/issues/1/reactions"
        return json_response(req, {"content": "rocket"})

    make_client(h).add_reaction("o", "r", 1, "rocket")


def test_list_workflows_reads_contents():
    def h(req):
        if "/contents/.github/workflows" in req.url.path:
            return json_response(req, [{"type": "file", "name": "ci.yml", "path": ".github/workflows/ci.yml"}])
        return httpx.Response(404, json={"message": "no"})

    wfs = make_client(h).list_workflows("o", "r")
    assert wfs == [{"name": "ci.yml", "path": ".github/workflows/ci.yml"}]


def test_dispatch_workflow():
    body = {}

    def h(req):
        assert "/actions/workflows/ci.yml/dispatches" in req.url.path
        body.update(json.loads(req.content))
        return httpx.Response(204)

    make_client(h).dispatch_workflow("o", "r", "ci.yml", ref="dev")
    assert body["ref"] == "dev"


def test_run_artifacts_and_download():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("result.txt", "hello-artifact")
    zip_bytes = buf.getvalue()

    def h(req):
        p = req.url.path
        if p == "/api/v1/repos/o/r/actions/tasks":
            return json_response(req, {"workflow_runs": [{"id": 6, "run_number": 1, "status": "success"}]})
        if p == "/o/r/actions/runs/1/artifacts":
            return json_response(req, {"artifacts": [{"name": "my-artifact", "size": 15, "status": "completed"}]})
        if p == "/o/r/actions/runs/1/artifacts/my-artifact":
            return httpx.Response(200, content=zip_bytes, headers={"content-type": "application/zip"})
        return httpx.Response(404)

    c = make_client(h)
    assert c.resolve_run_number("o", "r") == 1
    arts = c.list_run_artifacts("o", "r", 1)
    assert arts[0]["name"] == "my-artifact"
    raw = c.download_artifact("o", "r", 1, "my-artifact")
    assert zipfile.ZipFile(io.BytesIO(raw)).read("result.txt") == b"hello-artifact"


def test_raw_api_normalizes_path():
    seen = {}

    def h(req):
        seen["path"] = req.url.path
        return json_response(req, {"ok": True})

    make_client(h).raw_api("GET", "repos/o/r")
    assert seen["path"] == "/api/v1/repos/o/r"
