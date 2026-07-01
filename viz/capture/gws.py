"""Capture google-workspace-clone parity demos in-process against the real seed.

Running this verifies the seed format is accepted (the clone's seed loader + store
load it and serve reads across Drive / Docs / Gmail / Calendar) AND captures the
clone's ACTUAL output for the dashboard comparison boxes. The `real_output` golden
samples are authored from the real Google Workspace REST API docs (Drive v3 /
Docs v1 / Gmail v1 / Calendar v3) so they share the same field SHAPE.

The seed is the deterministic event-room corpus fixture — a Takeout-derived mailbox
+ calendar + Drive/Docs field, the only in-repo seed that populates all four
surfaces (so `is:unread` and the calendar write→read round-trip have real data).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

CLONE = Path(__file__).resolve().parents[2] / "clones" / "google-workspace-clone"
sys.path.insert(0, str(CLONE / "src"))

from gwsclone import store  # noqa: E402
from gwsclone.db import get_engine, session_factory  # noqa: E402
from gwsclone.seed.load import load_seed  # noqa: E402
from gwsclone.store import iter_paragraphs  # noqa: E402

# All-four-surface seed (Drive files + Docs bodies + Gmail mailbox + Calendar).
SEED_REL = "oddish/tasks/gws-event-room/environment/data/gws/fixture.json"

# Pinned demo inputs (chosen so each capture is small + reproducible).
DRIVE_Q = "name contains 'notes'"
GMAIL_Q = "is:unread"
CAL_ID = "primary"
CAL_TMIN = "2018-08-27T00:00:00Z"
CAL_TMAX = "2018-08-28T00:00:00Z"
NEW_EVENT_ID = "gwsviz0evt0designreview01"  # explicit id → byte-stable manifest


def build() -> dict:
    seed = json.load(open(CLONE / SEED_REL))
    db = tempfile.mktemp(suffix=".db")
    counts = load_seed(seed, db)  # verifies the seed format is accepted
    engine = get_engine(db)
    Session = session_factory(engine)

    demos = []
    with Session() as s:
        demos.append(_drive_list(s))
        demos.append(_docs_get(s))
        demos.append(_gmail_search(s))
        demos.append(_calendar_create(s))

    return {
        "clone": "google-workspace-clone",
        "product": "Google Workspace",
        "real_service": {
            "name": "Google Workspace (Drive v3 / Docs v1 / Gmail v1 / Calendar v3)",
            "reference": "https://developers.google.com/workspace",
            "api_base": "{gateway}"},
        "parity": {
            "verdict": "HIGH after reliability pass",
            "note": ("drive#fileList/drive#file/calendar#event kinds, Drive q-grammar, "
                     "Gmail is:/after:/before: filters enforced (has: → 400), "
                     "{error:{code,message}} body.")},
        "seed_file": SEED_REL,
        "surfaces": {"cli": "gws-cli", "mcp": "gws-mcp"},
        "_seed_counts": counts,
        "demos": demos,
    }


# --------------------------------------------------------------- Drive: files.list
def _drive_list(s) -> dict:
    files = store.list_files(s, DRIVE_Q, 8)
    clone_output = {"kind": "drive#fileList", "incompleteSearch": False, "files": files}
    sample = files[0]
    return {
        "id": "drive-list",
        "title": "List Drive files (q-grammar)",
        "method": "GET",
        "capability": "Drive files.list — q search",
        "seed_excerpt": {"drive": [{"id": f["id"], "name": f["name"],
                                    "mimeType": f["mimeType"]} for f in files[:3]]},
        "ui": {"type": "table", "title": "Drive › My Drive",
               "columns": ["name", "mimeType", "id"],
               "rows": [{"name": f["name"], "mimeType": f["mimeType"], "id": f["id"]}
                        for f in files]},
        "agent": {
            "cli": f"gws-cli drive ls -q \"{DRIVE_Q}\"",
            "mcp": {"tool": "gws_list_files", "args": {"q": DRIVE_Q}}},
        "real_mapping": {
            "api": "GET /drive/v3/files?q=name+contains+'notes'",
            "mcp": "gws-mcp › gws_list_files",
            "cli": "curl -H 'Authorization: Bearer …' '.../drive/v3/files?q=…'",
            "doc": "https://developers.google.com/drive/api/reference/rest/v3/files/list"},
        "clone_output": clone_output,
        "real_output": {
            "kind": "drive#fileList", "incompleteSearch": False,
            "files": [{
                "kind": "drive#file", "id": sample["id"], "name": sample["name"],
                "mimeType": sample["mimeType"]}]},
    }


# ------------------------------------------------------------- Docs: documents.get
def _docs_get(s) -> dict:
    # pick a Doc that maps 1:1 to a Drive file returned by the drive-list demo, so
    # the doc demo threads off the same file the agent just saw.
    files = store.list_files(s, DRIVE_Q, 20)
    doc = None
    for f in files:
        d = store.get_document(s, f["id"])
        paras = [(st, t.strip()) for st, t in iter_paragraphs(d.body) if t.strip()] if d else []
        if d and len(paras) >= 5:
            doc = d
            break
    if doc is None:  # fall back to the first document with a body
        doc = store.get_document(s, files[0]["id"])

    clone_output = store.document_resource(doc)
    blocks = _doc_blocks(doc.body)
    return {
        "id": "docs-get",
        "title": "Get a Google Doc (structural body)",
        "method": "GET",
        "capability": "Docs documents.get — body tree",
        "seed_excerpt": {"documents": [{"documentId": doc.document_id,
                                        "title": doc.title,
                                        "revisionId": doc.revision_id}]},
        "ui": {"type": "doc", "title": "Docs", "doc_title": doc.title, "blocks": blocks},
        "agent": {
            "cli": f"gws-cli docs get {doc.document_id}",
            "mcp": {"tool": "gws_get_document", "args": {"document_id": doc.document_id}}},
        "real_mapping": {
            "api": "GET /v1/documents/{documentId}",
            "mcp": "gws-mcp › gws_get_document",
            "cli": "curl -H 'Authorization: Bearer …' '.../v1/documents/{id}'",
            "doc": "https://developers.google.com/docs/api/reference/rest/v1/documents/get"},
        "clone_output": clone_output,
        "real_output": {
            "documentId": doc.document_id, "title": doc.title,
            "revisionId": doc.revision_id,
            "body": {"content": [{
                "startIndex": 1, "endIndex": len((blocks[0]["text"] if blocks else "") ) + 1,
                "paragraph": {
                    "elements": [{"startIndex": 1, "endIndex": 2, "textRun": {
                        "content": (blocks[0]["text"] + "\n") if blocks else "\n",
                        "textStyle": {}}}],
                    "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"}}}]},
            "namedStyles": {}, "inlineObjects": {}},
    }


def _doc_blocks(body: dict, limit: int = 8) -> list[dict]:
    out = []
    for style, text in iter_paragraphs(body):
        t = text.strip()
        if not t:
            continue
        kind = "h" if ("HEADING" in style or "TITLE" in style) else ""
        out.append({"type": kind, "text": t})
        if len(out) >= limit:
            break
    return out


# ----------------------------------------------------------- Gmail: messages.list
def _gmail_search(s) -> dict:
    msgs = store.list_messages(s, GMAIL_Q, 8)
    refs = [{"id": m.id, "threadId": m.thread_id} for m in msgs]
    clone_output = {"messages": refs, "resultSizeEstimate": len(refs)}
    return {
        "id": "gmail-search",
        "title": "Search Gmail (is:unread)",
        "method": "GET",
        "capability": "Gmail messages.list — is:/after:/before: filters",
        "seed_excerpt": {"gmail": [{"id": m.id, "subject": m.subject,
                                    "labelIds": m.label_ids} for m in msgs[:3]]},
        "ui": {"type": "list", "title": "Gmail › Unread",
               "rows": [{"icon": "✉", "title": m.subject or "(no subject)",
                         "sub": m.from_addr, "tags": ["unread"]} for m in msgs]},
        "agent": {
            "cli": "gws-cli gmail search \"is:unread\"",
            "mcp": {"tool": "gws_search_messages", "args": {"q": "is:unread"}}},
        "real_mapping": {
            "api": "GET /gmail/v1/users/me/messages?q=is:unread",
            "mcp": "gws-mcp › gws_search_messages",
            "cli": "curl -H 'Authorization: Bearer …' '.../gmail/v1/users/me/messages?q=is:unread'",
            "doc": "https://developers.google.com/gmail/api/reference/rest/v1/users.messages/list"},
        "clone_output": clone_output,
        "real_output": {
            "messages": [{"id": refs[0]["id"], "threadId": refs[0]["threadId"]}] if refs else [],
            "resultSizeEstimate": len(refs)},
    }


# ------------------------------------------------------ Calendar: events.insert (POST)
def _calendar_create(s) -> dict:
    before = store.list_events(s, CAL_ID, None, CAL_TMIN, CAL_TMAX)
    created = store.insert_event(s, CAL_ID, {
        "id": NEW_EVENT_ID,
        "summary": "Design review sync",
        "location": "Room 4",
        "description": "Parity demo — write→read round-trip.",
        "start": {"dateTime": "2018-08-27T15:00:00Z"},
        "end": {"dateTime": "2018-08-27T16:00:00Z"}})
    clone_output = store.event_resource(created)
    after = store.list_events(s, CAL_ID, None, CAL_TMIN, CAL_TMAX)
    return {
        "id": "calendar-create",
        "title": "Create a Calendar event",
        "method": "POST",
        "capability": "Calendar events.insert — write→read round-trip",
        "seed_excerpt": {"calendar_before": len(before)},
        "ui": {"type": "timeline", "title": "Calendar › primary",
               "before": [_ev(e) for e in before],
               "after": [_ev(e) for e in after],
               "new_id": created.id},
        "agent": {
            "cli": ("gws-cli calendar create -s \"Design review sync\" "
                    "--start 2018-08-27T15:00:00Z --end 2018-08-27T16:00:00Z "
                    "--location \"Room 4\""),
            "mcp": {"tool": "gws_create_event",
                    "args": {"summary": "Design review sync",
                             "start": "2018-08-27T15:00:00Z",
                             "end": "2018-08-27T16:00:00Z",
                             "location": "Room 4"}}},
        "real_mapping": {
            "api": "POST /calendar/v3/calendars/{calendarId}/events",
            "mcp": "gws-mcp › gws_create_event",
            "cli": "curl -X POST -H 'Authorization: Bearer …' '.../calendar/v3/calendars/primary/events'",
            "doc": "https://developers.google.com/calendar/api/v3/reference/events/insert"},
        "clone_output": clone_output,
        "real_output": {
            "kind": "calendar#event", "id": created.id, "status": "confirmed",
            "summary": "Design review sync", "location": "Room 4",
            "start": {"dateTime": "2018-08-27T15:00:00Z"},
            "end": {"dateTime": "2018-08-27T16:00:00Z"},
            "created": created.created, "updated": created.updated,
            "organizer": {"email": "me@example.com", "self": True}},
        "change": {
            "before": [_ev(e) for e in before],
            "after": [_ev(e) for e in after],
            "new_id": created.id},
    }


def _ev(e: dict) -> dict:
    return {"id": e["id"], "title": e.get("summary", ""),
            "tags": [(e.get("start") or {}).get("dateTime")
                     or (e.get("start") or {}).get("date") or ""]}


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "data" / "google-workspace-clone.json"
    manifest = build()
    out.write_text(json.dumps(manifest, indent=2, default=str))
    populated = sum(1 for d in manifest["demos"] if d.get("clone_output"))
    print(f"OK google-workspace-clone: {len(manifest['demos'])} demos "
          f"({populated} with clone_output), seed '{manifest['seed_file']}' "
          f"accepted {manifest['_seed_counts']} -> {out}")
