# Rate limiter misconfiguration

The `acme-api` codebase is checked out at **`/workspace`**. Its test suite is currently failing:

```bash
cd /workspace && python -m pytest -q
```

`ratelimit/bucket.py` defines four configuration constants — `CAPACITY`, `REFILL_RATE`,
`INITIAL_TOKENS`, and `OVERDRAFT_ALLOWANCE` — that are **wrong**. They were set to conservative
placeholder values during initial development and revised after a load-testing exercise, but the
repo was never updated. The agreed production values live only in the team's Slack workspace.

Recover the agreed values and update the constants so the full test suite passes without
breaking tests that already pass.

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

Several values were proposed and revised during the load-test discussion — use the **final
agreed values**, not superseded proposals.
