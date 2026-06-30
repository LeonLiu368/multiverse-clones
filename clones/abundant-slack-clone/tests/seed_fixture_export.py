"""Write the deterministic test fixture as a Slack export directory.

Mirrors conftest._seed exactly, but as the on-disk Slack-export format the gateway's importer
(import_export.py) ingests — so a booted `slack-gateway:empty` container, given this export, holds
byte-identical data to the in-process conftest gateway. Used by tests/test.sh in docker mode.

Usage:  python3 seed_fixture_export.py <out_dir>
"""
from __future__ import annotations

import json
import os
import sys

# Keep these in lockstep with tests/conftest.py.
TEAM_ID = "T0TESTTEAM0"
TEAM_NAME = "testworkspace"
CH_GENERAL = "C0000000001"
CH_ENG = "C0000000002"
U_ALICE = "U0000000A01"
U_BOB = "U0000000B02"
THREAD_TS = "1700000100.000000"
SEARCH_PHRASE = "ZEBRAFISH"


def main(out: str) -> None:
    os.makedirs(out, exist_ok=True)
    channels = [
        {"id": CH_GENERAL, "name": "general", "is_general": True, "creator": U_ALICE,
         "created": 1700000000, "topic": {"value": "company-wide"},
         "purpose": {"value": "announcements"}, "members": [U_ALICE, U_BOB]},
        {"id": CH_ENG, "name": "engineering", "creator": U_BOB, "created": 1700000000,
         "topic": {"value": "eng chatter"}, "purpose": {"value": "builds and incidents"},
         "members": [U_ALICE, U_BOB]},
    ]
    users = [
        {"id": U_ALICE, "name": "alice", "real_name": "Alice Ant", "team_id": TEAM_ID,
         "profile": {"real_name": "Alice Ant", "email": "alice@test.dev"}},
        {"id": U_BOB, "name": "bob", "real_name": "Bob Bee", "team_id": TEAM_ID,
         "profile": {"real_name": "Bob Bee", "email": "bob@test.dev"}},
    ]
    with open(os.path.join(out, "channels.json"), "w") as fh:
        json.dump(channels, fh)
    with open(os.path.join(out, "users.json"), "w") as fh:
        json.dump(users, fh)

    general_msgs = [
        {"type": "message", "ts": "1700000001.000000", "user": U_ALICE,
         "text": "welcome to the workspace"},
        {"type": "message", "ts": "1700000002.000000", "user": U_BOB,
         "text": f"secret marker {SEARCH_PHRASE} lives here"},
    ]
    eng_msgs = [
        {"type": "message", "ts": THREAD_TS, "user": U_ALICE,
         "text": "deploy thread: starting rollout", "thread_ts": THREAD_TS, "reply_count": 2},
        {"type": "message", "ts": "1700000101.000000", "user": U_BOB,
         "text": "canary looks healthy", "thread_ts": THREAD_TS},
        {"type": "message", "ts": "1700000102.000000", "user": U_ALICE,
         "text": "rollout complete", "thread_ts": THREAD_TS},
    ]
    os.makedirs(os.path.join(out, "general"), exist_ok=True)
    os.makedirs(os.path.join(out, "engineering"), exist_ok=True)
    with open(os.path.join(out, "general", "2023-11-14.json"), "w") as fh:
        json.dump(general_msgs, fh)
    with open(os.path.join(out, "engineering", "2023-11-14.json"), "w") as fh:
        json.dump(eng_msgs, fh)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "slack-export")
