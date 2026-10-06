# On-call incident — fix ready for review

You are the on-call engineer. A team member has already diagnosed the incident
and submitted a fix as a pull request. Your job is to validate the fix against
the context across all three surfaces, then merge it and close the ticket.

## Issue tracker — `linear` / `jira`

```bash
linear issue mine                        # your assigned tickets
linear issue view PROD-101 --comments    # full incident ticket
```

## Team chat — `slack` (CLI or MCP)

```bash
slack channels
slack history ops-oncall --limit 100
# or use the slack-mcp MCP server
```

## Code — `gh` / `git`

```bash
gh pr list -R acme/webapp                # the open fix PR
gh pr view 1 -R acme/webapp             # PR description and diff
gh repo clone acme/webapp               # clone to inspect code if needed
```

## What to do

Read the incident ticket, the on-call discussion, and the open pull request.
Verify the PR's fix matches what the team agreed in the Slack thread.
If correct, approve and merge it, then set PROD-101 to Done.
