# Feature PR — ready for final review and merge

A feature has been designed, agreed on, and implemented as a pull request.
You are the assigned engineer responsible for the final review and merge.

## Issue tracker — `linear` / `jira`

```bash
linear issue mine
linear issue view FEAT-301 --comments
```

## Team chat — `slack` (CLI or MCP)

```bash
slack channels
slack history eng-design --limit 100
# or use the slack-mcp MCP server
```

## Code — `gh` / `git`

```bash
gh pr list -R acme/platform              # the open feature PR
gh pr view 1 -R acme/platform           # PR description and diff
gh repo clone acme/platform             # clone to inspect code if needed
```

## What to do

Read the feature ticket, the implementation spec agreed in the Slack design
channel, and the open pull request. Verify the PR implements exactly what the
team specified (regex pattern, error code, which function). If it matches, approve
and merge it, then move FEAT-301 to Done.
