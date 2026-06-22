## Your Task

We need to implement environment variable support for x-podman settings in podman-compose. Currently, settings like `in_pod`, `default_net_name_compat`, `default_net_behavior_compat`, and `pod_args` can only be configured in the compose file's x-podman section, but operators need the ability to override these via `PODMAN_COMPOSE_*` environment variables.

The implementation requires refactoring how x-podman settings are stored and accessed — check the observability logs for the proposed implementation pattern including the enum class and parsing method that need to be created. The tests expect specific class/attribute names to exist on `PodmanCompose`.

Verify with `pytest tests/unit/test_container_to_args.py -v`.

## Available Tools

This is an observability task — use the observability and collaboration tools to debug and
understand the issue. The application source code is checked out at `/app/repo`.

### Logs / dashboards (Grafana-compatible)
Query the service request logs with the `gcx` CLI or the `grafana` MCP server (`mcp-grafana`):
```bash
gcx logs query '{service="podman-compose"}'
gcx logs query '{service="podman-compose"} |= "error"'
gcx dashboards list
```

### Issue tracker
Search the project's issues with the `linear` (or `jira`) CLI:
```bash
linear issue list
linear issue search "<term>"
```

### Team chat
Read the community channel with the `slack` CLI (or the `slack` MCP server):
```bash
slack channels list
slack messages search "<term>"
```

Correlate these signals to localize the bug, then implement the fix in `/app/repo`.
Validate against the project's own test suite. Do not modify the test suite to make it pass.
