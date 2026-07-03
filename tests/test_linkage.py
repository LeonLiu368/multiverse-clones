"""Incident -> fix-PR linkage extraction (linkage.py)."""
from spoink.pipeline import linkage


def _issue(*, description="", attachments=None, comments=None):
    return {
        "description": description,
        "attachments": {"nodes": attachments or []},
        "comments": {"nodes": comments or []},
    }


def test_attachment_link_wins_and_parses():
    it = _issue(attachments=[{"url": "https://github.com/abundant-ai/oddish/pull/224",
                              "title": "fix: recover preview branches", "sourceType": "github"}])
    pr = linkage.best_fix_pr(it)
    assert pr == {"owner": "abundant-ai", "repo": "oddish", "number": 224, "via": "attachment"}


def test_description_and_comment_urls():
    it = _issue(description="root cause in https://github.com/abundant-ai/oddish/pull/300")
    assert linkage.best_fix_pr(it)["number"] == 300
    it2 = _issue(comments=[{"body": "fixed by github.com/abundant-ai/harbor/pull/12"}])
    assert linkage.best_fix_pr(it2)["number"] == 12


def test_attachment_ranks_above_comment_for_same_pr():
    it = _issue(
        comments=[{"body": "see github.com/abundant-ai/oddish/pull/9"}],
        attachments=[{"url": "https://github.com/abundant-ai/oddish/pull/9", "title": ""}])
    refs = linkage.prs_for_linear_issue(it)
    assert len(refs) == 1 and refs[0]["via"] == "attachment"      # deduped, highest-trust source kept


def test_prefer_owner():
    it = _issue(description="dup in github.com/vendor/lib/pull/5 and github.com/abundant-ai/oddish/pull/7")
    assert linkage.best_fix_pr(it, prefer_owner="abundant-ai")["owner"] == "abundant-ai"


def test_no_link_returns_none():
    assert linkage.best_fix_pr(_issue(description="no PR here, just prose")) is None
    assert linkage.prs_for_linear_issue(_issue()) == []
