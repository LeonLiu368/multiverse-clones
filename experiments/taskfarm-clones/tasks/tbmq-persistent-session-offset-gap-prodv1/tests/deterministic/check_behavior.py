import json
import subprocess
import tempfile
from pathlib import Path


def run_planner(fixture):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fixture_path = tmp_path / "fixture.json"
        out_path = tmp_path / "plan.json"
        fixture_path.write_text(json.dumps(fixture))
        subprocess.run(
            ["nodejs", "tools/replayPersistentSession.js", "--fixture", str(fixture_path), "--out", str(out_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return json.loads(out_path.read_text())


fixture = {
    "incident_id": "TBMQ-320",
    "source_issue": "thingsboard/tbmq#320",
    "captures": [
        {
            "gap_id": "probe_gap_1001_1047",
            "client_id": "probe_app",
            "client_type": "APPLICATION",
            "clean_session": False,
            "qos": 1,
            "retry_packet": {"packet_id": 77, "offset": 1000, "is_dup": False},
            "next_pack": {"packet_start": 78, "packet_end": 84, "offset_start": 1048, "offset_end": 1054},
            "consumer_group": {"lag_before_reconnect": 52, "records_confirmed": True},
        },
        {
            "gap_id": "probe_dup_ack_only",
            "client_id": "probe_app",
            "client_type": "APPLICATION",
            "clean_session": False,
            "qos": 1,
            "retry_packet": {"packet_id": 77, "offset": 1000, "is_dup": False},
            "next_pack": {"packet_start": 77, "packet_end": 77, "offset_start": 1000, "offset_end": 1000},
            "consumer_group": {"lag_before_reconnect": 0, "records_confirmed": False},
            "untouched_reason": "duplicate PubAck only",
        },
    ],
}

plan = run_planner(fixture)
actions = {item["gap_id"]: item for item in plan["actions"]}
assert set(actions) == {"probe_gap_1001_1047"}, plan
assert actions["probe_gap_1001_1047"]["missing_offsets"] == {"start": 1001, "end": 1047}, actions
assert actions["probe_gap_1001_1047"]["broad_replay"] is False, actions
assert any(item["gap_id"] == "probe_dup_ack_only" for item in plan["untouched_decoys"]), plan
print("behavior ok")
