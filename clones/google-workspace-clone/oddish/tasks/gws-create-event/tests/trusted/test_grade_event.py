"""HIDDEN grader — reads the calendar back THROUGH THE API to confirm the agent's
WRITE (events.insert). Passes iff a 'Q3 Retro' event exists starting 2026-10-06T14:00
UTC (the CONFIRMED ask), and NOT the superseded DRAFT (Oct 3, 10:00). This is the
write->read round-trip: the agent must have created it for this to pass (R5.2)."""
import os
import subprocess
import json


def _events(query):
    env = dict(os.environ)
    env.setdefault("GWS_API_URL", "http://gworkspace:8080")
    env.setdefault("GWS_TOKEN", "gws-clone-token")
    out = subprocess.run(["gws-cli", "calendar", "events", "-q", query],
                         capture_output=True, text=True, env=env)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)["items"]


def _start(e):
    s = e.get("start", {})
    return s.get("dateTime") or s.get("date") or ""


def test_event_created_via_api():
    items = _events("Q3 Retro")
    retros = [e for e in items if e.get("summary") == "Q3 Retro"]
    assert retros, "no 'Q3 Retro' event on the calendar — the agent did not create it"
    # the confirmed start; the superseded draft (Oct 3, 10:00) must NOT be what was booked
    starts = [_start(e) for e in retros]
    assert any(s.startswith("2026-10-06T14:00") for s in starts), \
        f"'Q3 Retro' not at the confirmed time; got {starts}"
    assert not any(s.startswith("2026-10-03") for s in starts), \
        "booked the superseded DRAFT date (Oct 3) — should be the confirmed Oct 6"
