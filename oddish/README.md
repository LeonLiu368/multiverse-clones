# Oddish tasks (Slack-clone)

Oddish-runnable, **self-contained** multi-service tasks. Each task is a seeded Slack
workspace (the `slack` service, built from the vendored slackclone package) plus an agent
container (`client`) that has **`slack-cli`** pointed at it (`SLACK_API_URL=http://slack:3000`).
The agent operates the workspace only through the tools; the verifier reads state back via
the Slack API, so scoring is deterministic (`nop`=0, `oracle`=1).

> Self-containment: build contexts live inside `tasks/<name>/environment/` (the slackclone
> package is vendored there), so `oddish run` uploads and builds each task with **no**
> references outside the task directory.

## Layout

```
oddish/
  slack-clone-manifest.yaml      # create-oddish-task manifest (task_path, tasks, agents)
  sweep.yaml                     # oddish CLI sweep config
  tasks/
    slack-incident-triage/
      task.toml  instruction.md
      environment/
        Dockerfile               # client (agent) image — installs slack-cli
        docker-compose.yaml      # client + slack
        slack/{Dockerfile,entrypoint.sh}
        slackclone/              # vendored package (src + pyproject)
        data/slack/workspace.json
      solution/solve.sh          # oracle
      tests/{test.sh, run_verifier.sh}   # split-harness verifier (reads state via the API)
```

## Run via Oddish

```bash
cd /path/to/oddish/oddish
uv run oddish run /path/to/abundant-slack-clone/oddish/tasks \
  -a gemini-cli -m google/gemini-3.1-flash-preview --n-trials 1
# or with the sweep config:
uv run oddish run .../oddish/tasks -c .../oddish/sweep.yaml
```

## Local validation (per task)

```bash
cd oddish/tasks/slack-incident-triage/environment
docker compose config                 # renders client + slack
docker compose up -d --build          # slack goes healthy, then client
docker cp ../tests   client:/tests
docker cp ../solution client:/solution
docker compose exec -T client bash /tests/run_verifier.sh   # nop  -> reward 0
docker compose exec -T client bash /solution/solve.sh
docker compose exec -T client bash /tests/run_verifier.sh   # oracle -> reward 1
docker compose down -v
```

## Add a new task
Copy `tasks/slack-incident-triage`, swap `environment/data/slack/workspace.json` (author it
with `slack-cli seed generate|import-export|load --emit workspace.json`), rewrite
`instruction.md` + `solution/solve.sh` + `tests/run_verifier.sh`, and add the name to the
manifest/sweep. Keep the `environment/slackclone/` vendored copy in sync with the repo's `src/`.

---

# Mattermost tasks (real product, `mmctl`)

Alongside the from-scratch Slack clone, this repo also hosts tasks built on the **real
Mattermost product** (team edition 8.1.1 + embedded Postgres) — the "be lazy, reuse OSS"
path. The agent's tool is **`mmctl`**, the official Mattermost CLI, copied straight out of
the Mattermost image (exact-version, no download). See
[`mattermost-manifest.yaml`](mattermost-manifest.yaml) / [`mattermost-sweep.yaml`](mattermost-sweep.yaml).

**`tasks/mattermost-incident-response/`** — the agent drops into a seeded workspace and runs
a **multi-step incident response**, all via `mmctl`: read `#incidents`, post the `ROOT CAUSE:`,
**create a dedicated `inc-checkout-latency` channel**, and post a `SUMMARY:` there. This
deliberately flexes the **write/operate** surface (post + threaded reply + channel-admin +
post) — a workflow APEX-bench's read-only Mattermost MCP tools cannot express. Validated
`nop`=0 / `oracle`=1.

```
tasks/mattermost-incident-response/
  task.toml  instruction.md
  environment/
    Dockerfile                 # client: copies mmctl out of the Mattermost image
    client-entrypoint.sh       # mmctl auth login (admin) + wait-for-seed, then sleep
    docker-compose.yaml        # client + mattermost (platform: linux/amd64; no networks)
    mattermost/{Dockerfile,entrypoint.sh,seed.py}   # vendored Mattermost service + seeder
    data/mattermost/scraped.json                    # {messages:[{channel,author,content,timestamp}]}
  solution/solve.sh            # oracle: 4 mmctl steps
  tests/{test.sh,run_verifier.sh}   # split-harness verifier (reads state via REST /api/v4)
```

