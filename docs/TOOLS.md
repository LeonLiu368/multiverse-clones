# The agent's tool surface

Each task gives the agent **two interchangeable ways** to operate the Mattermost workspace.
Both talk to the same server over the same remote (TCP) connection; the agent can use either.

## 1. `mmctl` — the official Mattermost CLI

A real admin CLI, copied verbatim out of the Mattermost product image (so the version always
matches the server). In the `client` container it is **pre-authenticated** as admin, so the
agent can run commands immediately. A few examples:

```bash
mmctl user list                              # list users
mmctl user search carol                      # find a user
mmctl user activate carol                    # reactivate a deactivated user
mmctl channel list test-demo                 # list channels on the team
mmctl channel unarchive test-demo:deploys    # restore an archived channel
mmctl post list test-demo:incidents -n 50    # read a channel's history
mmctl post create test-demo:incidents -m "…" # post a message
mmctl config get  FileSettings.EnableFileAttachments
mmctl config set  FileSettings.EnableFileAttachments true
```

Run `mmctl --help` (or `mmctl <group> --help`) inside the client to discover the rest.

## 2. `mmctl-mcp` — an MCP server (~65 tools)

The same capabilities, exposed as structured **MCP tools** so MCP-aware agents can call them
directly. It is registered the **Harbor-native way** in each task's `task.toml`:

```toml
[environment]
mcp_servers = [
  { name = "mattermost", transport = "stdio", command = "/usr/local/bin/mcp-mmctl", args = [] },
]
```

The Harbor agent runtime launches that stdio server and writes it into the agent's own MCP
config (e.g. Claude's `~/.claude.json`), so the tools auto-load. Under the hood each tool simply
shells out to `mmctl` over the remote auth context.

### The full tool list (65 tools)

| Group | Tools |
|---|---|
| generic | `mmctl` (run any mmctl command), `system_info` |
| posts | `post_create`, `post_list`, `post_delete` |
| channels | `channel_list`, `channel_create`, `channel_search`, `channel_archive`, `channel_unarchive` |
| users | `user_list`, `user_search`, `user_create`, `user_activate`, `user_deactivate`, `user_email`, `user_add_team`, `user_add_channel` |
| teams | `team_list`, `team_create`, `team_search`, `team_modify`, `team_rename` |
| bots | `bot_list`, `bot_create`, `bot_assign`, `bot_enable`, `bot_disable` |
| webhooks | `webhook_list`, `webhook_show`, `webhook_create_incoming`, `webhook_create_outgoing`, `webhook_delete` |
| auth | `auth_list`, `auth_set`, `auth_current` |
| roles & permissions | `role_system_admin`, `role_member`, `permission_add`, `permission_remove`, `permission_reset` |
| groups | `group_channel_list`, `group_team_list`, `group_channel_status`, `group_team_status`, `group_channel_enable`, `group_channel_disable`, `group_team_enable`, `group_team_disable` |
| plugins | `plugin_list`, `plugin_enable`, `plugin_disable`, `plugin_marketplace_list` |
| config & jobs | `config_get`, `config_set`, `config_show`, `job_list`, `job_update` |
| enterprise* | `license_remove`, `license_upload`, `license_upload_string`, `oauth_list`, `ldap_sync`, `ldap_idmigrate`, `saml_auth_data_reset` |

\* Enterprise/admin tools are present but several require an enterprise license; the
chat-operations tools (posts / channels / users / teams / bots / webhooks / config) are what
the current tasks actually use.

## "Minimal hand-holding" by design

Task instructions tell the agent **only the symptom** and that it has admin tools — never which
command to run. The agent has to explore the tool surface (e.g. realize that a deactivated user
is hidden from the default `user list` and needs the inactive filter, or that an archived
channel won't show in `channel list`) to diagnose and fix the issue. That exploration is the
skill being measured.

## Scoping note

This surface is **full workspace admin** — much broader than any one task needs. We keep it
broad on purpose (it mirrors a real admin's access) and rely on the **task instruction +
verifier** to define the objective. If you want a tightly-scoped eval, you can trim the tool
list in `task.toml`'s `mcp_servers` / instruction without changing the service.
