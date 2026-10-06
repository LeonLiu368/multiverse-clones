#!/usr/bin/env python3
"""Deterministic generator for the ticketvector ``state.json`` fixture.

Emits a FakePlaneBackend snapshot (the schema the ticketvector-service loads from
WORLD_ISSUES_STATE_FILE) describing the Paperless (PNGX) issue tracker for this
incident. The agent reaches it read-only via the ``linear`` / ``jira`` CLIs in
``remote`` mode against http://ticketvector:8765.

Design: the INCIDENT ticket (PNGX-417) is symptom-level — new documents stop being
searchable after a batch errors mid-commit, worker logs repeat ``LockBusy``, a
restart clears it briefly. It points the responder at the on-call chat for root
cause but does NOT name the code fix. The exact localization (WriteBatch.__exit__
releasing the writer only on the success path; move disposal into ``finally``) lives
ONLY in Slack. Distractor tickets (OCR, API, Redis pool, "increase writer heap", …)
are realistic and some are deliberate red herrings.

Run:  python3 generate.py   ->  writes state.json next to this file.
No third-party deps; output is byte-stable (sort_keys).
"""
from __future__ import annotations

import json
import pathlib

WORKSPACE = "acme"
BASE_URL = "https://plane.local"
PROJECT = {"id": "proj-pngx", "key": "PNGX", "name": "Paperless", "archived": False}

USERS = [
    {"id": "user-agent", "name": "Agent User", "handle": "agent"},
    {"id": "user-dana", "name": "Dana Okafor", "handle": "dana"},     # SRE / on-call
    {"id": "user-ravi", "name": "Ravi Menon", "handle": "ravi"},      # search/backend eng
    {"id": "user-mia", "name": "Mia Schultz", "handle": "mia"},       # support
    {"id": "user-theo", "name": "Theo Park", "handle": "theo"},       # platform ops
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

CYCLES = [
    {"id": "cycle-a", "name": "Sprint 2026-06-A", "starts_at": "2026-06-01", "ends_at": "2026-06-14"},
]
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


def issue(
    ident, title, description, state, priority, labels, module,
    *, assignees=None, created="2026-06-06T09:00:00Z", updated="2026-06-06T10:00:00Z",
    comments=0, attachments=0, links=None, relations=None,
):
    return {
        "id": "issue-" + ident.lower(),
        "identifier": ident,
        "project": PROJECT,
        "title": title,
        "description": description,
        "state": state,
        "priority": priority,
        "assignees": assignees or [],
        "labels": [L[n] for n in labels],
        "cycle": CYCLE_A,
        "module": module,
        "links": links or [],
        "relations": relations or [],
        "comments_count": comments,
        "attachments_count": attachments,
        "created_at": created,
        "updated_at": updated,
        "url": url(ident),
    }


def u(handle):
    return next(x for x in USERS if x["handle"] == handle)


# --- The active incident ----------------------------------------------------
INCIDENT_LINKS = [
    {"id": "link-pngx-417-1", "url": "https://runbooks.paperless.local/search-indexing",
     "title": "Search indexing runbook"},
    {"id": "link-pngx-417-2", "url": "https://grafana.paperless.local/d/search/indexer",
     "title": "Indexer throughput dashboard"},
]
INCIDENT_ATTACH = [
    {"id": "attachment-pngx-417-1", "name": "indexer-worker.log", "content_type": "text/plain",
     "size": 20144, "uploaded_at": "2026-06-06T02:30:00Z"},
]

incident = issue(
    "PNGX-417",
    "Search index wedged — new documents not searchable after a failed import batch",
    "Since ~02:08 today, documents ingested after a failed bulk-import batch never become "
    "searchable. The indexer worker logs repeat `LockBusy: failed to acquire index writer "
    "lock`. Restarting paperless-worker clears it for a few minutes, then it wedges again on "
    "the next batch that errors mid-commit. Throughput flatlined on the indexer dashboard at "
    "02:08. Root-cause investigation is happening in the #paperless-oncall channel — see the "
    "thread for the exact code path. Impact: new uploads are invisible in search workspace-wide.",
    S["Todo"], "urgent", ["search", "incident", "regression"], M["Search Indexing"],
    assignees=[u("agent")],
    created="2026-06-06T02:20:00Z", updated="2026-06-06T08:45:00Z",
    comments=3, attachments=1, links=INCIDENT_LINKS,
    relations=[{"id": "relation-pngx-417-1", "type": "duplicated-by",
                "issue": "PNGX-417", "related_issue": "PNGX-418"}],
)

# --- Distractors (realistic; PNGX-419 and PNGX-427 are deliberate red herrings) ---
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
          S["Backlog"], "medium", ["backend", "database"], M["Document Ingestion"],
          created="2026-06-01T09:00:00Z", updated="2026-06-01T10:00:00Z"),
    issue("PNGX-412", "Dark mode: sidebar contrast too low",
          "Selected nav item is hard to read in dark theme.",
          S["Backlog"], "low", ["frontend"], M["REST API"],
          created="2026-06-01T09:00:00Z", updated="2026-06-01T10:00:00Z"),
    issue("PNGX-414", "Add a healthcheck endpoint for the search index",
          "Expose index writer/lock status so we can alert before users notice stalls.",
          S["Todo"], "medium", ["observability", "search"], M["Search Indexing"],
          assignees=[u("dana")], created="2026-06-04T09:00:00Z", updated="2026-06-04T10:00:00Z"),
    issue("PNGX-416", "Consume folder ignores symlinked files",
          "Documents symlinked into the consume dir are not picked up.",
          S["Backlog"], "low", ["backend"], M["Document Ingestion"],
          created="2026-06-02T09:00:00Z", updated="2026-06-02T10:00:00Z"),
    issue("PNGX-418", "Duplicate of PNGX-417 from support intake",
          "Three merchants report uploads not appearing in search since early this morning.",
          S["Todo"], "medium", ["customer-report", "search"], M["Search Indexing"],
          assignees=[u("mia")], created="2026-06-06T03:10:00Z", updated="2026-06-06T03:10:00Z",
          relations=[{"id": "relation-pngx-418-1", "type": "duplicates",
                      "issue": "PNGX-418", "related_issue": "PNGX-417"}]),
    issue("PNGX-419", "Increase Tantivy index writer heap size",
          "Proposal to bump the writer heap from 128MB to 512MB to speed large commits. "
          "NOTE: floated during the incident but ruled out — heap size does not cause the lock to "
          "leak. Tracked separately as an optimisation.",
          S["Backlog"], "low", ["search"], M["Search Indexing"],
          created="2026-06-06T07:00:00Z", updated="2026-06-06T07:30:00Z"),
    issue("PNGX-421", "Search: document schema v2 migration",
          "Plan migration of the index document schema; backfill strategy TBD.",
          S["Backlog"], "low", ["search", "database"], M["Search Indexing"],
          created="2026-05-30T09:00:00Z", updated="2026-05-30T10:00:00Z"),
    issue("PNGX-423", "Flaky test: test_search_highlight intermittently fails in CI",
          "Highlight offsets occasionally off by one under parallel test runs.",
          S["Todo"], "low", ["search"], M["Search Indexing"], assignees=[u("ravi")],
          created="2026-06-04T09:00:00Z", updated="2026-06-04T10:00:00Z"),
    issue("PNGX-425", "Thumbnails missing for multi-page TIFF",
          "Thumbnail generation skips TIFFs with >1 frame.",
          S["Backlog"], "low", ["ocr"], M["OCR Pipeline"],
          created="2026-06-01T09:00:00Z", updated="2026-06-01T10:00:00Z"),
    issue("PNGX-427", "Redis connection pool exhaustion under load",
          "Celery workers occasionally exhaust the Redis pool during nightly bulk imports; "
          "raise pool size. (Unrelated to the search-index lock incident, though it surfaced the "
          "same night.)",
          S["Todo"], "medium", ["backend"], M["Document Ingestion"], assignees=[u("theo")],
          created="2026-06-06T06:00:00Z", updated="2026-06-06T06:30:00Z"),
]

