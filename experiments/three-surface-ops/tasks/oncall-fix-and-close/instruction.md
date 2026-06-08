# On-call incident — active

You are the on-call engineer. An incident is active.

Investigate using the three tools wired into your environment, find the root cause,
and fix it.

## Issue tracker — `linear` / `jira`

```bash
linear issue mine                        # your assigned tickets
linear issue list                        # project backlog
linear issue view PROD-101 --comments    # full incident ticket
```

## Team chat — `slack` (CLI or MCP)

```bash
slack channels
slack history ops-oncall --limit 100
slack search "search endpoint"
# or use the slack-mcp MCP server
```

## Code — `gh` / `git`

```bash
gh repo list                             # repos you have access to
gh repo clone acme/webapp
```

## What to do

Correlate the incident ticket with the on-call discussion to identify the exact
root cause. The ticket describes the symptom; the chat thread has the diagnosis and
agreed fix. Implement the fix in the repo, ship it via a reviewed and merged pull
request, and move the ticket to Done.

**Do not modify any test files.**
