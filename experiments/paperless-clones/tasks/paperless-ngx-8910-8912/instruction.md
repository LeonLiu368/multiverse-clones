## Your Task

I'm running into an issue where the custom fields API endpoint changed its response format in a recent update, but the change isn't being properly versioned. When I make API requests with older version headers (like `version=6`), I'm still getting the new response format where select options are objects with IDs and labels, instead of the simple string array format that older API versions should return. This is breaking backward compatibility for my application that expects the legacy format when using older API versions. I need the API to respect the version header and return responses in the format that corresponds to the requested version, so existing integrations don't break when Paperless is updated.

## Available Tools
This is an observability task — use the observability + collaboration tools. The repo is at `/app/repo`.
- Logs (Grafana/Loki): `gcx logs query '{service="paperless-ngx"}'` (filter with `|= "500"` etc.), `gcx dashboards list`
- Issue tracker: `linear issue list`, `linear issue search "<term>"` (or the `jira` CLI)
- Team chat: `slack channels list`, `slack messages search "<term>"`
Correlate these, then fix the root cause in `/app/repo`. Do not modify the test suite.
