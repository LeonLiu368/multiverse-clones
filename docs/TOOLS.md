# The agent's tool surface: `slack`

The agent operates the workspace through a single Slack-branded tool called **`slack`**,
available in two interchangeable forms. Both are a **thin facade** over the real Mattermost
tooling (`mmctl` / `mmctl-mcp`) — the agent sees "Slack", the backend is Mattermost.

## 1. `slack` CLI (Slack Web API style)

A small wrapper (`environment/slack`) exposing Slack Web API-style methods. In the `client`
container it is pre-authenticated, so the agent can run it immediately. `slack help` lists
everything:

```
Conversations (channels):
  slack conversations.list [--archived]      # active channels, or archived ones with --archived
  slack conversations.info       <channel>   # {id, name, is_archived, is_private, purpose}
  slack conversations.history    <channel> [count]
  slack conversations.create     <name>
  slack conversations.archive    <channel>
  slack conversations.unarchive  <channel>
Chat:
  slack chat.postMessage         <channel> <text...>
Search:
  slack search.messages          <query terms>   # matches across all channels (noisy — returns
                                                  # superseded/old hits too; read to disambiguate)
Users (members):
  slack users.list                           # [{id, name, deleted}]
  slack users.info               <user>      # {id, name, real_name, email, deleted}
Admin:
  slack admin.users.setActive    <user> <true|false>
  slack admin.getFileSharing
  slack admin.setFileSharing     <true|false>
  slack auth.test
```

- **Read/diagnostic methods** (`conversations.list/info`, `users.list/info`, `admin.getFileSharing`)
  return **Slack-shaped JSON** with the fields that make a problem visible — e.g. `deleted: true`
  for a deactivated member, `is_archived: true` for a hidden channel. They read the workspace API
  directly.
- **Action methods** (`conversations.unarchive`, `chat.postMessage`, `admin.users.setActive`,
  `admin.setFileSharing`, …) perform the change via `mmctl` underneath.
- Anything unrecognized is **passed straight through** to the underlying CLI, so nothing is
  blocked.

The workspace name is injected automatically; the agent never has to know about it.

## 2. `slack` MCP server

Registered the **Harbor-native way** in each task's `task.toml`:

```toml
[environment]
mcp_servers = [
  { name = "slack", transport = "stdio", command = "/usr/local/bin/slack-mcp", args = [] },
]
```

The Harbor agent runtime launches that stdio server and writes it into the agent's own MCP
config (e.g. Claude's `~/.claude.json`), so the tools auto-load under the name **`slack`**.
`slack-mcp` authenticates the connection and then hands off to the underlying MCP server, which
exposes the workspace operations as structured tools (`channel_list`, `channel_unarchive`,
`post_create`, `user_activate`, `config_get`/`config_set`, …).

## How the facade maps down

| Agent sees (`slack`) | Runs underneath |
|---|---|
| `slack conversations.list [--archived]` | REST `GET /teams/{id}/channels[/deleted]` → Slack-shaped JSON |
| `slack conversations.unarchive <c>` | `mmctl channel unarchive <ws>:<c>` |
| `slack chat.postMessage <c> <text>` | `mmctl post create <ws>:<c> -m <text>` |
| `slack users.info <u>` | REST `GET /users/username/<u>` → `{…, deleted}` |
| `slack admin.users.setActive <u> true` | `mmctl user activate <u>` |
| `slack admin.setFileSharing true` | `mmctl config set FileSettings.EnableFileAttachments true` |
| `slack` MCP tools | `mmctl-mcp` (remote-auth patched) |

## "Minimal hand-holding" by design

Task instructions tell the agent **only the symptom** and that it has the `slack` tool — never
which method to run. The agent has to explore (`slack help`, then the right read method/flag) to
make the problem visible — a deactivated member only shows as `deleted: true` in `users.info`; an
archived channel only appears under `conversations.list --archived`; a disabled setting only
shows via `admin.getFileSharing`. That exploration is the skill being measured.

## Why a facade (lightweight) rather than a full Slack API

This is intentionally a **lightweight Slack rename**: real Slack method names and Slack-shaped
read output, but mapped onto Mattermost rather than reimplementing Slack's API byte-for-byte. It
makes the environment *look* like Slack to the agent with almost no code, while keeping the
battle-tested Mattermost backend. If you later need true Slack-API fidelity (real Slack SDKs,
exact JSON), that's the job of the from-scratch Slack clone on the other branch.
