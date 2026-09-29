# Analytics pipeline schema drift

The `acme-analytics` codebase is checked out at **`/workspace`**. Its test suite is failing:

```bash
cd /workspace && python -m pytest -q
```

`events/publisher.py::build_event_payload` returns a v1-format payload — the analytics
pipeline was migrated to **schema v2**, but the function was never updated. The v2 field
names, types, and format requirements were announced by the data platform team in the team's
Slack workspace. They are **not** recorded in this repo.

Recover the v2 spec and update `build_event_payload` so the full suite passes without
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

Read carefully — there was a mid-thread correction on one of the field names; use the
corrected name, not the original suggestion.
