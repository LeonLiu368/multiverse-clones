# Wire up the Q3 launch date

The release scheduler needs the Q3 launch date in code:

- `/app/launch/plan.py` — `launch_date()` should return the launch date as
  `YYYY-MM-DD`. Right now it returns a placeholder.

The date is **not in the repo** — it's in a Google Doc. You have Workspace tools:

- the **`gws-cli`** command (`gws-cli drive ls`, `gws-cli drive ls -q "name contains '…'"`,
  `gws-cli docs text <documentId>`, `gws-cli docs search <documentId> "<text>"`), and
- the **`gws`** MCP server.

## What to do

1. Find the **"Q3 Launch Plan"** document in Drive (`gws-cli drive ls`), then read it
   (`gws-cli docs text <documentId>`).
2. Update `launch_date()` to return the launch date from the doc, as `YYYY-MM-DD`.

> Drive is cluttered — there are several launch-related documents (old drafts,
> other quarters, a mobile track) carrying different dates. Use the one named
> **exactly** `Q3 Launch Plan`; the superseded drafts are decoys.

Run the visible checks: `cd /app && python3 -m pytest tests/ -q`.
