CREATE TABLE loki_index_path_status (
  pod_id text PRIMARY KEY,
  component text NOT NULL,
  ticket text NOT NULL,
  needs_repair boolean NOT NULL,
  current_state text NOT NULL,
  active_index_directory text NOT NULL,
  cache_location text NOT NULL,
  repaired boolean NOT NULL DEFAULT false
);

CREATE TABLE incident_status (
  ticket text PRIMARY KEY,
  status text NOT NULL,
  repaired_pods text NOT NULL DEFAULT ''
);

CREATE TABLE repair_audit (
  ticket text NOT NULL,
  pod_id text NOT NULL,
  active_index_directory text NOT NULL,
  cache_location text NOT NULL,
  repaired_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (ticket, pod_id)
);

INSERT INTO loki_index_path_status (pod_id, component, ticket, needs_repair, current_state, active_index_directory, cache_location, repaired) VALUES
('loki-write-2', 'write', 'LOKI-3248', true, 'crashlooping', '/data/loki/boltdb-shipper-active', '/data/loki/boltdb-shipper-cache', false),
('loki-write-5', 'write', 'LOKI-3248', true, 'crashlooping', '/data/loki/boltdb-shipper-active', '/data/loki/boltdb-shipper-cache', false),
('loki-compactor-0', 'compactor', 'LOKI-3201', false, 'running', '/data/loki/boltdb-shipper-compactor', '/data/loki/boltdb-shipper-cache', false),
('loki-read-1', 'read', 'LOKI-3104', false, 'running', '/data/loki/boltdb-shipper-read', '/data/loki/boltdb-shipper-cache-read', false);

INSERT INTO incident_status (ticket, status, repaired_pods) VALUES
('LOKI-3248', 'active', ''),
('LOKI-3219', 'closed', '');
