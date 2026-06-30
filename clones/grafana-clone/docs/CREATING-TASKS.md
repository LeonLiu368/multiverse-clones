# Creating Tasks With Grafana

Use Grafana when the agent should need observability evidence without access to real Grafana or live telemetry systems.

## Compose Pattern

Mount task state only into the Grafana sidecar:

```yaml
grafana:
  image: ghcr.io/abundant-ai/grafana-service:<tag>@sha256:<digest>
  hostname: grafana
  environment:
    GRAFANA_STATE_FILE: /data/grafana/state.json
    GRAFANA_RUNTIME_STATE_FILE: /var/lib/grafana/state.json
    GRAFANA_ENABLE_ADMIN_API: "1"
    GRAFANA_ADMIN_TOKEN: ${GRAFANA_ADMIN_TOKEN}
    GRAFANA_SERVICE_ACCOUNT_TOKEN: test-token-acme-eval
  volumes:
    - ./data/grafana/state.json:/data/grafana/state.json:ro
    - grafana-runtime:/var/lib/grafana
```

Copy only agent tools into the agent image:

```dockerfile
FROM ghcr.io/abundant-ai/grafana-service:<tag>@sha256:<digest> AS grafana-tools
COPY --from=grafana-tools /usr/local/bin/gcx /usr/local/bin/mcp-grafana /usr/local/bin/
COPY --from=grafana-tools /opt/grafanacli /opt/grafanacli
ENV PYTHONPATH=/opt/grafanacli
ENV GRAFANA_URL=http://grafana
```

Pass `GRAFANA_TOKEN` and `GRAFANA_SERVICE_ACCOUNT_TOKEN` to the agent at runtime through the task environment. Do not bake token values into the agent image unless the task pack already follows that convention for local test credentials.

Do not mount `data/grafana/state.json` into the agent container. Do not copy `grafanactl` or pass `GRAFANA_ADMIN_TOKEN` to the agent container.

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
