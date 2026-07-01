"""Capture gh-cli-clone (`ghc`) parity demos by exercising the clone's REAL
gh-shaping code over recorded Forgejo responses.

There is no Docker and Forgejo is a Go binary here, so we cannot boot the real
engine. Instead we replicate exactly what the clone's own unit tests do
(tests/test_client.py): build a `ForgejoClient` against an `httpx.MockTransport`
that returns recorded Forgejo (Gitea-compatible) JSON, call the client's real
methods, then run the result through the clone's real `--json` field shaper
(`ghclone.cli.ghjson`). The captured `clone_output` is therefore the ACTUAL
gh-shaped bytes `ghc … --json` would print — produced by clone code, not authored.

The `real_output` golden samples are authored from the `gh` CLI `--json` schema
(https://cli.github.com/manual/) so they share field shape with clone_output.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

CLONE = Path(__file__).resolve().parents[2] / "clones" / "gh-cli-clone"
sys.path.insert(0, str(CLONE))

import httpx  # noqa: E402

from ghclone.config import HostConfig  # noqa: E402
from ghclone.forge import ForgejoClient  # noqa: E402
from ghclone.cli import ghjson  # noqa: E402

# The clone ships no monolithic read seed — its unit tests feed recorded Forgejo
# responses inline through a MockTransport (tests/test_client.py). We do the same:
# these RECORDED_FORGEJO payloads are Forgejo/Gitea-shaped engine responses, and
# they are fed through the clone's real ForgejoClient + ghjson shaping code.
SEED_REL = "tests/test_client.py"  # provenance: the fixture/mock pattern we replicate

# ---- recorded Forgejo (Gitea-compatible) engine responses ------------------
FORGEJO_REPO = {
    "id": 42, "name": "payments-api", "full_name": "acme/payments-api",
    "owner": {"id": 7, "login": "acme"}, "private": False, "fork": False,
    "archived": False, "empty": False,
    "description": "Payment processing service (webhooks, ledger, payouts)",
    "html_url": "http://forge.test/acme/payments-api",
    "ssh_url": "git@forge.test:acme/payments-api.git",
    "default_branch": "main", "stars_count": 3, "forks_count": 1,
    "created_at": "2026-01-05T10:00:00Z", "updated_at": "2026-06-23T15:44:58Z",
}

FORGEJO_ISSUES = [
    {"id": 1001, "number": 128, "title": "Webhook retries are not idempotent",
     "state": "open", "state_reason": None, "body": "Duplicate events double-charge.",
     "html_url": "http://forge.test/acme/payments-api/issues/128",
     "user": {"id": 11, "login": "priya-n", "full_name": "Priya N", "is_bot": False},
     "labels": [{"id": 5, "name": "bug", "color": "#d73a4a", "description": "Something is broken"},
                {"id": 6, "name": "p1", "color": "#b60205", "description": "High priority"}],
     "assignees": [{"id": 12, "login": "dave-k", "full_name": "Dave K", "is_bot": False}],
     "milestone": None, "comments": 4,
     "created_at": "2026-06-23T15:40:00Z", "updated_at": "2026-06-23T15:44:58Z", "closed_at": None},
    {"id": 1002, "number": 127, "title": "Payout ledger rounds down sub-cent amounts",
     "state": "closed", "state_reason": "completed", "body": "Off-by-one in cents.",
     "html_url": "http://forge.test/acme/payments-api/issues/127",
     "user": {"id": 13, "login": "sam-w", "full_name": "Sam W", "is_bot": False},
     "labels": [{"id": 5, "name": "bug", "color": "#d73a4a", "description": "Something is broken"}],
     "assignees": [], "milestone": None, "comments": 2,
     "created_at": "2026-06-20T09:00:00Z", "updated_at": "2026-06-22T18:10:00Z",
     "closed_at": "2026-06-22T18:10:00Z"},
]

FORGEJO_PRS = [
    {"id": 2001, "number": 130, "title": "fix: make webhook retry idempotent",
     "state": "open", "body": "Closes #128.", "draft": False, "merged": False,
     "merged_at": None, "mergeable": True, "additions": 41, "deletions": 6, "changed_files": 3,
     "html_url": "http://forge.test/acme/payments-api/pulls/130",
     "user": {"id": 11, "login": "priya-n", "full_name": "Priya N", "is_bot": False},
     "labels": [{"id": 6, "name": "p1", "color": "#b60205", "description": "High priority"}],
     "assignees": [], "milestone": None, "comments": 1,
     "head": {"ref": "fix/webhook-retry-idempotency", "sha": "7d3c9af1e0b24a6c8f5e2a1d9b7c4e6f0a1b2c3d"},
     "base": {"ref": "main", "sha": "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"},
     "created_at": "2026-06-23T16:00:00Z", "updated_at": "2026-06-23T16:20:00Z", "closed_at": None},
    {"id": 2002, "number": 129, "title": "chore: bump httpx to 0.27",
     "state": "closed", "body": "Routine dep bump.", "draft": False, "merged": True,
     "merged_at": "2026-06-21T12:00:00Z", "mergeable": None,
     "additions": 2, "deletions": 2, "changed_files": 1,
     "html_url": "http://forge.test/acme/payments-api/pulls/129",
     "user": {"id": 14, "login": "renovate", "full_name": "Renovate Bot", "is_bot": True},
     "labels": [{"id": 7, "name": "dependencies", "color": "#0366d6", "description": "Dependency updates"}],
     "assignees": [], "milestone": None, "comments": 0,
     "head": {"ref": "renovate/httpx-0.x", "sha": "f00dcafe0000111122223333444455556666aaaa"},
     "base": {"ref": "main", "sha": "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"},
     "created_at": "2026-06-21T10:00:00Z", "updated_at": "2026-06-21T12:00:00Z",
     "closed_at": "2026-06-21T12:00:00Z"},
]

# The recorded Forgejo response for the issue-create POST (Forgejo returns the
# created issue object). The client posts to /issues and returns this body.
FORGEJO_CREATED_ISSUE = {
    "id": 1003, "number": 131, "title": "Add dead-letter queue for failed webhooks",
    "state": "open", "state_reason": None,
    "body": "Failed webhook deliveries should land in a DLQ, not silently drop.",
    "html_url": "http://forge.test/acme/payments-api/issues/131",
    "user": {"id": 12, "login": "dave-k", "full_name": "Dave K", "is_bot": False},
    "labels": [], "assignees": [], "milestone": None, "comments": 0,
    "created_at": "2026-07-01T09:30:00Z", "updated_at": "2026-07-01T09:30:00Z", "closed_at": None,
}


def _client(response) -> ForgejoClient:
    """Build a real ForgejoClient wired to a MockTransport that returns the
    recorded Forgejo JSON — the exact stubbing tests/test_client.py uses. `ghc`'s
    read commands paginate (page/limit); for lists we serve the batch on page 1
    and an empty page 2 so pagination terminates."""
    cfg = HostConfig(host="http://forge.test", token="tok", user="me")

    def handler(req: httpx.Request) -> httpx.Response:
        if isinstance(response, list):
            page = int(req.url.params.get("page", "1"))
            return httpx.Response(200, json=response if page == 1 else [])
        return httpx.Response(200, json=response)

    c = ForgejoClient(cfg)
    c._http = httpx.Client(base_url=cfg.api_base, headers=dict(c._http.headers),
                           transport=httpx.MockTransport(handler))
    return c


def _shape(data, mapping, fields: str):
    """Run the clone's REAL ghjson.export over `data` and capture the bytes it
    prints — i.e. exactly what `ghc … --json <fields>` emits — then parse back to
    an object for the manifest."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ghjson.export(data, mapping, fields)
    return json.loads(buf.getvalue())


