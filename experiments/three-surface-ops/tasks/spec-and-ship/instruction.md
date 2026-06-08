# Feature implementation

A feature is ready to implement. You have the ticket, the design discussion, and
access to the codebase.

## Issue tracker — `linear` / `jira`

```bash
linear issue mine
linear issue view FEAT-301 --comments
```

## Team chat — `slack` (CLI or MCP)

```bash
slack channels
slack history eng-design --limit 100
slack search "email validation"
```

## Code — `gh` / `git`

```bash
gh repo list
gh repo clone acme/platform
```

## What to do

The ticket describes the requirement. The Slack design channel has the team's
agreed implementation spec — the exact details of how to implement it (regex,
error handling, which function to modify). Implement it exactly as the team agreed,
ship via a reviewed and merged pull request, and move the ticket to Done.
