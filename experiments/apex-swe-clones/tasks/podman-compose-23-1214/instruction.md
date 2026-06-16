## Your Task

**Issue Description**:

# Issue #23: WIP: proper healthchecks support

## Problem Description

The healthcheck command formatting in podman-compose is incorrect. Currently, healthcheck
commands are being wrapped with `/bin/sh -c` and shell quoting, but podman expects healthcheck
commands to be passed as JSON arrays. This causes healthchecks to fail because podman cannot
properly interpret the malformed command format.

## Additional Context

The current implementation incorrectly formats healthcheck commands like:
- String healthchecks get wrapped as `/bin/sh -c "command"`
- CMD arrays get shell-quoted and wrapped as `/bin/sh -c 'cmd' 'arg1' 'arg2'`
- CMD-SHELL arrays also get shell-quoted and wrapped

But podman expects JSON array format:
- String healthchecks should become `["CMD-SHELL", "command"]`
- CMD arrays should become `["cmd", "arg1", "arg2"]` (removing the CMD keyword)
- CMD-SHELL arrays should become `["command"]` (removing the CMD-SHELL keyword and keeping only
  the command string)

**Important:** For CMD-SHELL arrays like `["CMD-SHELL", "command"]`, the implementation should
remove the "CMD-SHELL" prefix and pass only `["command"]` to the `--healthcheck-command` flag.

A reported reproduction (`podman_compose.py` `container_to_args`) raises
`ValueError: 'CMD_SHELL' takes a single string after it` for
`test: ["CMD-SHELL", "pg_isready", "-U", "$PGUSER", "-d", "$PGDATABASE"]`.

The application source code is checked out at `/app/repo`.

---

## Available Tools

This is an observability task — you should use the observability and collaboration tools to
debug and understand the issue.

### Issue tracker
Search the project's issues with the `linear` (or `jira`) CLI:
```bash
linear issue list
linear issue search "healthcheck"
```

### Logs / dashboards (Grafana-compatible)
Query logs and dashboards with the `gcx` CLI or the `grafana` MCP server:
```bash
gcx logs query '{service="podman-compose"}'
gcx logs query '{service="podman-compose"} |= "healthcheck"'
```

### Team chat
Read the team channel with the `slack` CLI (or the `slack` MCP server) if available.

Correlate these signals, fix the root cause in `/app/repo`, and validate against the project's
own test suite. Do not modify the test suite to make it pass.
