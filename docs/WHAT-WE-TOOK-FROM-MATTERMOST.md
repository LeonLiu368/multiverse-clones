# What we took from Mattermost (and the tradeoffs)

The guiding idea: **reuse real Mattermost for the chat functionality, but present it to the agent
as a realistic Slack Web API** — so we don't reimplement a chat backend, yet the agent gets a
believable Slack with no "it's Mattermost / it's a sim" tells.

## The inventory

| Taken | From | Used as |
|---|---|---|
| `mattermost/mattermost-team-edition:8.1.1` + embedded Postgres | Docker Hub | the chat **backend** (channels, threads, users, posts, search) — bound to `127.0.0.1`, never exposed |
| **REST API v4** | the running server | what our gateway calls to do the real work; also how `seed.py` builds the workspace |
| (nothing else) | — | the agent's Slack surface is our own thin gateway, not any Mattermost tool |

What we **own** is small: the Slack Web API **gateway** (`slackgw/`, ~250 lines), a `seed.py`
chat seeder, the entrypoints, and the tasks. Everything hard — the chat product — is reused.

> Earlier iterations exposed Mattermost's own `mmctl` CLI and the `mmctl-mcp` server to the agent.
> Those are **no longer used**: a bespoke CLI is a simulation tell, and `mmctl` couldn't be made
> to look like Slack. The current design gives the agent the **real Slack Web API** (curl +
> official `slack_sdk`) instead, with Mattermost sealed behind the gateway.

## The Slack gateway (the fidelity layer)
`slackgw/app.py` (FastAPI) implements the task-scoped Slack methods and translates them to
Mattermost `/api/v4`, returning faithful Slack shapes (`{"ok":...}` envelope, `C…`/`U…` ids, `ts`
strings, cursor fields, snake_case errors), validating an `xoxb-` token, and scrubbing
backend/framework headers. It self-authenticates to Mattermost internally; the agent never sees
the Mattermost token, port, `/api/v4`, or headers. See [TOOLS.md](TOOLS.md).

## Tradeoffs of this approach
**Buys us**
- A real, battle-tested chat backend (threads, reactions, DMs, search) for almost no code.
- A **realistic Slack surface** the agent uses the real way (`slack_sdk`) — no bespoke-tool tell.
- **Isolation**: Mattermost is unreachable from the agent; no Slack-vs-Mattermost tells survive
  basic recon (port/headers/paths all hidden).

**Costs**
- The gateway is **task-scoped** Slack fidelity, not the whole Slack API — extend it per method as
  new tasks need (it's a thin translation, not a from-scratch store).
- Heavyweight backend: the Mattermost image is large and boot takes ~30–45 s (Postgres + server +
  seed).
- amd64-only (Mattermost), so both services pin `platform: linux/amd64` (native on Modal).
- Some Slack concepts don't map perfectly to Mattermost (ids are synthesized, not Slack's real
  format/length) — fine for agents, who don't know real Slack ids a priori.

## When to prefer the from-scratch clone instead
Use the Slack clone (other branch) if you need **byte-for-byte Slack-API parity** (real SDK edge
cases, exact id formats) or a tiny/fast service. Use this branch for a **realistic, full-featured
chat backend with strong isolation** and minimal code to own.
