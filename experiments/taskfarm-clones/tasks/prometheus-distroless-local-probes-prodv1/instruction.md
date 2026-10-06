The 18:03 UTC Prometheus readiness page is yours. After the kube-prometheus-stack image default moved to a distroless Prometheus image, two `listenLocal: true` Prometheus workloads started failing kubelet probes because the rendered probe still shells out through `sh -c` and tries `curl` or `wget`.

Work from `/app/src`. The local repository models the Prometheus Operator probe renderer and includes an inventory in `ops/prometheus_instances.yaml`. Runtime evidence is spread across Postgres, the local GitHub clone, k3s, and the Grafana dashboard. Ticket `PROMOP-8605` is the handoff record.

The affected instances are `prom-ceems-primary` and `prom-edge-rules`. `prom-legacy-shell` is a near miss because it still uses a shell-capable image, and `prom-public-metrics` is a near miss because `listenLocal` is false. Do not solve this by rolling every Prometheus workload back to a non-distroless image, changing all probes in the fleet, or marking the near misses repaired.

Patch the renderer so only distroless `listenLocal` instances stop emitting shell-based exec probes. Then run the local repair builder so it writes `/app/artifacts/prometheus_distroless_probe_repair.json` and applies the scoped database repair.

The JSON artifact must use this schema:

```json
{
  "ticket_id": "PROMOP-8605",
  "incident_id": "distroless-listenlocal-probes",
  "affected_instances": [
    {
      "instance_id": "prom-ceems-primary",
      "namespace": "ceems",
      "before_kind": "exec",
      "after_kind": "httpGet",
      "probe_path": "/-/ready",
      "evidence": ["kubelet log or inventory evidence"]
    }
  ],
  "untouched_instances": ["prom-legacy-shell", "prom-public-metrics"],
  "broad_workaround_rejected": "short explanation",
  "scope_note": "short explanation"
}
```

When the repair is complete, move `PROMOP-8605` to `In Review` and add a comment that names the artifact, both repaired instances, both untouched near misses, and why this was a narrow renderer fix rather than a broad rollback or fleet rewrite.
