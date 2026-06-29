# Creating Tasks With Gauge

Use Gauge when the agent should need observability evidence without access to real Grafana or live telemetry systems.

## Compose Pattern

Mount task state only into the Gauge sidecar:

```yaml
gauge:
  image: ghcr.io/abundant-ai/gauge-service:<tag>@sha256:<digest>
  hostname: gauge
  environment:
    GAUGE_STATE_FILE: /data/gauge/state.json
    GAUGE_RUNTIME_STATE_FILE: /var/lib/gauge/state.json
    GAUGE_ENABLE_ADMIN_API: "1"
    GAUGE_ADMIN_TOKEN: ${GAUGE_ADMIN_TOKEN}
    GRAFANA_SERVICE_ACCOUNT_TOKEN: test-token-acme-eval
  volumes:
    - ./data/gauge/state.json:/data/gauge/state.json:ro
    - gauge-runtime:/var/lib/gauge
```

Copy only agent tools into the agent image:

```dockerfile
FROM ghcr.io/abundant-ai/gauge-service:<tag>@sha256:<digest> AS gauge-tools
COPY --from=gauge-tools /usr/local/bin/gcx /usr/local/bin/mcp-grafana /usr/local/bin/
COPY --from=gauge-tools /opt/gaugecli /opt/gaugecli
ENV PYTHONPATH=/opt/gaugecli
ENV GRAFANA_URL=http://gauge
```

Pass `GRAFANA_TOKEN` and `GRAFANA_SERVICE_ACCOUNT_TOKEN` to the agent at runtime through the task environment. Do not bake token values into the agent image unless the task pack already follows that convention for local test credentials.

Do not mount `data/gauge/state.json` into the agent container. Do not copy `gaugectl` or pass `GAUGE_ADMIN_TOKEN` to the agent container.

## Authoring Evidence

Good tasks make Grafana evidence necessary but not answer-leaking:

- Put the symptom or alert name in the issue or chat context.
- Seed dashboards and alerts that point to the right service area.
- Include metric and log fixtures that confirm the root cause.
- Include distractor dashboards, normal alerts, and superseded log clues when useful.
- Require the final answer to cite evidence discovered through `gcx` or `mcp-grafana`.
- Use annotations as an observable side effect when the workflow should leave an investigation note.
- Use alert instances/history to make "is it still firing?" and "when did this change?" workflows realistic.
- Use dashboard variables and panel-query execution when agents should inspect dashboard structure before querying.

Verifiers should inspect outcomes through admin endpoints or service APIs, not by giving agents direct access to raw seed files.
