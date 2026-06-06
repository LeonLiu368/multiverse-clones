# What we took from Mattermost (and the tradeoffs)

The guiding idea of this branch is **be lazy: reuse real Mattermost code instead of building a
chat service, a CLI, and an MCP server ourselves.** This doc lists exactly what we took, what
we changed, and the tradeoffs that come with reuse.

## The inventory

| Taken | From | Used as | Replaces (what we'd otherwise build) |
|---|---|---|---|
| `mattermost/mattermost-team-edition:8.1.1` image | Docker Hub (official) | the chat **service** | an entire chat backend: channels, threads, reactions, DMs, users, roles, server config, full REST API v4 |
| **`mmctl`** binary | copied out of the image (`/mattermost/bin/mmctl`) | engine behind the `slack` **CLI** | a hand-written admin CLI |
| **`mmctl-mcp`** | `github.com/mattermost/mmctl-mcp` (pinned commit, built from source) | engine behind the `slack` **MCP** server | a hand-written MCP server |
| **REST API v4** | the running server | the **verifier's** read-back channel | a custom state-inspection layer |
| Embedded-Postgres entrypoint pattern | adapted from APEX-SWE's Mattermost setup | the service **boot sequence** | a working DB+server-in-one-container script |
| Seed format `{messages:[{channel,author,content,timestamp}]}` | APEX-SWE convention | the **seed** input | a bespoke seed schema |

The net result: the only code we actually *own* is a ~150-line Python seeder, a handful of
small shell scripts (entrypoints, fault injectors, verifiers, and the `slack` facade), and the
task definitions. Everything that is hard — the chat product and the agent tooling — is reused.

**The `slack` facade.** The agent never sees `mmctl`/`mmctl-mcp` or "Mattermost". A thin
`slack` wrapper (CLI + MCP) presents Slack Web API-style methods and Slack-shaped output and maps
them down to the reused tooling, so the environment *looks like Slack* to the agent. This is a
**lightweight rename**, not a byte-for-byte Slack API — see [TOOLS.md](TOOLS.md).

## What we changed (and why)

Only one real patch was needed:

- **`mmctl-mcp` forced `mmctl --local`.** Upstream hard-codes "local mode", which talks to the
  server over a **unix socket on the server's own host**. In our setup the MCP server runs in
  the *separate* `client` container, where that socket doesn't exist. We apply a **one-line
  patch** (drop the forced `--local`) so every tool uses `mmctl`'s **remote auth context** —
  plain TCP to `http://mattermost:8065`. That's the same transport the CLI and the verifier
  already use, and the only option that's portable to Harbor/Modal (where containers don't
  share a host filesystem).

Two seeding choices are also worth calling out (details in
[ENVIRONMENT.md](ENVIRONMENT.md)):

- **Channels and users are created via REST, not raw SQL**, so the running server's caches know
  about them and admin operations (list, deactivate, role change) actually work.
- **Posts are inserted via SQL**, only to preserve original timestamps.

## Tradeoffs of reuse

**What reuse buys us**
- A real, battle-tested chat product — threads, reactions, DMs, roles, config, search, bots,
  webhooks all exist for free.
- Real agent tools (`mmctl`, `mmctl-mcp`) instead of approximations, so the eval reflects how an
  agent does on *actual* tooling.
- A stable REST API for deterministic verification.

**What reuse costs us**
- **Not Slack-API shaped.** Mattermost's API/CLI are its own; agents' Slack-SDK knowledge does
  not transfer. (If you specifically need Slack-API fidelity, that's what the from-scratch clone
  branch is for.)
- **Heavyweight.** The image is large (~500 MB) and boot takes ~30–45 s (Postgres + server +
  seed), vs. seconds for a lightweight clone.
- **amd64-only.** Mattermost and `mmctl` are published for amd64 only, so we pin
  `platform: linux/amd64` (emulated on Apple-Silicon dev machines; native on Modal).
- **Broad admin tool surface.** `mmctl-mcp` exposes ~65 mostly-admin tools — far more than any
  single task needs. We scope the objective through the task instruction + verifier rather than
  by trimming tools (see [TOOLS.md](TOOLS.md)).
- **License ambiguity.** `mmctl-mcp` has no SPDX-detected license. Fine for internal evaluation;
  revisit before any redistribution.
- **Cache quirks with direct DB writes.** Seeding via raw SQL fights the server's caches; we
  worked around it by creating users/channels through the API (above).

## When to prefer the from-scratch clone instead
Use the Slack clone (other branch) when you need **Slack-API compatibility** (real Slack SDKs,
Slack-shaped JSON), a **tiny/fast** service, or a **tightly-scoped** tool surface you fully
control. Use this Mattermost branch when you want a **realistic, full-featured** chat backend
and **real agent tooling** with minimal code to maintain.
