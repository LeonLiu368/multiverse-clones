"""Faithful-query regression tests for the Drive/Gmail `q` engine.

Locks in the behaviors the real Google APIs have (and that earlier silently broke):
content search via fullText, and/or/not + parentheses, proper errors on bad
queries, default trashed exclusion, and Gmail's space==AND / OR semantics.
"""
import pytest

from gwsclone import store
from gwsclone.db import get_engine, init_db, session_factory
from gwsclone.seed import schema
from gwsclone.seed.load import load_seed_into_engine

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture()
def s():
    eng = get_engine(":memory:")
    init_db(eng)
    seed = {
        "drive": [
            {"id": "F1", "name": "Resume", "mimeType": DOCX, "parents": ["root"]},
            {"id": "F2", "name": "Behavioral Prep", "mimeType": DOCX, "parents": ["root"]},
            {"id": "F3", "name": "Budget", "mimeType": "application/pdf", "parents": ["root"]},
            {"id": "F4", "name": "Old", "mimeType": DOCX, "parents": ["root"], "trashed": True},
        ],
        "documents": [
            {"documentId": "F1", "title": "Resume", "body": schema.make_body(
                schema.paragraph("I built MarketLens, a performance dashboard for startups.\n"))},
            {"documentId": "F2", "title": "Behavioral Prep", "body": schema.make_body(
                schema.paragraph("Notes about interviews and culture.\n"))},
        ],
        "gmail": [
            schema.message("M1", "Atlas launch date", "ship date?", frm="pm@acme.example",
                           to="launch@acme.example", thread_id="T", internal_date="100"),
            schema.message("M2", "Re: Atlas launch date", "approved", frm="mira@acme.example",
                           to="launch@acme.example", thread_id="T", internal_date="200"),
        ],
    }
    load_seed_into_engine(seed, eng)
    Session = session_factory(eng)
    with Session() as sess:
        yield sess


def names(rows):
    return sorted(r["name"] for r in rows)


def test_fulltext_searches_content(s):
    assert names(store.list_files(s, "fullText contains 'MarketLens'", 100)) == ["Resume"]
    assert store.list_files(s, "fullText contains 'nonexistent-zzz'", 100) == []


def test_name_contains_and_or(s):
    assert names(store.list_files(s, "name contains 'Resume'", 100)) == ["Resume"]
    assert names(store.list_files(s, "name contains 'Resume' or name contains 'Behavioral'", 100)) \
        == ["Behavioral Prep", "Resume"]


def test_compound_and_parens(s):
    q = "(name contains 'Resume' or name contains 'Behavioral') and mimeType = '%s'" % DOCX
    assert names(store.list_files(s, q, 100)) == ["Behavioral Prep", "Resume"]


def test_trashed_excluded_by_default(s):
    assert "Old" not in names(store.list_files(s, None, 100))
    assert names(store.list_files(s, "trashed = true", 100)) == ["Old"]


def test_invalid_query_raises(s):
    with pytest.raises(store.QueryError):
        store.list_files(s, "frobnicate 'x'", 100)


def test_gmail_space_is_and_and_or(s):
    assert len(store.list_messages(s, "from:pm subject:Atlas", 100)) == 1
    assert len(store.list_messages(s, "from:pm OR from:mira", 100)) == 2
    assert len(store.list_messages(s, "from:nobody", 100)) == 0
