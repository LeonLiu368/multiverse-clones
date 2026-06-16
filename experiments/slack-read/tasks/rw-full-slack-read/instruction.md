# Find a few facts in the Slack workspace

You have access to a **large real Slack workspace** (many channels, years of history) through
either of two equivalent tools:

- the **`slack` CLI** (in your shell):
  ```bash
  slack channels                          # list channels
  slack history <channel> --limit 1000    # read a channel's messages (name or C… id)
  slack search "<query>"                  # full-text search
  # add --json to any command for raw JSON
  ```
- the **`slack` MCP server** — the same workspace via MCP tools: `channels_list`,
  `conversations_history`, `conversations_search_messages`, …

## Task
Answer these three questions. For the per-channel counts, "messages in a channel" means the
messages returned by that channel's **history** (`slack history <channel>` / `conversations.history`).
Counts are **case-insensitive substring matches** over message text.

1. How many channels are in the workspace?
2. How many messages are in **#testing-survey-responses** (its history)?
3. In **#testing-survey-responses**, how many messages contain the text **`survey`**?

Write your answers to `/workspace/answers.txt`, one per line, **exactly** in this format:

```
channels=<number>
tsr_messages=<number>
tsr_survey=<number>
```
