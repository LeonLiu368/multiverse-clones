# The agent's tool surface: the `slack` CLI + MCP

The agent operates the workspace through **two equivalent Slack tools** — consistent across every
task (no raw SDK/curl in the instructions):

- the **`slack` CLI** — a command-line tool in the agent's shell.
- the **`slack` MCP server** (`slack-mcp`, stdio) — the same operations as MCP tools.

Both are thin clients of a **realistic Slack Web API** (the `slackgw/` FastAPI gateway: `{"ok":...}`
envelopes, `C…`/`U…` ids, `ts` strings, an `xoxb-` token). Under the hood the gateway translates each
Slack method to a real Mattermost backend; the agent never sees Mattermost. Both tools ship in the
agent image from the `slackcli` package (single source: `selfcontained/base/slackcli/`); the MCP
server is declared per task in `task.toml` (`[[environment.mcp_servers]]`, stdio, `command="slack-mcp"`).

## How the agent calls it
The tools read `$SLACK_API_URL` (`http://api`, neutral host) and `$SLACK_BOT_TOKEN` (`xoxb-…`),
baked into the agent image as env.

```bash
# the `slack` CLI
slack channels                              # list channels
slack history platform-infra --limit 100    # read a channel (name or C… id)
slack search "overdue fee"                  # full-text search (noisy on purpose)
slack post postmortems "ROOT CAUSE: ..."    # post a message
slack whoami                                # identity
# --json on any command for raw JSON
```

```
# the `slack` MCP tools (same ops): slack_list_channels, slack_history, slack_search,
#                                    slack_list_users, slack_post_message, slack_whoami
```

## Methods implemented (task-scoped) — what the CLI/MCP call under the hood
| Method | Returns |
|---|---|
| `auth.test` | `{ok, url, team, user, team_id, user_id}` |
| `conversations.list` | `{channels:[{id,name,is_channel,is_private,is_archived,topic,purpose}], response_metadata}` |
| `conversations.info` | `{channel:{…}}` |
| `conversations.history` | `{messages:[{type,user,text,ts}], has_more, response_metadata}` |
| `search.messages` | `{messages:{total, matches:[{type,user,text,ts,channel}]}}` — **noisy on purpose** |
| `users.list` / `users.info` | `{members:[…]}` / `{user:{id,name,real_name,deleted,is_bot,profile}}` |
| `chat.postMessage` | `{ok, channel, ts, message}` |

Fidelity is faithful where agents trip: the envelope (always HTTP 200), id formats, `ts` strings,
cursor fields, and snake_case error codes (`not_authed`, `channel_not_found`, `unknown_method`).

## What the agent CANNOT see (recon hardening)
- **Mattermost is unreachable.** It's bound to `127.0.0.1` inside the `api` sidecar; `curl api:8065`
  → connection refused.
- **No `/api/v4`.** Any non-Slack path (e.g. a probe at `/api/v4/...`) returns Slack-shaped
  `{"ok":false,"error":"unknown_method"}`.
- **No backend/framework headers.** `Server`/`X-Version-Id` are stripped; responses look like a
  generic Slack-compatible endpoint.
- **No service-name tell in URLs** beyond the neutral host `api`; no `:8065`, no Mattermost.

## Minimal hand-holding by design
Instructions tell the agent only the symptom + that it has the `slack` CLI / MCP tools. It must
explore (list channels, read history, search) and **disambiguate** superseded vs. agreed values —
that exploration is the skill being measured.