ISSUES = [incident] + distractors

COMMENTS = {
    "PNGX-417": [
        {"id": "comment-pngx-417-1", "issue": "PNGX-417", "author": u("mia"),
         "body": "Support has 3 customers reporting that documents uploaded after ~02:10 don't "
                 "show up in search. Re-uploading doesn't help.",
         "created_at": "2026-06-06T03:05:00Z", "updated_at": "2026-06-06T03:05:00Z"},
        {"id": "comment-pngx-417-2", "issue": "PNGX-417", "author": u("dana"),
         "body": "Indexer throughput flatlined at 02:08, right after a bulk batch raised during "
                 "commit. Bouncing paperless-worker unblocks it for a few minutes, then it wedges "
                 "again the next time a batch errors. Logs are full of `LockBusy: failed to "
                 "acquire index writer lock`.",
         "created_at": "2026-06-06T03:40:00Z", "updated_at": "2026-06-06T03:40:00Z"},
        {"id": "comment-pngx-417-3", "issue": "PNGX-417", "author": u("ravi"),
         "body": "This is the index writer lock not being released once a batch hits an error "
                 "mid-commit — a reindex clears it. I'm chasing the exact code path in "
                 "#paperless-oncall; will link the fix here once we land it. Not a Redis/heap issue.",
         "created_at": "2026-06-06T04:15:00Z", "updated_at": "2026-06-06T04:15:00Z"},
    ],
}

LINKS = {"PNGX-417": INCIDENT_LINKS}
ATTACHMENTS = {"PNGX-417": INCIDENT_ATTACH}
RELATIONS = {
    "PNGX-417": incident["relations"],
    "PNGX-418": distractors[6]["relations"],
}

STATE = {
    "base_url": BASE_URL,
    "workspace": WORKSPACE,
    "project": PROJECT,
    "users": USERS,
    "states": STATES,
    "labels": LABELS,
    "cycles": CYCLES,
    "modules": MODULES,
    "issues": ISSUES,
    "comments": COMMENTS,
    "links": LINKS,
    "attachments": ATTACHMENTS,
    "relations": RELATIONS,
    "history": {},
}


def main() -> None:
    out = pathlib.Path(__file__).with_name("state.json")
    out.write_text(json.dumps(STATE, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(ISSUES)} issues)")


if __name__ == "__main__":
    main()
