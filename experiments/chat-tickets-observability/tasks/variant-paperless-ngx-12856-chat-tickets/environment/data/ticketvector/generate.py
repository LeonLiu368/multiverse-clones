#!/usr/bin/env python3
"""Deterministic generator for the ticketvector ``state.json`` fixture (PR #12856).

Same Paperless (PNGX) tracker shape as the #12865 task, but a different active
incident: under concurrent bulk consumption a fraction of newly consumed documents
never become searchable. The worker logs ``SearchIndexLockError: Could not acquire
index lock within 5s`` — index writes make a SINGLE lock-acquire attempt with no
retry/backoff, so on contention the write is dropped. The ticket carries the symptom
and points at #paperless-oncall; the agreed FIX (bounded exponential backoff + full
jitter, plus a deferred self-heal Celery task on lock exhaustion) lives ONLY in Slack.

Run:  python3 generate.py   ->  writes state.json next to this file.
"""
from __future__ import annotations

import json
import pathlib

WORKSPACE = "acme"
BASE_URL = "https://plane.local"
PROJECT = {"id": "proj-pngx", "key": "PNGX", "name": "Paperless", "archived": False}

USERS = [
    {"id": "user-agent", "name": "Agent User", "handle": "agent"},
    {"id": "user-dana", "name": "Dana Okafor", "handle": "dana"},
    {"id": "user-ravi", "name": "Ravi Menon", "handle": "ravi"},
    {"id": "user-mia", "name": "Mia Schultz", "handle": "mia"},
    {"id": "user-theo", "name": "Theo Park", "handle": "theo"},
]

STATES = [
    {"id": "state-backlog", "name": "Backlog", "category": "backlog"},
    {"id": "state-todo", "name": "Todo", "category": "unstarted"},
    {"id": "state-progress", "name": "In Progress", "category": "started"},
    {"id": "state-review", "name": "In Review", "category": "started"},
    {"id": "state-blocked", "name": "Blocked", "category": "started"},
    {"id": "state-done", "name": "Done", "category": "completed"},
    {"id": "state-canceled", "name": "Canceled", "category": "cancelled"},
]
S = {s["name"]: s for s in STATES}

LABELS = [
    {"id": "label-backend", "name": "backend"},
    {"id": "label-search", "name": "search"},
    {"id": "label-incident", "name": "incident"},
    {"id": "label-regression", "name": "regression"},
    {"id": "label-ocr", "name": "ocr"},
    {"id": "label-api", "name": "api"},
    {"id": "label-frontend", "name": "frontend"},
    {"id": "label-database", "name": "database"},
    {"id": "label-observability", "name": "observability"},
    {"id": "label-customer-report", "name": "customer-report"},
]
L = {x["name"]: x for x in LABELS}

CYCLES = [{"id": "cycle-a", "name": "Sprint 2026-06-A", "starts_at": "2026-06-01", "ends_at": "2026-06-14"}]
CYCLE_A = CYCLES[0]

MODULES = [
    {"id": "module-search", "name": "Search Indexing"},
    {"id": "module-ingest", "name": "Document Ingestion"},
    {"id": "module-ocr", "name": "OCR Pipeline"},
    {"id": "module-api", "name": "REST API"},
]
M = {m["name"]: m for m in MODULES}


def url(identifier: str) -> str:
    return f"{BASE_URL}/{WORKSPACE}/projects/{PROJECT['key']}/issues/{identifier}"


def issue(ident, title, description, state, priority, labels, module, *, assignees=None,
          created="2026-06-06T09:00:00Z", updated="2026-06-06T10:00:00Z",
          comments=0, attachments=0, links=None, relations=None):
    return {
        "id": "issue-" + ident.lower(), "identifier": ident, "project": PROJECT,
        "title": title, "description": description, "state": state, "priority": priority,
        "assignees": assignees or [], "labels": [L[n] for n in labels], "cycle": CYCLE_A,
        "module": module, "links": links or [], "relations": relations or [],
        "comments_count": comments, "attachments_count": attachments,
        "created_at": created, "updated_at": updated, "url": url(ident),
    }


