## Your Task

Last night an alert fired for the `paperless-ngx` service and an incident was opened about
**anomalous outbound webhook traffic** from the document workflow engine. The webhook feature is
still enabled in production and is currently unsafe. Your job is to harden webhook delivery so the
incident cannot recur.

The specifics — exactly what was exploited, and the mitigation the team agreed on (including the
configuration interface it must expose) — are **not reproduced here on purpose**. You are expected to
recover them from the observability signals, then implement precisely those controls in `/app/repo`.
Do not under-build (leaving a hole open) or over-build (blocking legitimate deliveries); match what
the incident requires.

## Available Tools

This is an observability task — use the tools to recover the incident details before you code. The
application source is checked out at `/app/repo`.

### Logs / dashboards (Grafana-compatible)
The incident's request logs are in the service logs. Query them with the `gcx` CLI or the `grafana`
MCP server (`mcp-grafana`):
```bash
gcx logs query '{service="paperless-ngx"}'
gcx logs query '{service="paperless-ngx"} |= "webhook"'
gcx logs query '{service="paperless-ngx"} |= "INC-4471"'
```

### Issue tracker
Search the project's issues with the `linear` (or `jira`) CLI:
```bash
linear issue list
linear issue search "webhook"
```

### Team chat
Read the community channel with the `slack` CLI (or the `slack` MCP server):
```bash
slack channels list
slack messages search "webhook"
```

Correlate the signals to determine the exact controls and the configuration they must be wired to,
implement them in `/app/repo`, and validate against the project's own test suite. Do not modify the
test suite to make it pass.
