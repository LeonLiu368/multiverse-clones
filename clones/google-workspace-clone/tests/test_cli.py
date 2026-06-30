"""`gws-cli` subprocess coverage (R6.1): every CLI command, happy + >=1 error path.
The CLI is a thin HTTP client of the live server (R3.2)."""
import json

from tests._helpers import run_cli

DOC = "DOC_PLAN_0001"


def _json(out):
    return json.loads(out)


# ---- drive ----
def test_cli_drive_ls(cli_env):
    rc, out, err = run_cli(cli_env, "drive", "ls")
    assert rc == 0, err
    assert "Q3 Launch Plan" in out


def test_cli_drive_ls_q(cli_env):
    rc, out, _ = run_cli(cli_env, "drive", "ls", "-q", "name contains 'Launch'")
    assert rc == 0
    assert _json(out)["files"][0]["name"] == "Q3 Launch Plan"


def test_cli_drive_get(cli_env):
    rc, out, _ = run_cli(cli_env, "drive", "get", DOC)
    assert rc == 0 and _json(out)["id"] == DOC


def test_cli_drive_export(cli_env):
    rc, out, _ = run_cli(cli_env, "drive", "export", DOC)
    assert rc == 0 and "2026-09-15" in out


# ---- docs ----
def test_cli_docs_get(cli_env):
    rc, out, _ = run_cli(cli_env, "docs", "get", DOC)
    assert rc == 0 and _json(out)["documentId"] == DOC


def test_cli_docs_text(cli_env):
    rc, out, _ = run_cli(cli_env, "docs", "text", DOC)
    assert rc == 0 and "Launch date: 2026-09-15" in out


def test_cli_docs_search(cli_env):
    rc, out, _ = run_cli(cli_env, "docs", "search", DOC, "Launch date")
    assert rc == 0 and any("2026-09-15" in r["text"] for r in _json(out))


# ---- calendar ----
def test_cli_calendar_events(cli_env):
    rc, out, _ = run_cli(cli_env, "calendar", "events")
    assert rc == 0
    summaries = {e["summary"] for e in _json(out)["items"]}
    assert {"Q3 Kickoff", "Design Review"} <= summaries  # >=, other tests may insert


def test_cli_calendar_get(cli_env):
    rc, out, _ = run_cli(cli_env, "calendar", "get", "EV_KICKOFF_1")
    assert rc == 0 and _json(out)["summary"] == "Q3 Kickoff"


def test_cli_calendar_create_roundtrip(cli_env):
    """`calendar create` (WRITE) then read it back via `calendar get` (R5.2)."""
    rc, out, err = run_cli(cli_env, "calendar", "create", "-s", "CLI RoundTrip",
                           "--start", "2026-09-10T09:00:00Z", "--end", "2026-09-10T10:00:00Z")
    assert rc == 0, err
    eid = _json(out)["id"]
    rc, out2, _ = run_cli(cli_env, "calendar", "get", eid)
    assert rc == 0 and _json(out2)["summary"] == "CLI RoundTrip"


# ---- gmail ----
def test_cli_gmail_search(cli_env):
    rc, out, _ = run_cli(cli_env, "gmail", "search", "from:pm")
    assert rc == 0 and _json(out)["resultSizeEstimate"] == 1


def test_cli_gmail_get(cli_env):
    rc, out, _ = run_cli(cli_env, "gmail", "get", "MSG_1")
    assert rc == 0 and _json(out)["id"] == "MSG_1"


def test_cli_gmail_thread(cli_env):
    rc, out, _ = run_cli(cli_env, "gmail", "thread", "THR_1")
    assert rc == 0 and len(_json(out)["messages"]) == 2


# ---- error paths (non-zero exit) ----
def test_cli_drive_get_error(cli_env):
    rc, _, err = run_cli(cli_env, "drive", "get", "NOPE")
    assert rc != 0 and "error" in err.lower()


def test_cli_docs_get_error(cli_env):
    rc, _, err = run_cli(cli_env, "docs", "get", "NOPE")
    assert rc != 0


def test_cli_calendar_get_error(cli_env):
    rc, _, err = run_cli(cli_env, "calendar", "get", "NOPE")
    assert rc != 0


def test_cli_calendar_create_error(cli_env):
    """Missing required option -> Typer usage error (non-zero exit)."""
    rc, _, _ = run_cli(cli_env, "calendar", "create", "-s", "x")  # no --start/--end
    assert rc != 0


def test_cli_gmail_get_error(cli_env):
    rc, _, _ = run_cli(cli_env, "gmail", "get", "NOPE")
    assert rc != 0
