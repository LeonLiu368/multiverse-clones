CREATE TABLE probe_inventory (
  instance_id text PRIMARY KEY,
  namespace text NOT NULL,
  listen_local boolean NOT NULL,
  image_flavor text NOT NULL,
  current_probe_kind text NOT NULL,
  desired_probe_kind text NOT NULL,
  repair_action text NOT NULL,
  ticket text NOT NULL,
  kubelet_excerpt text NOT NULL
);

CREATE TABLE incident_status (
  ticket text PRIMARY KEY,
  status text NOT NULL,
  repaired_ids text NOT NULL DEFAULT '',
  artifact text NOT NULL DEFAULT '',
  broad_workaround text NOT NULL
);

CREATE TABLE repair_audit (
  id bigserial PRIMARY KEY,
  record_id text NOT NULL,
  action text NOT NULL,
  artifact text NOT NULL,
  note text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE probe_noise (
  noise_id text PRIMARY KEY,
  summary text NOT NULL,
  ticket text NOT NULL,
  authoritative boolean NOT NULL
);

INSERT INTO probe_inventory(instance_id, namespace, listen_local, image_flavor, current_probe_kind, desired_probe_kind, repair_action, ticket, kubelet_excerpt) VALUES
('prom-ceems-primary', 'ceems', true, 'distroless', 'exec', 'httpGet', 'pending', 'PROMOP-8605', 'exec failed: unable to start container process: exec: "sh": executable file not found in PATH'),
('prom-edge-rules', 'edge', true, 'distroless', 'exec', 'httpGet', 'pending', 'PROMOP-8605', 'startup probe repeats OCI runtime exec failure for sh'),
('prom-legacy-shell', 'ceems', true, 'full', 'exec', 'exec', 'leave', 'PROMOP-8605', 'same listenLocal path but shell and wget are present'),
('prom-public-metrics', 'monitoring', false, 'distroless', 'httpGet', 'httpGet', 'leave', 'PROMOP-8612', 'distroless image without local-only listener already uses httpGet'),
('prom-remote-write-lag', 'telemetry', false, 'full', 'httpGet', 'httpGet', 'leave', 'PROMOP-8441', 'remote write lag recovered before probe incident');

INSERT INTO incident_status(ticket, status, broad_workaround) VALUES
('PROMOP-8605', 'active', 'rollback all distroless images or rewrite every Prometheus probe'),
('PROMOP-8441', 'closed', 'increase probe timeout for slow starts'),
('PROMOP-8612', 'triage', 'public listener cleanup');

INSERT INTO probe_noise(noise_id, summary, ticket, authoritative) VALUES
('stale-timeout-pr', 'Timeout tuning branch opened before the distroless shell evidence arrived', 'PROMOP-8441', false),
('operator-restart-note', 'Restarting the operator clears no kubelet exec failures', 'PROMOP-8605', false),
('public-listener-case', 'A distroless public listener has a similar image but not the listenLocal failure', 'PROMOP-8612', true);
