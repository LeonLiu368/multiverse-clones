# Production issue

Users are hitting errors in production and a work item has been assigned to you
to resolve it. Nobody is going to walk you through it: the symptom, the
root-cause discussion, the agreed approach, and the code all live in different
places, and most of what you'll read is unrelated chatter. Figure out what's
actually wrong, decide on the fix your team agreed to, implement it, and put it
up for review.

## Tools you have

- **Issue tracker** — the `linear` (and `jira`) CLI. Your team's tickets,
  assignments, priorities, and comments live here.
- **Team chat** — the `slack` CLI and the `slack-mcp` MCP server. Discussion is
  spread across many channels in the workspace.
- **Code** — `git` and the `gh` CLI for the organization's GitHub host. Work is
  proposed as pull requests against `main`.

## What "done" looks like

A pull request that fixes the problem. Your change will be graded by checking
out your PR branch and running the project's existing automated test suite
together with additional tests for the reported behavior — everything must
pass. Don't change or delete tests to make them pass.
