# fetch-basics — working notes for the agent

This task has **no code to fix**. Your only job is to fetch a few basic facts from the
team's tools and write them to `/app/report.json`. Every fact lives behind a service you
reach over the network with a CLI that is already installed and configured:

| Fact source | Tool (already on PATH) | Endpoint (preset in env) |
|---|---|---|
| Slack    | `slack`  (`slack channels --json`, `slack search "<q>" --json`, `slack history <ch> --json`) | `$SLACK_API_URL` |
| Jira     | `jira` / `linear` (`jira issue view <ID> --json`) | `$PLANE_BASE_URL` |
| GitHub   | `gh` (`gh issue list -R <owner>/<repo>`, `gh api repos/<owner>/<repo>/issues`) | `$GH_HOST` |
| Gauge    | `gcx` (`gcx logs query '{service="..."}'`) | `$GRAFANA_URL` |
| Sentry   | `sentry` (`sentry issues list --project <slug>`, `sentry issues get <ID>`) | `$SENTRY_URL` |

See `instruction.md` for exactly which facts to fetch and the output schema.
