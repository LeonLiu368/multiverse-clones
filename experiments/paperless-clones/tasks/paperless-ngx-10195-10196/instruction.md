## Your Task

I'm experiencing multiple crashes in my REST API that are preventing normal operations. When I try to create a configuration via POST to the config endpoint a second time, the server returns a 500 error instead of handling it gracefully. The mail rules endpoint is also crashing when I submit only the required fields according to the schema - it seems to expect additional fields that should be optional. Most critically, the UI settings endpoint accepts invalid data that then crashes the entire homepage, making the application unusable until I manually reset the settings. I need these endpoints to properly validate incoming requests and return appropriate error responses instead of crashing the server.

## Available Tools
This is an observability task — use the observability + collaboration tools. The repo is at `/app/repo`.
- Logs (Grafana/Loki): `gcx logs query '{service="paperless-ngx"}'` (filter with `|= "500"` etc.), `gcx dashboards list`
- Issue tracker: `linear issue list`, `linear issue search "<term>"` (or the `jira` CLI)
- Team chat: `slack channels list`, `slack messages search "<term>"`
Correlate these, then fix the root cause in `/app/repo`. Do not modify the test suite.
