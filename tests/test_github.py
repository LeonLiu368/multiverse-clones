"""GitHub fetch_repo mapping with a fake REST client (no token needed)."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spoink.github_export import fetch_repo  # noqa: E402

REPO = {"full_name": "o/r", "private": True, "default_branch": "main", "description": "d",
        "created_at": "2025-01-01T00:00:00Z", "pushed_at": "2026-06-25T00:00:00Z"}
ISSUES_AND_PRS = [
    {"number": 1, "title": "bug", "body": "b", "state": "open", "user": {"login": "alice"},
     "labels": [{"name": "bug"}], "assignees": [{"login": "bob"}],
     "created_at": "2026-06-01T00:00:00Z", "updated_at": "2026-06-02T00:00:00Z", "closed_at": None},
    {"number": 2, "title": "a PR", "pull_request": {"url": "..."}, "user": {"login": "carol"},
     "created_at": "2026-06-03T00:00:00Z"},  # excluded from issues
]
PULLS = [{"number": 2, "title": "a PR", "body": "", "state": "closed", "user": {"login": "carol"},
          "head": {"ref": "fix/x"}, "base": {"ref": "main"}, "merged_at": "2026-06-04T00:00:00Z",
          "created_at": "2026-06-03T00:00:00Z", "updated_at": "2026-06-04T00:00:00Z", "closed_at": "2026-06-04T00:00:00Z"}]
COMMENTS = [{"id": 11, "issue_url": "https://api.github.com/repos/o/r/issues/1",
             "user": {"login": "bob"}, "body": "looking", "created_at": "2026-06-01T12:00:00Z", "updated_at": None}]


class FakeGH:
    def get_json(self, path, **p):
        return REPO

    def paginate(self, path, **p):
        if path.endswith("/issues"):
            return iter(ISSUES_AND_PRS)
        if path.endswith("/pulls"):
            return iter(PULLS)
        if path.endswith("/issues/comments"):
            return iter(COMMENTS)
        return iter([])


def test_fetch_repo_splits_and_preserves_timestamps():
    d = fetch_repo(FakeGH(), "o", "r")
    assert d["repo"]["full_name"] == "o/r" and d["repo"]["default_branch"] == "main"
    # PR #2 is filtered out of issues; pulls captured separately
    assert [i["number"] for i in d["issues"]] == [1]
    assert d["issues"][0]["labels"] == ["bug"] and d["issues"][0]["assignees"] == ["bob"]
    assert [p["number"] for p in d["pulls"]] == [2]
    assert d["pulls"][0]["merged_at"] == "2026-06-04T00:00:00Z" and d["pulls"][0]["head"] == "fix/x"
    # comment maps back to its issue number via issue_url
    assert d["comments"][0]["number"] == 1 and d["comments"][0]["user"] == "bob"
