# Incident triage in the Acme Slack workspace

An incident is active in the **Acme** Slack workspace. You have `slack-cli` configured
(it talks to the workspace at `$SLACK_API_URL`).

Investigate with the CLI, for example:

```bash
slack-cli channels list
slack-cli channels history incidents --format markdown
slack-cli thread incidents <ts> --format markdown      # read the incident thread
slack-cli search "latency" --format markdown
```

Read the discussion in **#incidents**, determine the **root cause** of the checkout
latency incident, then post a single concise summary message to **#incidents** that
begins with `ROOT CAUSE:` and names the underlying cause:

```bash
slack-cli post incidents "ROOT CAUSE: <your one-line root cause>"
```
