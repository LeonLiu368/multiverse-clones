CREATE TABLE descriptor_validation_cases (
  case_id TEXT PRIMARY KEY,
  ticket TEXT NOT NULL,
  tenant TEXT NOT NULL,
  table_name TEXT NOT NULL,
  schema_change TEXT NOT NULL,
  partition_tuple_hex TEXT NOT NULL,
  tuple_arity INTEGER NOT NULL,
  observed_error TEXT NOT NULL,
  guard_state TEXT NOT NULL,
  expected_action TEXT NOT NULL,
  captured_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE incident_status (
  ticket TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  repaired_ids TEXT NOT NULL DEFAULT '',
  artifact TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE repair_audit (
  record_id TEXT PRIMARY KEY,
  ticket TEXT NOT NULL,
  action TEXT NOT NULL,
  artifact TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO descriptor_validation_cases VALUES
('tenant_31_orders_pk_swap','CRDB-63642','tenant-31','orders','ALTER PRIMARY KEY USING COLUMNS (region, id)','',2,'slice bounds out of range [2:0]','pending','guard_empty_tuple_decode','2026-05-21T14:48:10Z'),
('tenant_42_events_pk_swap','CRDB-63642','tenant-42','events','ALTER PRIMARY KEY USING COLUMNS (bucket, event_id)','',2,'slice bounds out of range [2:0]','pending','guard_empty_tuple_decode','2026-05-21T14:51:42Z'),
('tenant_77_geo_archive_intentional_empty','CRDB-63590','tenant-77','geo_archive','ALTER PARTITION BY LIST ()','',0,'none','leave','leave_intentional_empty_list','2026-05-21T14:37:00Z'),
('tenant_18_inventory_hash_shard','CRDB-63512','tenant-18','inventory','ALTER PRIMARY KEY USING HASH WITH BUCKET_COUNT = 8','0x1204',2,'none','leave','leave_valid_tuple','2026-05-21T13:22:00Z'),
('tenant_65_customers_expr_index','CRDB-63441','tenant-65','customers','CREATE INDEX ON lower(email)','0x0f',1,'validator warning only','leave','leave_expr_index_noise','2026-05-21T12:16:00Z');

INSERT INTO incident_status(ticket, status, repaired_ids, artifact, updated_at)
VALUES ('CRDB-63642', 'open', '', '', '2026-05-21T15:02:00Z');
