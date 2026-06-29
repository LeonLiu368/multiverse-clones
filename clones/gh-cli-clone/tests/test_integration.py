"""Live integration tests against a running Forgejo.

Opt-in: skipped unless GHC_HOST + GHC_TOKEN are set (set them after
`docker compose up` + scripts/bootstrap.sh). Exercises the P0 loop end-to-end.
Each run uses a unique repo name derived from the worker pid to stay isolated.
"""

from __future__ import annotations

import base64
import os
import time

import pytest

from ghclone.forge import ForgejoError

from ghclone.config import resolve
from ghclone.forge import ForgejoClient

pytestmark = pytest.mark.skipif(
    not (os.getenv("GHC_HOST") and os.getenv("GHC_TOKEN")),
    reason="set GHC_HOST + GHC_TOKEN to run live integration tests",
)


@pytest.fixture
def client():
    return ForgejoClient(resolve())


@pytest.fixture
def repo(client):
    name = f"itest-{os.getpid()}"
    me = client.whoami()["login"]
    try:
        client.delete_repo(me, name)
    except Exception:
        pass
    client.create_repo(name=name, description="integration test")
    yield me, name
    try:
        client.delete_repo(me, name)
    except Exception:
        pass


def test_issue_lifecycle(client, repo):
    o, r = repo
    i = client.create_issue(o, r, title="bug", body="boom")
    assert i["number"] >= 1
    client.comment(o, r, i["number"], "looking into it")
    assert len(client.list_comments(o, r, i["number"])) == 1
    client.edit_issue(o, r, i["number"], state="closed")
    assert client.get_issue(o, r, i["number"])["state"] == "closed"


def test_p1_labels_milestones_reactions(client, repo):
    o, r = repo
    lb = client.create_label(o, r, name="p1", color="#00ff00", description="x")
    assert any(x["name"] == "p1" for x in client.list_labels(o, r))
    ms = client.create_milestone(o, r, title="m1")
    assert any(x["title"] == "m1" for x in client.list_milestones(o, r))
    i = client.create_issue(o, r, title="react me")
    client.add_reaction(o, r, i["number"], "rocket")
    client.delete_label(o, r, lb["id"])
    client.delete_milestone(o, r, ms["id"])


def test_p1_workflow_listing(client, repo):
    import base64
    o, r = repo
    wf = b"name: CI\non: [push]\njobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"
    client.put_file(o, r, ".forgejo/workflows/ci.yml",
                    content_b64=base64.b64encode(wf).decode(), message="wf", branch="main")
    wfs = client.list_workflows(o, r)
    assert any(w["name"] == "ci.yml" for w in wfs)


def test_pr_lifecycle(client, repo):
    o, r = repo
    client.create_branch(o, r, new_branch="feat", old_branch="main")
    client.put_file(o, r, "f.txt", content_b64=base64.b64encode(b"hi\n").decode(),
                    message="add f", branch="feat")
    p = client.create_pr(o, r, title="add f", head="feat", base="main")
    assert "diff --git" in client.pr_diff(o, r, p["number"])
    client.create_review(o, r, p["number"], event="APPROVE", body="lgtm")
    # Forgejo computes mergeability asynchronously; retry the merge briefly.
    for _ in range(10):
        try:
            client.merge_pr(o, r, p["number"], method="squash")
            break
        except ForgejoError as e:
            if e.status in (405, 409):
                time.sleep(1)
                continue
            raise
    assert client.get_pr(o, r, p["number"])["merged"] is True
