"""Deterministic "prod" Drive corpus — the needle buried in realistic distraction.

This is the data baked into ``gworkspace-service:prod-v1``. It is the SAME needle
as ``fixtures/acme.json`` (the "Q3 Launch Plan" doc whose body carries
``Launch date: 2026-09-15``) plus a deterministic field of decoy Drive files and
docs, so that switching a task's service image ``:empty`` → ``:prod-v1`` changes
*only* the retrieval difficulty (needle-alone vs needle-among-distractors), never
the answer.

Adversarial by construction: several decoys are *also* "launch plan" documents
carrying plausible-but-wrong dates (a superseded Q3 draft, the Q2/Q4 plans, a
mobile track), so an agent that grabs the first launch-ish doc — or the first
``Launch date:`` line it sees — picks the wrong value. Only the doc named exactly
``Q3 Launch Plan`` holds ``2026-09-15``.

Everything is generated from a seeded ``random.Random`` so the baked DB is
byte-reproducible.
"""

from __future__ import annotations

import random
from typing import Any

from ..ids import gen_file_id
from . import schema

DOC_MIME = schema.DOC_MIME
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
SLIDE_MIME = "application/vnd.google-apps.presentation"
FOLDER_MIME = "application/vnd.google-apps.folder"
PDF_MIME = "application/pdf"

# The needle — pinned id/name/date, identical to fixtures/acme.json. The grader
# downstream pins 2026-09-15; keep these three in lockstep.
NEEDLE_ID = "DOC_Q3PLAN_0001"
NEEDLE_NAME = "Q3 Launch Plan"
NEEDLE_DATE = "2026-09-15"

_OWNERS = [
    {"displayName": "Mira Devon", "emailAddress": "mira@acme.example"},
    {"displayName": "Theo Park", "emailAddress": "theo@acme.example"},
    {"displayName": "Lena Cho", "emailAddress": "lena@acme.example"},
    {"displayName": "Sam Ruiz", "emailAddress": "sam@acme.example"},
]

# Decoy launch-ish docs: name -> (wrong date, note). NONE of these dates is the
# answer; each is plausible enough to fool a careless reader.
_LAUNCH_DECOYS = [
    ("Q3 Launch Plan (DRAFT — superseded)", "2026-09-08", "superseded draft, do not use"),
    ("Q2 Launch Plan", "2026-06-15", "previous quarter"),
    ("Q4 Launch Plan", "2026-12-01", "next quarter"),
    ("Launch Plan — Mobile", "2026-10-20", "mobile track, separate schedule"),
    ("Launch Readiness Checklist", "2026-09-12", "internal go/no-go review date, not launch"),
]

# Filler file name fragments for bulk Drive distraction (non-launch).
_FILLER_DOCS = [
    "Pricing PRD", "Onboarding Spec", "Q3 OKRs", "Eng Retro Notes", "Brand Guidelines",
    "Support Runbook", "Data Privacy Review", "Hiring Plan", "Roadmap Overview",
    "Incident Postmortem", "API Style Guide", "Design System Notes",
]
_FILLER_SHEETS = ["Budget", "Metrics Dashboard", "Headcount", "A/B Test Results"]
_FILLER_SLIDES = ["Launch Deck", "All-Hands Q3", "Investor Update"]
_FILLER_PDFS = ["Vendor Contract", "Security Audit", "SOW — Acme"]


def _doc(doc_id: str, name: str, *lines: str, revision: str = "3",
         owner: dict | None = None, modified: str = "2026-05-01T10:00:00Z") -> tuple[dict, dict]:
    """Return (drive_file, document) for a Google Doc whose body is `lines`."""
    blocks = [schema.paragraph(name + "\n", style="HEADING_1")]
    blocks += [schema.paragraph(ln + "\n") for ln in lines]
    drive_file = {
        "id": doc_id, "name": name, "mimeType": DOC_MIME, "parents": ["root"],
        "modifiedTime": modified, "owners": [owner or _OWNERS[0]],
    }
    document = {
        "documentId": doc_id, "title": name, "revisionId": revision,
        "body": schema.make_body(*blocks),
    }
    return drive_file, document


def build_corpus(seed: int = 42, filler: int = 24) -> dict[str, Any]:
    """Build the canonical prod corpus seed (needle + decoys + filler)."""
    rng = random.Random(seed)
    drive: list[dict] = []
    documents: list[dict] = []

    # 1) The needle — exactly the fixtures/acme.json content.
    f, d = _doc(
        NEEDLE_ID, NEEDLE_NAME,
        "Owner: Mira Devon",
        f"Launch date: {NEEDLE_DATE}",
        "Status: on track",
        revision="7", owner=_OWNERS[0], modified="2026-06-01T10:00:00Z",
    )
    drive.append(f)
    documents.append(d)

    # 2) Adversarial launch-ish decoys with plausible-but-wrong dates.
    for name, wrong_date, note in _LAUNCH_DECOYS:
        f, d = _doc(
            gen_file_id(rng), name,
            f"Owner: {rng.choice(_OWNERS)['displayName']}",
            f"Launch date: {wrong_date}",
            f"Note: {note}",
            revision=str(rng.randint(1, 9)), owner=rng.choice(_OWNERS),
            modified="2026-04-%02dT09:00:00Z" % rng.randint(1, 28),
        )
        drive.append(f)
        documents.append(d)

    # 3) Bulk filler — realistic Drive clutter across mime types.
    def _rand_modified() -> str:
        return "2026-0%d-%02dT%02d:00:00Z" % (rng.randint(1, 6), rng.randint(1, 28), rng.randint(8, 18))

    for base in _FILLER_DOCS[:max(0, filler)]:
        f, d = _doc(
            gen_file_id(rng), base,
            f"Owner: {rng.choice(_OWNERS)['displayName']}",
            "This document is unrelated to the launch schedule.",
            revision=str(rng.randint(1, 5)), owner=rng.choice(_OWNERS),
            modified=_rand_modified(),
        )
        drive.append(f)
        documents.append(d)

    for name, mime in (
        [(n, SHEET_MIME) for n in _FILLER_SHEETS]
        + [(n, SLIDE_MIME) for n in _FILLER_SLIDES]
        + [(n, PDF_MIME) for n in _FILLER_PDFS]
    ):
        drive.append({
            "id": gen_file_id(rng), "name": name, "mimeType": mime, "parents": ["root"],
            "modifiedTime": _rand_modified(), "owners": [rng.choice(_OWNERS)],
        })

    return schema.normalize({"drive": drive, "documents": documents})


if __name__ == "__main__":  # python -m gwsclone.seed.corpus [seed] > corpus.json
    import sys

    s = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    print(schema.to_json(build_corpus(s)))
