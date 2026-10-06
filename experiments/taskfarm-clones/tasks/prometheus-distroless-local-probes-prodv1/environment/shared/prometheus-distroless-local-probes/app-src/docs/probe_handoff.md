# Probe Handoff

Issue 8605 is not a timeout problem. The kubelet is failing before Prometheus receives the request because the probe command starts with `sh`, and the distroless image has no shell.

Near misses:

- `prom-legacy-shell` still has `listenLocal: true`, but its image can run the existing exec probe.
- `prom-public-metrics` is distroless, but its listener is not local-only and it already uses `httpGet`.
