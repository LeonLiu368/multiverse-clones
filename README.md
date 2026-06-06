# Mattermost observability tasks (for Harbor / Oddish)

> **Branch:** `mattermost-focused-implementation`. This branch builds agent-evaluation tasks
> on top of the **real Mattermost product** instead of a from-scratch chat clone. (The
> from-scratch Slack clone lives on the `slack-focused-implementation` branch / `main`.)

This repo holds a small suite of **"there's an issue, go fix it"** tasks that run an AI agent
against a real, seeded **Mattermost** team-chat server. The agent is told *only the symptom*
and *which tools it has* — it has to explore, diagnose the root cause, and fix it. A verifier
then checks the result automatically.

Everything runs as a **multi-container Harbor task** and is **Oddish-runnable** out of the box.

---

## What this is, in one picture

```
   ┌────────────────────────── one Harbor task ──────────────────────────┐
   │                                                                       │
   │   ┌──────────────────┐         HTTP (REST)        ┌────────────────┐  │
   │   │  client          │  ───────────────────────►  │  mattermost    │  │
   │   │  (the agent)     │     http://mattermost:8065 │  real product  │  │
   │   │                  │  ◄───────────────────────  │  + Postgres    │  │
   │   │  tool: `slack`   │                            │                │  │
   │   │   • slack CLI    │                            │  seeded with a │  │
   │   │   • slack MCP    │                            │  workspace +   │  │
   │   │  (thin facade    │                            │  an injected   │  │
   │   │   over mmctl)    │                            │  "fault"       │  │
   │   └────────┬─────────┘                            └────────────────┘  │
   │            │ after the agent acts, the verifier (in the client)        │
   │            ▼ reads workspace state back over REST and scores 0 or 1     │
   │     /logs/verifier/reward.txt                                          │
   └───────────────────────────────────────────────────────────────────────┘
```

Two containers per task:
- **`mattermost`** — the real Mattermost server (team edition 8.1.1) with embedded Postgres,
  seeded at startup with a believable workspace, then a small **fault** is injected (the
  "issue" the agent must fix).
- **`client`** — where the agent lives. It gets a single, **Slack-branded** tool called
  **`slack`**, in two interchangeable forms: a `slack` **CLI** (Slack Web API-style methods like
  `conversations.list`, `chat.postMessage`, `users.info`) and a `slack` **MCP** server. Both are
  a thin facade over the real Mattermost tooling (`mmctl` / `mmctl-mcp`) underneath — so to the
  agent the environment looks like Slack, while the backend is real Mattermost.

The agent never sees the seed data on disk — it can only reach the workspace through the `slack`
tool, exactly like a real admin. That's what makes scoring trustworthy.

---

## The tasks

Each task gives the agent a vague symptom and minimal hand-holding. The agent must figure out
which tool/flag surfaces the problem, then remediate it.

| Task | Symptom the agent is told | Root cause (hidden) | Fix |
|---|---|---|---|
| **responder-lockout** | "`carol` suddenly can't access the workspace." | her account was deactivated | reactivate her |
| **archived-channel** | "The `#deploys` channel vanished." | it was archived | unarchive it |
| **file-sharing-broken** | "Nobody can upload/share files anywhere." | file attachments disabled server-wide | re-enable the setting |

All three are validated to score **0 for a no-op agent** and **1 for the reference solution**.

→ Details on writing your own: **[docs/CREATING-TASKS.md](docs/CREATING-TASKS.md)**

---

## What we took from Mattermost (and why)

The whole point of this branch is **reuse**: instead of building a chat backend, a CLI, and an
MCP server, we take them straight from the Mattermost ecosystem.

| Taken | Used as | What it saved us |
|---|---|---|
| `mattermost/mattermost-team-edition:8.1.1` Docker image | the chat **service** | a full product: channels, threads, reactions, DMs, users, roles, config, REST API |
| **`mmctl`** (copied from the image, exact version) | the engine behind the `slack` **CLI** | a real admin CLI — no hand-written tool |
| **`mmctl-mcp`** (built from pinned source, 1-line patch) | the engine behind the `slack` **MCP** server | a real MCP surface — no hand-written MCP server |
| **REST API v4** | the **verifier's** read-back channel (and the `slack` CLI's diagnostic reads) | deterministic scoring with no custom query layer |
| Embedded-Postgres boot pattern (from APEX-SWE) | the service **entrypoint** | a working single-container DB+server |

The agent doesn't see any of these names — they sit behind the **`slack`** facade (see below).

→ Full reuse inventory + tradeoffs: **[docs/WHAT-WE-TOOK-FROM-MATTERMOST.md](docs/WHAT-WE-TOOK-FROM-MATTERMOST.md)**
→ The `slack` tool surface (CLI methods + MCP), and how it maps down: **[docs/TOOLS.md](docs/TOOLS.md)**

**The one tradeoff worth knowing up front:** the Slack surface is a *lightweight facade* — Slack
method names and Slack-shaped JSON over a Mattermost backend, not a byte-for-byte Slack API. The
product image is also amd64-only (we pin `platform: linux/amd64`; Modal runs amd64 natively). In
exchange we get a real, full-featured chat server and real tooling for almost no code.

---

## How the environment works (short version)

1. **Build & upload.** Oddish uploads only the task folder; everything needed to build both
   images lives inside `environment/`. The `mmctl-mcp` server is compiled from a pinned commit
   during the build.
2. **Seed.** The `mattermost` container boots Postgres + the server, then a Python seeder
   creates a workspace (admin, team, channels, users, message history).
3. **Inject the fault.** A per-task `fault.sh` then breaks one thing over the REST API (e.g.
   deactivates a user). This is the "issue."
4. **Wire the client.** Once the server is healthy, the `client` container authenticates the
   workspace connection and waits until it's ready, so the `slack` CLI and `slack` MCP server
   work the moment the agent arrives.
5. **Agent acts.** The agent reads `instruction.md`, explores with the `slack` tool (CLI or MCP),
   and fixes the issue.
6. **Verify.** A verifier in the client reads the workspace back over REST and writes `0` or
   `1` to `/logs/verifier/reward.txt`. `nop` (do nothing) → 0; `oracle` (reference fix) → 1.

→ Full lifecycle, container comms, seeding, and fault injection: **[docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)**

---

## Run it

```bash
# With Oddish (uses the sweep config)
cd /path/to/oddish/oddish
uv run oddish run /path/to/this-repo/oddish/tasks -c /path/to/this-repo/oddish/sweep.yaml

# Locally, to validate one task end-to-end (first build pulls the Mattermost image; ~5-8 min)
cd oddish/tasks/responder-lockout/environment
docker compose up -d --build            # mattermost goes healthy; fault is injected
docker cp ../tests client:/tests && docker cp ../solution client:/solution
docker compose exec -T client bash /tests/run_verifier.sh    # nop    -> reward 0
docker compose exec -T client bash /solution/solve.sh
docker compose exec -T client bash /tests/run_verifier.sh    # oracle -> reward 1
docker compose down -v
```

## Repo layout

```
oddish/
  manifest.yaml          # task list + agents (create-oddish-task format)
  sweep.yaml             # oddish CLI sweep config
  tasks/
    responder-lockout/   ┐
    archived-channel/    ├─ one self-contained Harbor task each (see docs/CREATING-TASKS.md)
    file-sharing-broken/ ┘
docs/
  ENVIRONMENT.md                    # how the setup works, start to end
  WHAT-WE-TOOK-FROM-MATTERMOST.md   # reuse inventory + tradeoffs
  TOOLS.md                          # the full agent tool surface
  CREATING-TASKS.md                 # how to author a new task
```
