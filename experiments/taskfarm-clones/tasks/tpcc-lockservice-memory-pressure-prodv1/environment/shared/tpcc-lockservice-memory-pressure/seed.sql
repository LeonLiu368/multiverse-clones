create table tpcc_profile_evidence (
  profile_id text primary key,
  warehouses integer not null,
  terminals integer not null,
  passed_before_failure boolean not null,
  current_memory_limit_gib integer not null,
  current_rpc_timeout_ms integer not null,
  current_action text not null
);

insert into tpcc_profile_evidence values
  ('tpcc_10w_10t', 10, 10, true, 55, 30000, 'leave'),
  ('tpcc_10w_100t', 10, 100, true, 55, 30000, 'leave'),
  ('tpcc_100w_100t', 100, 100, true, 55, 30000, 'leave'),
  ('tpcc_100w_1000t', 100, 1000, true, 55, 30000, 'leave'),
  ('tpcc_1000w_1000t', 1000, 1000, false, 55, 30000, 'needs_scoped_repair'),
  ('ivf_vector_index', 0, 0, false, 55, 30000, 'leave');

create table cn_runtime_observations (
  observation_id text primary key,
  observed_at timestamptz not null,
  namespace text not null,
  pod text not null,
  backend text not null,
  memory_observed_gib numeric not null,
  memory_limit_gib numeric not null,
  restart_count integer not null,
  oomkilled_in_window boolean not null,
  note text not null
);

insert into cn_runtime_observations values
  ('obs_tpcc_target_cn', '2026-06-08T18:44:18Z', 'mo-branch-commit-7a8e7cd84-20260608', 'nightly-regression-dis-tp-cn-phqxp', '10.143.26.143:6003', 54.47, 55, 0, false, 'lockservice remote lock RPC timeout during TPCC 1000W/1000T'),
  ('obs_neighbor_cn', '2026-06-08T18:46:00Z', 'mo-branch-commit-7a8e7cd84-20260608', 'nightly-regression-dis-tp-cn-wkq2r', '10.143.26.144:6003', 31.2, 55, 0, false, 'healthy neighboring CN'),
  ('obs_later_ivf', '2026-06-08T23:49:00Z', 'mo-branch-commit-7a8e7cd84-20260608', 'ivf-vector-index-worker-0', 'n/a', 55, 55, 1, true, 'later IVF OOMKilled noise, not TPCC root cause');

create table incident_status (
  ticket text primary key,
  status text not null,
  root_cause text not null,
  repaired_profiles text not null default '',
  updated_at timestamptz not null
);

insert into incident_status(ticket, status, root_cause, repaired_profiles, updated_at)
values ('MO-24893', 'investigating', 'unconfirmed; do not conflate later IVF OOMKilled with TPCC failure', '', '2026-06-11T03:51:11Z');

create table repair_audit (
  id bigserial primary key,
  ticket text not null,
  profile_id text not null,
  target_cn text not null,
  evidence_window_start timestamptz not null,
  evidence_window_end timestamptz not null,
  action text not null,
  artifact_path text not null,
  created_at timestamptz not null default now()
);
