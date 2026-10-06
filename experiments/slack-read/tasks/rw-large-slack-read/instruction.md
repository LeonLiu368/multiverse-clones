# Find a few facts in the Slack workspace

You have access to a real **Slack workspace** with several channels of history. Read it through
either of two equivalent tools:

- the **`slack` CLI** (in your shell):
  ```bash
  slack channels                         # list channels
  slack history <channel> --limit 1000   # read a channel's messages (name or C… id)
  slack search "<query>"                 # full-text search
  # add --json to any command for raw JSON
  ```
- the **`slack` MCP server** — the same workspace via MCP tools: `channels_list`,
  `conversations_history`, `conversations_search_messages`, …

## Task
Answer these three questions. For the per-channel counts, "messages in a channel" means the
messages returned by that channel's **history** (`slack history <channel>` / `conversations.history`)
— read the **full** history (use a large `--limit`). Counts are **case-insensitive substring
matches** over message text.

1. In **#deploys**, how many messages contain the text **`deploy`**?
2. In **#product**, how many messages contain the text **`release`**?
3. How many channels are in the workspace?

Write your answers to `/workspace/answers.txt`, one per line, **exactly** in this format
(just the key, an `=`, and the number):

```
deploys_deploy=<number>
product_release=<number>
channels=<number>
```