def u(handle):
    return next(x for x in USERS if x["handle"] == handle)


INCIDENT_LINKS = [
    {"id": "link-pngx-531-1", "url": "https://runbooks.paperless.local/search-indexing",
     "title": "Search indexing runbook"},
    {"id": "link-pngx-531-2", "url": "https://grafana.paperless.local/d/search/lock-errors",
     "title": "Index lock error-rate dashboard"},
]
INCIDENT_ATTACH = [
    {"id": "attachment-pngx-531-1", "name": "consumer-lock-errors.log", "content_type": "text/plain",
     "size": 16720, "uploaded_at": "2026-06-06T09:40:00Z"},
]

incident = issue(
    "PNGX-531",
    "Documents silently missing from search after bulk consumption (index lock contention)",
    "When several consumers run in parallel (nightly bulk import, re-OCR sweeps), a fraction of "
    "newly consumed documents never appear in search — no error is surfaced to the user. The "
    "worker log shows bursts of `SearchIndexLockError: Could not acquire index lock within 5s`. "
    "It correlates exactly with indexing concurrency: the more parallel consumers, the more docs "
    "go missing. A later manual re-index makes them searchable, so the documents are fine — the "
    "index write is being lost under lock contention. Root-cause + the agreed fix are being worked "
    "in #paperless-oncall. Impact: silent search gaps after every large import.",
    S["Todo"], "urgent", ["search", "incident", "regression"], M["Search Indexing"],
    assignees=[u("agent")], created="2026-06-06T09:15:00Z", updated="2026-06-06T11:30:00Z",
    comments=3, attachments=1, links=INCIDENT_LINKS,
    relations=[{"id": "relation-pngx-531-1", "type": "duplicated-by",
                "issue": "PNGX-531", "related_issue": "PNGX-532"}],
)

distractors = [
    issue("PNGX-405", "OCR queue backlog grows on very large PDFs",
          "Tesseract step lags on 200+ page scans; queue depth climbs in the evening.",
          S["In Progress"], "high", ["ocr"], M["OCR Pipeline"], assignees=[u("theo")],
          created="2026-06-02T09:00:00Z", updated="2026-06-05T11:00:00Z"),
    issue("PNGX-409", "REST API: /api/documents/ pagination off-by-one on last page",
          "Last page returns one fewer item than `count` implies when page_size divides evenly.",
          S["Todo"], "medium", ["api"], M["REST API"], assignees=[u("ravi")],
          created="2026-06-03T09:00:00Z", updated="2026-06-03T10:00:00Z"),
    issue("PNGX-411", "Bulk tag edit slow for >5k documents",
          "Applying a tag to a large selection takes minutes; N+1 on document_tags.",
          S["Backlog"], "medium", ["backend", "database"], M["Document Ingestion"]),
    issue("PNGX-412", "Dark mode: sidebar contrast too low",
          "Selected nav item is hard to read in dark theme.",
          S["Backlog"], "low", ["frontend"], M["REST API"]),
    issue("PNGX-414", "Add a healthcheck endpoint for the search index",
          "Expose index writer/lock status so we can alert before users notice stalls.",
          S["Todo"], "medium", ["observability", "search"], M["Search Indexing"], assignees=[u("dana")],
          created="2026-06-04T09:00:00Z", updated="2026-06-04T10:00:00Z"),
    issue("PNGX-528", "Re-OCR sweep schedule overlaps nightly import",
          "The weekly re-OCR job and the nightly bulk import both run at 02:00, doubling indexing "
          "concurrency. Consider staggering them. (Ops mitigation, not the root cause.)",
          S["Todo"], "medium", ["ocr", "backend"], M["Document Ingestion"], assignees=[u("theo")],
          created="2026-06-06T08:00:00Z", updated="2026-06-06T08:30:00Z"),
    issue("PNGX-529", "Proposal: raise index lock timeout 5s -> 30s",
          "Floated as a quick fix for the lock errors. NOTE: ruled out in the incident review — a "
          "longer single timeout just delays the failure under sustained contention and stalls "
          "consumers; it does not retry. Kept for reference only.",
          S["Backlog"], "low", ["search"], M["Search Indexing"],
          created="2026-06-06T10:00:00Z", updated="2026-06-06T10:20:00Z"),
    issue("PNGX-532", "Duplicate of PNGX-531 from support intake",
          "Customer reports a batch of uploads not searchable after their migration import.",
          S["Todo"], "medium", ["customer-report", "search"], M["Search Indexing"], assignees=[u("mia")],
          created="2026-06-06T09:50:00Z", updated="2026-06-06T09:50:00Z",
          relations=[{"id": "relation-pngx-532-1", "type": "duplicates",
                      "issue": "PNGX-532", "related_issue": "PNGX-531"}]),
    issue("PNGX-423", "Flaky test: test_search_highlight intermittently fails in CI",
          "Highlight offsets occasionally off by one under parallel test runs.",
          S["Todo"], "low", ["search"], M["Search Indexing"], assignees=[u("ravi")],
          created="2026-06-04T09:00:00Z", updated="2026-06-04T10:00:00Z"),
    issue("PNGX-425", "Thumbnails missing for multi-page TIFF",
          "Thumbnail generation skips TIFFs with >1 frame.",
          S["Backlog"], "low", ["ocr"], M["OCR Pipeline"]),
    issue("PNGX-427", "Redis connection pool exhaustion under load",
          "Celery workers occasionally exhaust the Redis pool during nightly bulk imports; raise "
          "pool size. (Surfaced the same night; not the search-index lock issue.)",
          S["Todo"], "medium", ["backend"], M["Document Ingestion"], assignees=[u("theo")],
          created="2026-06-06T06:00:00Z", updated="2026-06-06T06:30:00Z"),
]

