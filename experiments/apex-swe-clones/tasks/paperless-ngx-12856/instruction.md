# Production incident — service: paperless-worker

You are the on-call engineer for the **paperless-worker** service. An incident is currently
active. The application source code is checked out at `/app/repo`.

Investigate using the tools available to you, then fix the root cause in `/app/repo`:

- **Issue tracker** — use the `linear` (or `jira`) CLI to read the active incident
  ticket(s) assigned to you. Read the ticket **comments** too
  (`linear issue view <ISSUE> --comments`) — the team records the agreed approach there.
- **Team chat** — use the `slack` tools to read the on-call channel for what responders
  have observed.
- **Logs / dashboards** — use the `gcx` CLI / Grafana tools to query the service logs and
  metrics and localize the failure.

Correlate these signals to identify the active production issue, find the root cause in the
source, and implement the fix in `/app/repo`. Validate your change against the project's own
test suite. Do not modify the test suite to make it pass.
