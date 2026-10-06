import json
import subprocess
from pathlib import Path


ARTIFACT = Path("/app/artifacts/tbmq_persistent_session_replay_plan.json")
EXPECTED = {
    "mqtt_gap_3216_3262": (3216, 3262),
    "edge_bridge_8801_8817": (8801, 8817),
}
DECOYS = {"mqtt_gap_packet_2708_dup0_followup", "sensor_qos0_snapshot_noise"}


assert ARTIFACT.is_file(), f"missing artifact {ARTIFACT}"
plan = json.loads(ARTIFACT.read_text())
assert plan.get("incident_id") == "TBMQ-320", plan
assert plan.get("source_issue") == "thingsboard/tbmq#320", plan
actions = {item.get("gap_id"): item for item in plan.get("actions", [])}
assert set(actions) == set(EXPECTED), actions

for gap_id, (start, end) in EXPECTED.items():
    action = actions[gap_id]
    assert action.get("action") == "replay_missing_offsets_before_commit", action
    assert action.get("missing_offsets") == {"start": start, "end": end}, action
    assert action.get("commit_guard") == "commit only after delivery ack", action
    assert action.get("broad_replay") is False, action

untouched = {item.get("gap_id") for item in plan.get("untouched_decoys", [])}
assert DECOYS <= untouched, untouched


def psql(sql):
    result = subprocess.run(
        ["psql", "-v", "ON_ERROR_STOP=1", "-At", "-c", sql],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


repaired = set(filter(None, psql("SELECT gap_id FROM incident_session_gaps WHERE status='replay_planned' ORDER BY gap_id;").splitlines()))
assert repaired == set(EXPECTED), repaired

decoy_status = dict(
    line.split("|", 1)
    for line in filter(None, psql("SELECT gap_id,status FROM incident_session_gaps WHERE gap_id IN ('mqtt_gap_packet_2708_dup0_followup','sensor_qos0_snapshot_noise') ORDER BY gap_id;").splitlines())
)
assert decoy_status == {
    "mqtt_gap_packet_2708_dup0_followup": "watch_only",
    "sensor_qos0_snapshot_noise": "watch_only",
}, decoy_status

audit = set(filter(None, psql("SELECT gap_id || '|' || offset_span || '|' || artifact_path FROM session_repair_audit ORDER BY gap_id;").splitlines()))
assert audit == {
    "edge_bridge_8801_8817|8801-8817|/app/artifacts/tbmq_persistent_session_replay_plan.json",
    "mqtt_gap_3216_3262|3216-3262|/app/artifacts/tbmq_persistent_session_replay_plan.json",
}, audit

status = psql("SELECT status FROM incident_status WHERE ticket_id='TBMQ-320';")
assert status == "replay_plan_ready", status
print("artifact and db ok")
