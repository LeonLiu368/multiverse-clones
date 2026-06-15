# Production incident — service: paperless-ngx

You are the on-call engineer for **paperless-ngx**. Several REST API endpoints are returning
raw HTML **500** error pages (instead of proper JSON) when called according to their OpenAPI
schema — e.g. a second `POST /api/config/`, non-dict UI settings, and missing optional
parameters. The application source is checked out at `/app/repo`.

Investigate using the tools available to you, then fix the root cause in `/app/repo`:

- **Issue tracker** — use the `linear` (or `jira`) CLI to search the project's issues for the
  relevant bug reports and reproduction details (`linear issue list`, `linear issue search`).
- **Team chat** — use the `slack` tools to read the community channel for what users and
  maintainers have reported.
- **Logs / dashboards** — use the `gcx` CLI / Grafana tools to query the service request logs
  and localize the failing endpoints.

Correlate these signals, implement proper request validation so the endpoints return
appropriate JSON error responses (e.g. 400/405) instead of crashing, and validate your change
against the project's own test suite. Do not modify the test suite to make it pass.
