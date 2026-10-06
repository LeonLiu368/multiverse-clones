## Your Task

I need to add security protections to our webhook delivery system to prevent SSRF attacks and other exploits. Right now, webhooks could potentially be abused to probe internal networks, access private services, or bypass security controls through redirects and header manipulation.

The system should validate that webhook URLs only use safe protocols and ports, block requests to private and internal IP addresses (unless explicitly configured to allow them), and prevent attackers from exploiting redirects or injecting malicious headers to reach unintended destinations. When a webhook tries to reach a blocked destination or encounters a redirect, it should fail immediately rather than proceeding with the request.

## Available Tools

This is an observability task — use the observability and collaboration tools to debug and
understand the issue. The application source code is checked out at `/app/repo`.

### Logs / dashboards (Grafana-compatible)
Query the service request logs with the `gcx` CLI or the `grafana` MCP server (`mcp-grafana`):
```bash
gcx logs query '{service="paperless-ngx"}'
gcx logs query '{service="paperless-ngx"} |= "error"'
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
