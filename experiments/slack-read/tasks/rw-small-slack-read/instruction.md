# Count messages that mention "testing"

You have access to a small **Slack workspace**. Read it through either of two equivalent tools:

- the **`slack` CLI** (in your shell):
  ```bash
  slack channels                      # list channels
  slack history <channel> --limit 100 # read a channel's messages (name or C… id)
  slack search "testing"              # full-text search
  # add --json to any command for raw JSON
  ```
- the **`slack` MCP server** — the same workspace via MCP tools: `channels_list`,
  `conversations_history`, `conversations_search_messages`, …

## Task
Count how many messages in the **entire workspace** contain the word **`testing`**
(case-insensitive; substring match — e.g. "testing" or "Testing" both count).

Write **only that number** to `/workspace/answer.txt`. For example, if the answer were 7, the
file would contain exactly:

```
7
```
