"""HTTP-endpoint coverage (R6.1): every covered endpoint, happy + >=1 error path,
against the live server. Pins envelope shapes + Google error codes (R4.3/R6.5)."""
import pytest

from tests._helpers import http

DOC = "DOC_PLAN_0001"


# ---- happy paths ----
def test_health(base_url):
    st, body = http("GET", base_url, "/health")
    assert st == 200 and body["status"] == "healthy"


def test_drive_list(base_url):
    st, body = http("GET", base_url, "/drive/v3/files")
    assert st == 200 and body["kind"] == "drive#fileList"
    names = {f["name"] for f in body["files"]}
    assert "Q3 Launch Plan" in names
    assert "Old Draft" not in names  # trashed excluded by default


def test_drive_list_q_grammar(base_url):
    st, body = http("GET", base_url, "/drive/v3/files?q=fullText+contains+'2026-09-15'")
    assert st == 200
    assert [f["name"] for f in body["files"]] == ["Q3 Launch Plan"]


def test_drive_get(base_url):
    st, body = http("GET", base_url, f"/drive/v3/files/{DOC}")
    assert st == 200 and body["kind"] == "drive#file" and body["id"] == DOC


def test_drive_export(base_url):
    st, body = http("GET", base_url, f"/drive/v3/files/{DOC}/export")
    assert st == 200 and "Launch date: 2026-09-15" in body


def test_drive_alt_media(base_url):
    st, body = http("GET", base_url, f"/drive/v3/files/{DOC}?alt=media")
    assert st == 200 and "2026-09-15" in body


def test_docs_get(base_url):
    st, body = http("GET", base_url, f"/v1/documents/{DOC}")
    assert st == 200 and body["documentId"] == DOC and "content" in body["body"]


def test_calendar_list(base_url):
    st, body = http("GET", base_url, "/calendar/v3/calendars/primary/events")
    assert st == 200 and body["kind"] == "calendar#events"
    summaries = {e["summary"] for e in body["items"]}
    assert {"Q3 Kickoff", "Design Review"} <= summaries  # >=, write tests may insert


def test_calendar_list_q(base_url):
    st, body = http("GET", base_url, "/calendar/v3/calendars/primary/events?q=LaTeX")
    assert st == 200 and len(body["items"]) == 1


def test_calendar_get(base_url):
    st, body = http("GET", base_url, "/calendar/v3/calendars/primary/events/EV_KICKOFF_1")
    assert st == 200 and body["kind"] == "calendar#event" and body["summary"] == "Q3 Kickoff"


def test_calendar_insert_roundtrip(base_url):
    """events.insert (WRITE) -> the event is observable on a later get/list (R5.2)."""
    st, created = http("POST", base_url, "/calendar/v3/calendars/primary/events",
                       body={"summary": "API RoundTrip",
                             "start": {"dateTime": "2026-09-09T09:00:00Z"},
                             "end": {"dateTime": "2026-09-09T10:00:00Z"}})
    assert st == 200 and created["kind"] == "calendar#event"
    eid = created["id"]
    assert eid and created["created"]  # server minted id + timestamp
    st, got = http("GET", base_url, f"/calendar/v3/calendars/primary/events/{eid}")
    assert st == 200 and got["summary"] == "API RoundTrip"
    st, listing = http("GET", base_url, "/calendar/v3/calendars/primary/events?q=RoundTrip")
    assert st == 200 and [e["id"] for e in listing["items"]] == [eid]


def test_gmail_search(base_url):
    st, body = http("GET", base_url, "/gmail/v1/users/me/messages?q=from:pm")
    assert st == 200 and body["resultSizeEstimate"] == 1


def test_gmail_get(base_url):
    st, body = http("GET", base_url, "/gmail/v1/users/me/messages/MSG_1")
    assert st == 200 and body["id"] == "MSG_1"
    hdrs = {h["name"]: h["value"] for h in body["payload"]["headers"]}
    assert hdrs["Subject"] == "Atlas launch date"


def test_gmail_thread(base_url):
    st, body = http("GET", base_url, "/gmail/v1/users/me/threads/THR_1")
    assert st == 200 and len(body["messages"]) == 2


# ---- error paths ----
def test_drive_get_404(base_url):
    st, body = http("GET", base_url, "/drive/v3/files/NOPE")
    assert st == 404 and body["error"]["status"] == "NOT_FOUND"


def test_drive_bad_query_400(base_url):
    st, body = http("GET", base_url, "/drive/v3/files?q=frobnicate+'x'")
    assert st == 400 and body["error"]["status"] == "INVALID_ARGUMENT"


def test_docs_get_404(base_url):
    st, body = http("GET", base_url, "/v1/documents/NOPE")
    assert st == 404 and body["error"]["status"] == "NOT_FOUND"


def test_calendar_get_404(base_url):
    st, body = http("GET", base_url, "/calendar/v3/calendars/primary/events/NOPE")
    assert st == 404 and body["error"]["status"] == "NOT_FOUND"


def test_calendar_insert_400(base_url):
    """Missing required fields -> Google's INVALID_ARGUMENT (not a 500)."""
    st, body = http("POST", base_url, "/calendar/v3/calendars/primary/events",
                    body={"summary": "no times"})
    assert st == 400 and body["error"]["status"] == "INVALID_ARGUMENT"


def test_gmail_get_404(base_url):
    st, body = http("GET", base_url, "/gmail/v1/users/me/messages/NOPE")
    assert st == 404 and body["error"]["status"] == "NOT_FOUND"


def test_gmail_thread_404(base_url):
    st, body = http("GET", base_url, "/gmail/v1/users/me/threads/NOPE")
    assert st == 404 and body["error"]["status"] == "NOT_FOUND"


def test_auth_required_401(base_url):
    st, body = http("GET", base_url, "/drive/v3/files", token="")
    assert st == 401 and body["error"]["status"] == "UNAUTHENTICATED"
