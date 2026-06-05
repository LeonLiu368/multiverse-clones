# How the Slack clone is put together (and why)

This is the plain-English tour of the system: what runs where, why the workspace
data is kept away from tasks, and how an agent is meant to interact with it. If you
just want commands, see [cli-and-db-commands.md](cli-and-db-commands.md).

## The one-sentence mental model

> The Slack clone is its **own service in its own container** with its **own data**.
> An agent can only reach that data by **using tools** — the `slack-cli` command or
> the `slack-mcp` MCP server — never by opening a file.

Everything below is in service of that sentence.

## The two containers

A task spins up two containers that talk over the network:

```
   ┌──────────────────────┐        HTTP        ┌───────────────────────────┐
   │   client (the agent) │  ───────────────▶  │  slack (the service)      │
   │   has slack-cli      │   :3000 /api/*     │  FastAPI + SQLite         │
   │   has slack-mcp      │ ◀───────────────   │  holds the workspace data │
   │   SLACK_API_URL set  │                    │ SLACK_WORKSPACE picks one │
   └──────────────────────┘                    └───────────────────────────┘
```

- `**slack**` runs the API and owns the database. It is the single source of truth.
- `**client**` is where the agent works. It has the *tools* and nothing else — no
database, no seed files, no admin token.

Because the agent only ever has tools, anything it learns about the workspace it had
to *ask the service for*. That is what makes the tasks realistic and hard to cheat.

## Where the workspace data lives (and where it doesn't)

The actual conversations — channels, users, messages — are stored as small JSON
files in the repo's top-level `**workspaces/*`* folder, one per workspace:

```
workspaces/
  acme-incident.json       # the "Acme" incident workspace
  globex-staging.json      # the "Globex" platform workspace
  hooli-decisions.json     # the "Hooli" design-decision workspace
```

These files are **baked into the `slack` service image** when it's built. They are
**never copied into a task directory**. A task doesn't ship data at all — it just
names the workspace it wants:

```yaml
# inside a task's docker-compose.yaml
slack:
  image: abundant-slack-clone:latest
  environment:
    - SLACK_WORKSPACE=acme-incident     # the ONLY per-task knob
```

When the `slack` container boots, it loads `acme-incident.json` from its baked-in
catalog into a fresh SQLite database, then starts serving. The agent's container
can't see that folder, and neither can anyone reading the task directory — because
the data simply isn't there.

This is the key change from the old design, where each task carried a copy of the
workspace next to it. Now: **canonical data in `workspaces/`, tasks stay empty.**

## Seeding "at any point": the control plane

Sometimes an operator wants to load *different* data into a **running** service —
without rebuilding or restarting. For that there's a small, private control surface:

- `POST /_control/seed` — load a workspace by name, or push raw seed JSON
- `POST /_control/reset` — reload whatever workspace the container booted with
- `GET  /_control/status` — what's loaded and what's available

This is deliberately **locked**. It only works if the service was started with a
secret token (`SLACK_CONTROL_TOKEN`), and every request must present that exact
token. If the token isn't set, these endpoints don't exist (they return "404 Not
Found"). **The agent's container is never given the token**, so even though it's on
the same network, it can't drive this surface or peek at the answer key.

Grading does **not** use the control plane — verifiers check the agent's work
through the normal public API, exactly like any other client would.

## Three ways to talk to the service, one source of truth

There are three front doors, and they all open into the same `/api/*` HTTP surface:


| Front door      | What it is                | Who uses it                           |
| --------------- | ------------------------- | ------------------------------------- |
| `**slack-cli`** | a command-line tool       | humans, shell-based agents, verifiers |
| `**slack-mcp**` | an MCP server (stdio)     | MCP-capable agents                    |
| raw **HTTP**    | the Slack-shaped REST API | SDKs, `curl`, anything                |


Because the CLI and the MCP server are both just thin clients of the HTTP API, they
**can't drift apart** — a new capability added to the API is reachable the same way
from all three. The MCP tools are named after Slack methods so they're familiar:


| MCP tool                      | CLI equivalent     | API method            |
| ----------------------------- | ------------------ | --------------------- |
| `slack_conversations_history` | `channels history` | conversations.history |
| `slack_conversations_replies` | `thread`           | conversations.replies |
| `slack_search_messages`       | `search`           | search.messages       |
| `slack_post_message`          | `post`             | chat.postMessage      |
| `slack_reactions_add`         | `react`            | reactions.add         |
| `slack_pins_add`              | `pin`              | pins.add              |
| …and so on                    |                    |                       |


The MCP server exposes **only** these read/write tools — never the control plane.

## How a task is graded

1. The `slack` service boots and seeds its named workspace.
2. The agent works, using `slack-cli` / `slack-mcp` to read and post.
3. A **verifier** script runs afterward and checks the result by querying the public
  API (e.g. "is there a message in `#incidents` naming the connection-pool cause?").
   It writes `reward = 1` for success, `0` otherwise.

A "do-nothing" run scores 0; the reference solution scores 1. Grading is
deterministic because it reads real workspace state back through the API rather than
trusting anything the agent says.

## Adding a new workspace

1. Author a canonical seed (hand-write JSON, or `slack-cli seed generate --emit …`,
  or import a real Slack export).
2. Drop it in `workspaces/<name>.json`.
3. Rebuild the `slack` image so the catalog includes it.
4. Reference it from a task with `SLACK_WORKSPACE=<name>`.

## Adding a new task

1. Copy an existing task folder under `oddish/tasks/`.
2. In its `docker-compose.yaml`, set `SLACK_WORKSPACE` to the workspace you want.
3. Write `instruction.md`, the `solution/solve.sh` (reference answer), and
  `tests/run_verifier.sh` (the check). **No data files** go in the task.

That's the whole contract: pick a workspace by name, describe the job, write the
check. The data stays in `workspaces/`, sealed behind the tools.