ISSUES = [incident] + distractors

COMMENTS = {
    "PNGX-531": [
        {"id": "comment-pngx-531-1", "issue": "PNGX-531", "author": u("dana"),
         "body": "Lock error rate on the dashboard tracks indexing concurrency 1:1. Single consumer: "
                 "~0 errors. Four parallel consumers: hundreds of `Could not acquire index lock "
                 "within 5s` and a matching number of docs missing from search.",
         "created_at": "2026-06-06T10:05:00Z", "updated_at": "2026-06-06T10:05:00Z"},
        {"id": "comment-pngx-531-2", "issue": "PNGX-531", "author": u("mia"),
         "body": "Customer migration import (~9k docs) — about 600 not searchable afterwards. A "
                 "re-index fixed all of them, so the docs themselves are fine.",
         "created_at": "2026-06-06T10:30:00Z", "updated_at": "2026-06-06T10:30:00Z"},
        {"id": "comment-pngx-531-3", "issue": "PNGX-531", "author": u("ravi"),
         "body": "Root cause is that index writes make a single lock-acquire attempt and just give "
                 "up on contention — no retry, and the failure is swallowed so the write is dropped. "
                 "Working the exact fix in #paperless-oncall; will link the PR here. Bumping the "
                 "timeout (PNGX-529) is not it.",
         "created_at": "2026-06-06T11:00:00Z", "updated_at": "2026-06-06T11:00:00Z"},
    ],
}
LINKS = {"PNGX-531": INCIDENT_LINKS}
ATTACHMENTS = {"PNGX-531": INCIDENT_ATTACH}
RELATIONS = {"PNGX-531": incident["relations"], "PNGX-532": distractors[7]["relations"]}

STATE = {
    "base_url": BASE_URL, "workspace": WORKSPACE, "project": PROJECT, "users": USERS,
    "states": STATES, "labels": LABELS, "cycles": CYCLES, "modules": MODULES, "issues": ISSUES,
    "comments": COMMENTS, "links": LINKS, "attachments": ATTACHMENTS, "relations": RELATIONS,
    "history": {},
}


def main() -> None:
    out = pathlib.Path(__file__).with_name("state.json")
    out.write_text(json.dumps(STATE, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(ISSUES)} issues)")


if __name__ == "__main__":
    main()
