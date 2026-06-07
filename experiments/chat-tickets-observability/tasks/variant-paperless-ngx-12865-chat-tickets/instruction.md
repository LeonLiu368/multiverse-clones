# Production incident — service: paperless-worker

You are the on-call engineer for the **paperless-ngx** document service. An incident is
active and the application source is checked out at `/app/repo`.

Investigate using the two tools wired into your environment, find the root cause, and fix
it in `/app/repo`.

## Issue tracker — `linear` / `jira`

A Jira/Linear-style tracker holds the active incident ticket and the surrounding backlog.
Use the CLIs (they output JSON; there is no `--help`, run a bare command to see subcommands):

```bash
linear issue mine                       # issues assigned to you
linear issue list                       # the project backlog
linear issue search "index writer"      # full-text search (noisy on purpose)
linear issue view PNGX-417 --comments --links --attachments
jira issue view PNGX-417                # jira vocabulary over the same tracker
```

## Team chat — `slack` (CLI or MCP)

The on-call discussion that localizes the root cause lives in the team's Slack. Use whichever
interface you prefer:

```bash
slack channels                          # list channels
slack history paperless-oncall --limit 200
slack search "index writer lock"        # full-text search (returns misleading hits too — read carefully)
# the slack-mcp MCP server exposes the same operations as tools
```

## What to do

Correlate the incident ticket with the on-call thread to identify the exact root cause, then
implement the fix in `/app/repo`. Several wrong theories were floated in chat (a Redis lock,
bumping the writer heap, raising a lock timeout) before the team agreed on the real cause —
use the **final agreed** root cause, not a superseded guess. Validate your change against the
project's own test suite. **Do not modify the test suite** to make it pass.