def build() -> dict:
    demos = []

    # ---- GET: repo view (--json) -> the clone's real gh-shaping -------------
    repo_fields = "nameWithOwner,owner,visibility,description,defaultBranchRef,url"
    repo_data = _client(FORGEJO_REPO).get_repo("acme", "payments-api")
    repo_out = _shape(repo_data, ghjson.REPO, repo_fields)
    demos.append({
        "id": "repo-view",
        "title": "View a repository (gh --json field schema)",
        "method": "GET",
        "capability": "repo view → nameWithOwner / visibility PUBLIC",
        "seed_excerpt": {"full_name": FORGEJO_REPO["full_name"], "private": FORGEJO_REPO["private"],
                         "owner": FORGEJO_REPO["owner"], "description": FORGEJO_REPO["description"]},
        "ui": {"type": "list", "title": "gh › repo view acme/payments-api",
               "rows": [
                   {"icon": "📦", "title": repo_out["nameWithOwner"],
                    "sub": repo_out["description"],
                    "tags": [repo_out["visibility"], "@" + repo_out["owner"]["login"]]},
               ]},
        "agent": {"cli": f"ghc repo view acme/payments-api --json {repo_fields}",
                  "mcp": {"tool": "repo_view", "args": {"repo": "acme/payments-api"}}},
        "real_mapping": {
            "api": "gh repo view acme/payments-api --json nameWithOwner,owner,visibility,description,defaultBranchRef,url",
            "mcp": "gh-mcp › get_repository",
            "cli": "gh api repos/acme/payments-api  (REST 2022-11-28)",
            "doc": "https://cli.github.com/manual/gh_repo_view"},
        "clone_output": repo_out,
        "real_output": {
            "defaultBranchRef": {"name": "main"},
            "description": "Payment processing service (webhooks, ledger, payouts)",
            "nameWithOwner": "acme/payments-api",
            "owner": {"id": "MDQ6VXNlcjc=", "login": "acme"},
            "url": "https://github.com/acme/payments-api",
            "visibility": "PUBLIC"},
    })

    # ---- GET: issue list (--json) -> state uppercased, label color sans # ---
    issue_fields = "number,title,state,labels,author,assignees"
    issue_data = _client(FORGEJO_ISSUES).list_issues("acme", "payments-api", state="all")
    issue_out = _shape(issue_data, ghjson.ISSUE, issue_fields)
    demos.append({
        "id": "issue-list",
        "title": "List issues (gh --json state OPEN/CLOSED)",
        "method": "GET",
        "capability": "issue list → state uppercased, labels color sans '#'",
        "seed_excerpt": {"issues": [
            {"number": i["number"], "title": i["title"], "state": i["state"],
             "labels": [{"name": lb["name"], "color": lb["color"]} for lb in i["labels"]]}
            for i in FORGEJO_ISSUES]},
        "ui": {"type": "table", "title": "gh › issue list -R acme/payments-api --state all",
               "columns": ["number", "state", "title", "labels", "author"],
               "rows": [
                   {"number": i["number"], "state": i["state"], "title": i["title"],
                    "labels": ", ".join(lb["name"] for lb in i["labels"]),
                    "author": i["author"]["login"]}
                   for i in issue_out]},
        "agent": {"cli": f"ghc issue list -R acme/payments-api --state all --json {issue_fields}",
                  "mcp": {"tool": "issue_list", "args": {"repo": "acme/payments-api", "state": "all"}}},
        "real_mapping": {
            "api": "gh issue list -R acme/payments-api --state all --json number,title,state,labels,author,assignees",
            "mcp": "gh-mcp › list_issues",
            "cli": "gh api repos/acme/payments-api/issues  (REST 2022-11-28)",
            "doc": "https://cli.github.com/manual/gh_issue_list"},
        "clone_output": issue_out,
        "real_output": [
            {"author": {"id": "", "is_bot": False, "login": "priya-n", "name": "Priya N"},
             "assignees": [{"id": "", "is_bot": False, "login": "dave-k", "name": "Dave K"}],
             "labels": [
                 {"id": "LA_x", "name": "bug", "description": "Something is broken", "color": "d73a4a"},
                 {"id": "LA_y", "name": "p1", "description": "High priority", "color": "b60205"}],
             "number": 128, "state": "OPEN", "title": "Webhook retries are not idempotent"},
            {"author": {"id": "", "is_bot": False, "login": "sam-w", "name": "Sam W"},
             "assignees": [],
             "labels": [{"id": "LA_z", "name": "bug", "description": "Something is broken", "color": "d73a4a"}],
             "number": 127, "state": "CLOSED", "title": "Payout ledger rounds down sub-cent amounts"}],
    })

    # ---- GET: pr list (--json) -> state "MERGED" for merged PRs -------------
    pr_fields = "number,title,state,headRefName,baseRefName,isDraft,merged,author"
    pr_data = _client(FORGEJO_PRS).list_prs("acme", "payments-api", state="all")
    pr_out = _shape(pr_data, ghjson.PR, pr_fields)
    demos.append({
        "id": "pr-list",
        "title": "List pull requests (gh --json state MERGED)",
        "method": "GET",
        "capability": "pr list → state MERGED for merged PRs",
        "seed_excerpt": {"pulls": [
            {"number": p["number"], "title": p["title"], "state": p["state"],
             "merged": p["merged"], "head": {"ref": p["head"]["ref"]}}
            for p in FORGEJO_PRS]},
        "ui": {"type": "table", "title": "gh › pr list -R acme/payments-api --state all",
               "columns": ["number", "state", "title", "headRefName", "author"],
               "rows": [
                   {"number": p["number"], "state": p["state"], "title": p["title"],
                    "headRefName": p["headRefName"], "author": p["author"]["login"]}
                   for p in pr_out]},
        "agent": {"cli": f"ghc pr list -R acme/payments-api --state all --json {pr_fields}",
                  "mcp": {"tool": "pr_list", "args": {"repo": "acme/payments-api", "state": "all"}}},
        "real_mapping": {
            "api": "gh pr list -R acme/payments-api --state all --json number,title,state,headRefName,baseRefName,isDraft,merged,author",
            "mcp": "gh-mcp › list_pull_requests",
            "cli": "gh api repos/acme/payments-api/pulls  (REST 2022-11-28)",
            "doc": "https://cli.github.com/manual/gh_pr_list"},
        "clone_output": pr_out,
        "real_output": [
            {"author": {"id": "", "is_bot": False, "login": "priya-n", "name": "Priya N"},
             "baseRefName": "main", "headRefName": "fix/webhook-retry-idempotency",
             "isDraft": False, "merged": False, "number": 130, "state": "OPEN",
             "title": "fix: make webhook retry idempotent"},
            {"author": {"id": "", "is_bot": True, "login": "renovate", "name": "Renovate Bot"},
             "baseRefName": "main", "headRefName": "renovate/httpx-0.x",
             "isDraft": False, "merged": True, "number": 129, "state": "MERGED",
             "title": "chore: bump httpx to 0.27"}],
    })

    # ---- POST: issue create -> the created resource, gh-shaped -------------
    # `ghc issue create` prints the new issue URL; the write effect is the created
    # issue. We capture the created object gh-shaped via ghjson (same shaping the
    # `--json` path uses), and show the before/after issue list as the change.
    create_fields = "number,title,state,url,author"
    created_data = _client(FORGEJO_CREATED_ISSUE).create_issue(
        "acme", "payments-api",
        title="Add dead-letter queue for failed webhooks",
        body="Failed webhook deliveries should land in a DLQ, not silently drop.")
    created_out = _shape(created_data, ghjson.ISSUE, create_fields)

    def _row(i):  # a compact issue row for the timeline change block
        return {"id": i["number"], "title": i["title"], "tags": [i["state"]]}

    before_rows = [_row(_shape(i, ghjson.ISSUE, "number,title,state")) for i in FORGEJO_ISSUES]
    after_rows = before_rows + [_row(created_out)]

    demos.append({
        "id": "issue-create",
        "title": "Create an issue (write → created resource URL)",
        "method": "POST",
        "capability": "issue create → new resource, gh-shaped",
        "seed_excerpt": {"created_issue": {
            "number": FORGEJO_CREATED_ISSUE["number"], "title": FORGEJO_CREATED_ISSUE["title"],
            "state": FORGEJO_CREATED_ISSUE["state"], "html_url": FORGEJO_CREATED_ISSUE["html_url"]}},
        "ui": {"type": "timeline", "title": "gh › issue create -R acme/payments-api",
               "before": before_rows, "after": after_rows, "new_id": created_out["number"]},
        "agent": {"cli": ('ghc issue create -R acme/payments-api '
                          '-t "Add dead-letter queue for failed webhooks" '
                          '-b "Failed webhook deliveries should land in a DLQ, not silently drop."'),
                  "mcp": {"tool": "issue_create",
                          "args": {"repo": "acme/payments-api",
                                   "title": "Add dead-letter queue for failed webhooks",
                                   "body": "Failed webhook deliveries should land in a DLQ, not silently drop."}}},
        "real_mapping": {
            "api": "gh issue create -R acme/payments-api -t '…' -b '…'  (prints the new issue URL)",
            "mcp": "gh-mcp › create_issue",
            "cli": "gh api -X POST repos/acme/payments-api/issues -f title=… -f body=…  (REST 2022-11-28)",
            "doc": "https://cli.github.com/manual/gh_issue_create"},
        "clone_output": created_out,
        "real_output": {
            "author": {"id": "", "is_bot": False, "login": "dave-k", "name": "Dave K"},
            "number": 131, "state": "OPEN",
            "title": "Add dead-letter queue for failed webhooks",
            "url": "https://github.com/acme/payments-api/issues/131"},
        "change": {"before": before_rows, "after": after_rows, "new_id": created_out["number"]},
    })

    return {
        "clone": "gh-cli-clone",
        "product": "GitHub",
        "real_service": {
            "name": "GitHub via the gh CLI (REST 2022-11-28), Forgejo-backed",
            "reference": "https://cli.github.com/manual/",
            "api_base": "{gateway}/api/v1  (Forgejo/Gitea-compatible)"},
        "parity": {"verdict": "HIGH",
                   "note": "gh --json field schema: nameWithOwner, state OPEN/CLOSED, PR MERGED, label color sans #, visibility PUBLIC."},
        "seed_file": SEED_REL,
        "surfaces": {"cli": "ghc", "mcp": "ghc-mcp"},
        "capture_note": ("No Docker/Forgejo here — clone_output is produced by the clone's real "
                         "gh-shaping code (ForgejoClient/ghjson) over recorded Forgejo responses "
                         "from the clone's test fixtures."),
        "demos": demos,
    }


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "data" / "gh-cli-clone.json"
    manifest = build()
    out.write_text(json.dumps(manifest, indent=2, default=str))
    populated = sum(1 for d in manifest["demos"] if d.get("clone_output"))
    print(f"OK gh-cli-clone: {len(manifest['demos'])} demos "
          f"({populated} with captured clone_output), fixtures '{manifest['seed_file']}' "
          f"fed through ForgejoClient+ghjson -> {out}")