Service contract (relied on by client + verifier): admin `admin@demo.local / AdminUser123!`,
team `test-demo`, channels seeded incl. `#incidents`. Channels are created over the REST API
(so they show in `mmctl channel list`); posts are inserted via SQL to preserve original
timestamps. **No `networks:`** in the compose, and both services pin `platform: linux/amd64`
(Mattermost/mmctl are amd64-only; Modal runs amd64 natively).

## Run / validate the Mattermost task

```bash
# Oddish
cd /path/to/oddish/oddish
uv run oddish run /path/to/abundant-slack-clone/oddish/tasks \
  -c /path/to/abundant-slack-clone/oddish/mattermost-sweep.yaml

# Local (first build pulls the Mattermost image; ~5-8 min)
cd oddish/tasks/mattermost-incident-response/environment
docker compose up -d --build           # mattermost goes healthy, client auths mmctl
docker cp ../tests client:/tests && docker cp ../solution client:/solution
docker compose exec -T client bash /tests/run_verifier.sh   # nop    -> reward 0
docker compose exec -T client bash /solution/solve.sh
docker compose exec -T client bash /tests/run_verifier.sh   # oracle -> reward 1
docker compose down -v
```

**Seeding it yourself.** Edit `environment/data/mattermost/scraped.json` (the
`{messages:[{channel,author,content,timestamp}]}` format the seeder ingests). The general
no-code paths Mattermost gives for free: synthetic via `mmctl sampledata --seed N --bulk
ws.jsonl` then `mmctl import`; real Slack export via `mmetl transform slack` then `mmctl
import`.

## MCP surface (`mmctl-mcp`) — tools the agent gets

The task also exposes an **MCP server** so the agent can drive Mattermost via structured
tools instead of (or alongside) shell `mmctl`. It is registered the **Harbor-native way** in
`task.toml`:

```toml
[environment]
mcp_servers = [
  { name = "mattermost", transport = "stdio", command = "/usr/local/bin/mcp-mmctl", args = [] },
]
```

Harbor's agent runtime launches this stdio server and writes it into the agent's own MCP
config (e.g. Claude's `~/.claude.json` `mcpServers`), so the tools auto-load. Validated
against Harbor's `TaskConfig`/`MCPServerConfig` model.

**Implementation.** The server is [`mmctl-mcp`](https://github.com/mattermost/mmctl-mcp)
(authored by a Mattermost core maintainer) built from a pinned commit in the client image's
Go builder stage. **One-line patch:** upstream hard-codes `mmctl --local` (a unix socket on
the *server* host, unreachable from the separate `client` container); we drop it so every
tool uses mmctl's **remote auth context** (TCP → `http://mattermost:8065`) — the same
transport `mmctl` and the verifier already use, and the only Harbor/Modal-portable option.
The `mcp-mmctl` wrapper does an idempotent `mmctl auth login` then hands off stdio. (License:
upstream has no SPDX-detected license — fine for internal eval use; revisit before any
redistribution.)

**The 65 tools** (verified live via an `initialize` → `tools/list` → `tools/call` probe):

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
| roles/perms | `role_system_admin`, `role_member`, `permission_add`, `permission_remove`, `permission_reset` |
| groups | `group_channel_list`, `group_team_list`, `group_channel_status`, `group_team_status`, `group_channel_enable`, `group_channel_disable`, `group_team_enable`, `group_team_disable` |
| plugins | `plugin_list`, `plugin_enable`, `plugin_disable`, `plugin_marketplace_list` |
| config/system | `config_get`, `config_set`, `config_show`, `job_list`, `job_update` |
| enterprise* | `license_remove`, `license_upload`, `license_upload_string`, `oauth_list`, `ldap_sync`, `ldap_idmigrate`, `saml_auth_data_reset` |

\* Enterprise/admin tools are present but several require an enterprise license or local mode;
the chat-operation tools (posts/channels/users/teams/bots/webhooks/search) are what this
task's agent actually uses over the remote context.

> **Scope note:** this MCP server is **read+write admin** over the whole workspace — far
> broader than the incident-response task needs. For a tightly-scoped eval you'd either trim
> the tool set or rely on the task instruction + verifier to define the objective (as here).
