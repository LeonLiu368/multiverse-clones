#!/usr/bin/env python3
"""Build the multi-hop fixture for gws-launch-multihop.

Two-hop by construction:
  1) Gmail resolves WHICH launch is authoritative (a thread whose FINAL message
     names the 'Atlas Launch — GA' calendar event — but carries NO date).
  2) Calendar resolves the DATE of that event (2026-10-06).

Shortcuts are defused:
  * The Gmail thread contains an earlier message proposing 2026-09-10; only the
    later (higher internalDate) message from the release manager is authoritative
    — and it overrides to the GA event, so "grep the email for a date" gets the
    wrong one or none.
  * The Calendar holds several Atlas events (tentative 09-10, cancelled 09-22, GA
    10-06) plus other-project launches — so "grab the first launch event" fails.
Only chaining email→calendar yields 2026-10-06.
"""
import json
import pathlib

from gwsclone.seed import schema as S

ANSWER = "2026-10-06"

seed = {
    "calendar": [
        S.event("EVT_ATLAS_GA", "Atlas Launch — GA",
                "2026-10-06T09:00:00-07:00", "2026-10-06T11:00:00-07:00",
                description="General availability launch for Project Atlas.",
                location="Launch War Room", status="confirmed",
                organizer={"email": "mira@acme.example", "displayName": "Mira Devon"}),
        S.event("EVT_ATLAS_TENT", "Atlas Launch (tentative)",
                "2026-09-10T09:00:00-07:00", "2026-09-10T10:00:00-07:00",
                description="Tentative early target — superseded.", status="tentative"),
        S.event("EVT_ATLAS_OLD", "Atlas Launch (old date — do not use)",
                "2026-09-22T09:00:00-07:00", "2026-09-22T10:00:00-07:00",
                description="Slipped; cancelled.", status="cancelled"),
        # other-project launch decoys
        S.event("EVT_BEACON", "Beacon Launch", "2026-08-15T09:00:00-07:00",
                description="Different project."),
        S.event("EVT_COMET", "Comet GA", "2026-11-30T09:00:00-07:00",
                description="Different project."),
        # generic clutter
        S.event("EVT_STANDUP", "Eng Standup", "2026-09-01T16:30:00-07:00"),
        S.event("EVT_ALLHANDS", "Q3 All-Hands", "2026-09-18T10:00:00-07:00"),
    ],
    "gmail": [
        # the resolving thread (chronological by internalDate)
        S.message("MSG_A1", "Atlas launch date",
                  "Team — what's our ship date for Atlas? I see a few calendar holds.",
                  frm="pm@acme.example", to="launch@acme.example",
                  thread_id="T_ATLAS", internal_date="1758600000000",
                  labels=["INBOX"]),
        S.message("MSG_A2", "Re: Atlas launch date",
                  "Let's pencil in Sept 10 for now (the tentative hold).",
                  frm="dev@acme.example", to="launch@acme.example",
                  thread_id="T_ATLAS", internal_date="1758700000000",
                  labels=["INBOX"]),
        S.message("MSG_A3", "Re: Atlas launch date",
                  "Final call from release management: we are shipping on the "
                  "'Atlas Launch — GA' calendar event. Please ignore the tentative "
                  "and the old/slipped holds. That GA event is the source of truth.",
                  frm="mira@acme.example", to="launch@acme.example",
                  thread_id="T_ATLAS", internal_date="1758900000000",
                  labels=["INBOX", "IMPORTANT"]),
        # decoy unrelated threads
        S.message("MSG_B1", "Beacon launch is Aug 15",
                  "Reminder: Beacon ships Aug 15.", frm="pm@acme.example",
                  to="launch@acme.example", thread_id="T_BEACON",
                  internal_date="1755000000000"),
        S.message("MSG_C1", "Lunch?", "Anyone up for lunch today?",
                  frm="dev@acme.example", to="pm@acme.example",
                  thread_id="T_LUNCH", internal_date="1758950000000"),
    ],
}

if __name__ == "__main__":
    out = pathlib.Path(__file__).parent / "environment" / "data" / "gws" / "fixture.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(S.normalize(seed), indent=2))
    print(f"wrote {out} (answer={ANSWER})")
