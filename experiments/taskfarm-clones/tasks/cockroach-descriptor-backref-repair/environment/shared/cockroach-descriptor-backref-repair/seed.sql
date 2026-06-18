CREATE TABLE descriptor_incidents (
  ticket_id text PRIMARY KEY,
  sentry_event text NOT NULL,
  status text NOT NULL,
  summary text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE descriptor_backrefs (
  relation_id integer PRIMARY KEY,
  relation_name text NOT NULL,
  descriptor_kind text NOT NULL,
  relation_state text NOT NULL,
  referenced_descriptor_id integer NOT NULL,
  referenced_exists boolean NOT NULL,
  stack_key text NOT NULL,
  first_seen timestamptz NOT NULL,
  repair_action text NOT NULL DEFAULT 'pending',
  repair_status text NOT NULL DEFAULT 'unreviewed',
  repair_note text NOT NULL DEFAULT ''
);

CREATE TABLE descriptor_repair_audit (
  id bigserial PRIMARY KEY,
  relation_id integer NOT NULL,
  action text NOT NULL,
  artifact_path text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE validation_event_noise (
  id text PRIMARY KEY,
  component text NOT NULL,
  message text NOT NULL,
  observed_at timestamptz NOT NULL
);

INSERT INTO descriptor_incidents (ticket_id, sentry_event, status, summary, updated_at) VALUES
  ('CRDB-63963', 'evt-crdb-170371', 'investigating', 'validate.go:358 panic while unsafe_upsert_descriptor reads relation descriptors with missing depended-on-by targets', '2026-05-21T11:36:27Z');

INSERT INTO descriptor_backrefs (relation_id, relation_name, descriptor_kind, relation_state, referenced_descriptor_id, referenced_exists, stack_key, first_seen) VALUES
  (193, 'tenant_usage_by_hour', 'relation', 'public', 400, false, 'sql.schema.validation_errors.read.backward_references.relation', '2026-05-21T10:54:22Z'),
  (211, 'rangefeed_checkpoint_rollup', 'relation', 'public', 417, false, 'sql.schema.validation_errors.read.backward_references.relation', '2026-05-21T11:02:49Z'),
  (244, 'statement_diagnostics_live', 'relation', 'public', 612, true, 'sql.schema.validation_errors.read.backward_references.relation', '2026-05-21T10:59:00Z'),
  (305, 'old_mvcc_statistics_shadow', 'relation', 'dropped', 731, false, 'sql.schema.validation_errors.read.backward_references.relation', '2026-05-20T23:12:00Z'),
  (318, 'descriptor_lease_table', 'relation', 'public', 819, false, 'sql.schema.validation_errors.write.forward_references.sequence', '2026-05-21T09:44:00Z'),
  (327, 'sql_stats_persisted_by_fingerprint', 'relation', 'public', 902, true, 'sql.schema.validation_errors.read.backward_references.relation', '2026-05-21T08:10:00Z');

INSERT INTO validation_event_noise (id, component, message, observed_at) VALUES
  ('evt-crdb-leaseholder-noise', 'kvserver', 'range lease transfer retry exceeded soft limit', '2026-05-21T10:41:00Z'),
  ('evt-crdb-backup-noise', 'backupccl', 'scheduled backup completed with slow span scan warning', '2026-05-21T10:48:00Z'),
  ('evt-crdb-schema-forward-ref', 'sql.schema', 'forward reference warning on descriptor_lease_table; tracked separately', '2026-05-21T09:44:00Z');
