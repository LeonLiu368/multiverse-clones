# Error-budget monitor: wrong alert thresholds

The `acme-sre-tools` codebase is checked out at **`/workspace`**. Its test suite is failing:

```bash
cd /workspace && python -m pytest -q
```

`budget/monitor.py::check_budget` has **wrong alert thresholds and paging conditions** — they
were set to placeholder values and revised in an SLO review, but the repo was never updated.
The agreed thresholds live in the team's Slack workspace.

Once you fix the code so the suite passes, also **post a notification** to Slack channel
`#error-budget-reports` confirming the thresholds you applied. The notification must include
the `error_rate` threshold and the `budget` threshold values.

You operate the team's **Slack** through two equivalent tools — use whichever you prefer:

- the **`slack` CLI** (preinstalled in your shell):

```bash
slack channels                             # list channels
slack history platform-infra --limit 100   # read a channel (by name or C... id)
slack search "rate limit"                  # full-text search (noisy on purpose - read carefully)
slack post <channel> "<text>"              # post a message
slack whoami                               # who am I
# add --json to any command for raw JSON
```

- the **`slack` MCP server** — the same workspace as MCP tools: `channels_list`,
  `conversations_history`, `conversations_replies`, `conversations_search_messages`,
  `conversations_add_message`.

Several thresholds were proposed and revised during the SLO review — use the **final agreed
values**, not earlier proposals. The paging condition also involves latency.
