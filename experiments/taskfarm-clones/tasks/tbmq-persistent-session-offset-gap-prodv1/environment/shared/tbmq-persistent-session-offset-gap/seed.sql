CREATE TABLE incident_session_gaps (
  gap_id text PRIMARY KEY,
  client_id text NOT NULL,
  client_type text NOT NULL,
  clean_session boolean NOT NULL,
  qos integer NOT NULL,
  topic text NOT NULL,
  broker_node text NOT NULL,
  fanout_node text NOT NULL,
  retry_packet integer NOT NULL,
  retry_offset integer NOT NULL,
  next_packet_start integer NOT NULL,
  next_packet_end integer NOT NULL,
  next_offset_start integer NOT NULL,
  next_offset_end integer NOT NULL,
  consumer_lag_before_reconnect integer NOT NULL,
  records_confirmed boolean NOT NULL,
  status text NOT NULL,
  candidate_action text NOT NULL DEFAULT 'unreviewed',
  untouched_reason text,
  updated_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE TABLE session_repair_audit (
  audit_id bigserial PRIMARY KEY,
  gap_id text NOT NULL REFERENCES incident_session_gaps(gap_id),
  action text NOT NULL,
  offset_span text NOT NULL,
  artifact_path text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE TABLE incident_status (
  ticket_id text PRIMARY KEY,
  status text NOT NULL,
  summary text NOT NULL,
  repaired_gap_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT NOW()
);

INSERT INTO incident_session_gaps (
  gap_id, client_id, client_type, clean_session, qos, topic, broker_node, fanout_node,
  retry_packet, retry_offset, next_packet_start, next_packet_end, next_offset_start,
  next_offset_end, consumer_lag_before_reconnect, records_confirmed, status, untouched_reason
) VALUES
  ('mqtt_gap_3216_3262', 'mqtt_gap', 'APPLICATION', false, 1, 'tbmq.msg.app.reSENSE.telemetry', 'tbmq1', 'tbmq2', 2708, 3215, 2709, 2718, 3263, 3272, 58, true, 'needs_replay_plan', NULL),
  ('edge_bridge_8801_8817', 'edge_bridge_west', 'APPLICATION', false, 1, 'tbmq.msg.app.edge.integration.telemetry', 'tbmq2', 'tbmq1', 4112, 8800, 4113, 4119, 8818, 8824, 24, true, 'needs_replay_plan', NULL),
  ('mqtt_gap_packet_2708_dup0_followup', 'mqtt_gap', 'APPLICATION', false, 1, 'tbmq.msg.app.reSENSE.telemetry', 'tbmq1', 'tbmq2', 2708, 3215, 2708, 2708, 3215, 3215, 0, false, 'watch_only', 'Duplicate PUBACK/DUP flag symptom; not a committed-over replay gap.'),
  ('sensor_qos0_snapshot_noise', 'sensor_qos0_snapshot', 'DEVICE', true, 0, 'tbmq.msg.device.snapshot', 'tbmq2', 'tbmq2', 188, 6042, 189, 192, 6043, 6046, 0, false, 'watch_only', 'QoS0 clean-session device snapshot has no persistent replay contract.'),
  ('mobile_clean_session_gap_noise', 'mobile_clean_a', 'APPLICATION', true, 1, 'tbmq.msg.app.mobile.telemetry', 'tbmq1', 'tbmq1', 901, 12040, 902, 908, 12041, 12047, 0, false, 'watch_only', 'Clean-session reconnect is intentionally not persisted.');

INSERT INTO incident_status (ticket_id, status, summary) VALUES
  ('TBMQ-320', 'investigating', 'Persistent APPLICATION clients skip Kafka offsets after reconnect.'),
  ('TBMQ-144', 'closed', 'Historical shared subscription PubAck warning, not part of current replay repair.'),
  ('TBMQ-287', 'watching', 'QoS0 device snapshot loss expected under clean-session behavior.');
