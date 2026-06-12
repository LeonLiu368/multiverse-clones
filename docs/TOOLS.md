# The agent's tool surface: the `slack` CLI + the korotovsky MCP

The agent operates the workspace through **two Slack tools** — consistent across every task (no raw
SDK/curl in the instructions):

- the **`slack` CLI** — our small command-line tool in the agent's shell.
- the **`slack-mcp` server** — the off-the-shelf
  **[korotovsky/slack-mcp-server](https://github.com/korotovsky/slack-mcp-server)** (stdio),
  patched only to point its base URL at our gateway.

Both are clients of a **realistic Slack Web API** (the `slackgw/` FastAPI gateway: `{"ok":...}`
envelopes, `C…`/`U…` ids, `ts` strings, threads, reactions). The gateway serves from a **SQLite store
seeded from a real Slack export** — there's no real Slack and no Mattermost. The CLI ships in the
image from `selfcontained/base/slackcli/`; the MCP is a Go binary built into the image and declared
per task in `task.toml` (`[[environment.mcp_servers]]`, stdio, `command="slack-mcp"`).

## How the agent calls it
Both reach the gateway at `$SLACK_API_URL` (`http://localhost`) with `$SLACK_BOT_TOKEN` (an
`xoxp-…` token), baked into the image as env.

```bash
# the `slack` CLI
slack channels                              # list channels
slack history platform-infra --limit 100    # read a channel (name or C… id)
slack search "overdue fee"                  # full-text search (noisy on purpose)
slack post error-budget-reports "ROOT CAUSE: ..."   # post a message
slack whoami                                # identity
# --json on any command for raw JSON
```

```
# the korotovsky MCP tools (enabled set):
#   channels_list, conversations_history, conversations_replies,
#   conversations_search_messages, conversations_add_message
```

The MCP runs in **xoxp (user-token) mode** (so its search tool is enabled) and is restricted via
`SLACK_MCP_ENABLED_TOOLS` to the tools our gateway backs (all standard Web API — no edge-API tools).
The `slack-mcp` wrapper recovers the token from PID 1 (stdio strips env) and sets the korotovsky env.

## Methods implemented (task-scoped) — what the CLI/MCP call under the hood
| Method | Returns |
|---|---|
| `auth.test` | `{ok, url(<ws>.slack.com), team, user, team_id, user_id, bot_id}` |
| `conversations.list` / `users.conversations` | `{channels:[{id,name,is_channel,is_archived,topic,purpose,…}], response_metadata}` |
| `conversations.info` | `{channel:{…}}` |
| `conversations.history` | `{messages:[{type,user,text,ts,thread_ts?,reactions?,subtype?}], has_more, response_metadata}` |
| `conversations.replies` | `{messages:[…thread parent + replies…]}` |
| `search.all` / `search.messages` | `{messages:{total, matches:[…]}, files:{…empty…}}` — **noisy on purpose** |
| `users.list` / `users.info` | `{members:[…]}` / `{user:{id,name,real_name,deleted,is_bot,profile}}` |
| `chat.postMessage` / `conversations.add_message` | `{ok, channel, ts, message}` |
| `team.info` | `{team:{id,name,domain}}` |

Fidelity is faithful where tools trip: the envelope (always HTTP 200), id formats, `ts` strings, a
Slack-shaped `auth.test` URL (so korotovsky parses the workspace), `search.all` (slack-go's combined
endpoint), and snake_case error codes (`not_authed`, `channel_not_found`, `unknown_method`).

## Note on isolation
This is a lightweight self-contained mock — there's no hidden real backend to discover (no
Mattermost, no Postgres). The gateway is simply the in-container Slack-compatible endpoint at
`http://localhost`. The agent reaches the workspace exactly as it would a self-hosted Slack-compatible
API.

## Minimal hand-holding by design
Instructions tell the agent only the symptom + that it has the `slack` CLI / MCP tools. It must
explore (list channels, read history, search, follow threads) and **disambiguate** superseded vs.
agreed values — that exploration is the skill being measured.
