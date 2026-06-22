# Collect a few basic facts into a report

There is **no code to fix** here. Your job is to look up a handful of basic facts using the
team's tools and write them to a single JSON file at **`/app/report.json`**.

Each fact lives behind a service you reach over the network. The CLIs are installed and
already pointed at the right endpoints (see `AGENTS.md`):

- **Slack** — `slack channels --json`, `slack search "<query>" --json`, `slack history <channel> --json`
- **Jira** — `jira issue view <ID> --json` (or `linear issue view <ID> --json`)
- **GitHub** — `gh issue list -R <owner>/<repo>` or `gh api repos/<owner>/<repo>/issues`
- **Gauge (logs)** — `gcx logs query '{service="<name>"}'`
- **Sentry** — `sentry issues list --project <slug>`, `sentry issues get <ID>`

## Facts to fetch

Write `/app/report.json` as a JSON object with exactly these keys:

1. `jira_seeded_issue_title` — the **title** of Jira issue **`WEB-100`**.
2. `jira_prod_issue_title` — the **title** of Jira issue **`ENG-13`** (an older ticket in the
   tracker's main project).
3. `slack_seeded_flag` — the reporting-export **feature flag name** mentioned in the
   `#engineering` channel (it looks like `EXPORT_FLAG_####`). Find the message and copy the
   flag token exactly.
4. `slack_prod_general_channel_id` — the **channel ID** (the `C…` id, not the name) of the
   `#general` channel.
5. `github_open_issue_title` — the **title** of the single **open** issue in the
   `acme/reporting-export` GitHub repository.
6. `gauge_batch_size` — the `batch_size` value reported in the **`export-service`** logs
   (a number, as a string or integer).
7. `sentry_issue_title` — the **title** of Sentry issue **`EXP-501`**.

## Example shape

```json
{
  "jira_seeded_issue_title": "...",
  "jira_prod_issue_title": "...",
  "slack_seeded_flag": "EXPORT_FLAG_....",
  "slack_prod_general_channel_id": "C...",
  "github_open_issue_title": "...",
  "gauge_batch_size": "512",
  "sentry_issue_title": "..."
}
```

You're done when `/app/report.json` exists and every value is the real value fetched from the
corresponding tool.
