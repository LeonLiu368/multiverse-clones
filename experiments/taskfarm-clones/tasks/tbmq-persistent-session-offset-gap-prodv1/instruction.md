The TBMQ persistent-session page is yours.

Customer traffic from the ReSENSE MQTT feed is still missing offline-window messages after reconnect. The captured issue matches the public TBMQ report: `mqtt_gap` is an APPLICATION client, clean session is false, QoS 1 messages were persisted to the per-client Kafka topic, lag rose while the client was offline, and then the broker committed past offsets that were never built into a delivery pack.

The sharpest capture is on `tbmq1`/`tbmq2`: packet `2708` at offset `3215` was retried, then the next built pack started at packet `2709` with offsets `3263-3272`. Offsets `3216-3262` were skipped. A ThingsBoard Edge integration has the same replay-shape failure in the local evidence. There are also duplicate PUBACK/DUP=0 warnings in the same window, but do not turn this into a global replay or DUP-flag cleanup unless the scoped offset evidence requires it.

Work in `/app/src`. The miniature repo has the replay planner under `src/` and the operator tool under `tools/`. Postgres has the captured gap rows and operational audit tables. Ticket `TBMQ-320` has the on-call handoff. Slack and Grafana contain supporting evidence and noise from the same morning.

When you are done, run the replay planner so it writes:

`/app/artifacts/tbmq_persistent_session_replay_plan.json`

That JSON is the handoff artifact. It must use this schema:

```json
{
  "incident_id": "TBMQ-320",
  "source_issue": "thingsboard/tbmq#320",
  "generated_by": "tbmq persistent session replay planner",
  "actions": [
    {
      "gap_id": "mqtt_gap_3216_3262",
      "client_id": "mqtt_gap",
      "action": "replay_missing_offsets_before_commit",
      "missing_offsets": {"start": 3216, "end": 3262},
      "packet_window": {"retry_packet": 2708, "next_packet_start": 2709, "next_packet_end": 2718},
      "commit_guard": "commit only after delivery ack",
      "broad_replay": false
    }
  ],
  "untouched_decoys": [
    {"gap_id": "mqtt_gap_packet_2708_dup0_followup", "reason": "duplicate PUBACK/DUP flag symptom is not this replay repair"}
  ]
}
```

The `actions` array should name only the two true replay gaps: `mqtt_gap_3216_3262` and `edge_bridge_8801_8817`. Leave `mqtt_gap_packet_2708_dup0_followup` and `sensor_qos0_snapshot_noise` out of the repair plan. Update `TBMQ-320` to `In Review` with a comment that mentions the artifact path, both repaired gap ids, at least one untouched decoy, and why this is a narrow replay repair rather than a broad consumer reset.
