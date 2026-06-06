# Creating a new task

Every task here follows the same shape: a realistic seeded workspace, a single **injected
fault**, a **vague instruction**, a reference **oracle** fix, and a **verifier** that reads the
result back over REST. Because the service image is identical across tasks, authoring a new one
means changing only a few small files.

## What types of tasks fit

Anything an admin can break and fix in a Mattermost workspace, where the fixed state is checkable
over the REST API. Some ideas, by tool group:

- **Users** — deactivated user, user removed from a team/channel, wrong email/username.
- **Channels** — archived channel, channel that should be public but is private, missing channel.
- **Roles/permissions** — a user who should be admin isn't; a role missing a permission.
- **Config** — a server setting flipped the wrong way (file uploads, sign-up, message retention…).
- **Bots / webhooks** — a disabled integration bot, a missing/incorrect webhook.
- **Posts / channels content** — required message missing, something needs to be posted/pinned.

The "observability" flavor comes from giving the agent only the **symptom** and making the broken
state **hidden from the default view**, so it has to explore the right tool/flag to find it.

## Anatomy of a task

```
tasks/<name>/
  task.toml            # Harbor task config (incl. the MCP server registration)
  instruction.md       # the symptom only — minimal hand-holding
  environment/
    Dockerfile                 # client image (slack facade over mmctl/mmctl-mcp) — copy as-is
    client-entrypoint.sh       # authenticates the connection, waits for seed     — copy as-is
    slack                      # the `slack` CLI (Slack Web API style)            — copy as-is
    slack-mcp.sh               # the `slack` MCP launcher                         — copy as-is
    docker-compose.yaml        # client + mattermost                              — copy as-is
    mattermost/
      Dockerfile               # service image                    — copy as-is
      entrypoint.sh            # boot + seed + run fault.sh        — copy as-is
      seed.py                  # workspace seeder                  — copy as-is
    data/mattermost/
      scraped.json             # the seed workspace (can be shared across tasks)
      fault.sh   ← YOU WRITE   # injects the "issue" over REST at seed time
  solution/solve.sh   ← YOU WRITE   # the oracle fix (uses the `slack` tool)
  tests/
    test.sh                    # orchestrator                     — copy as-is
    run_verifier.sh ← YOU WRITE  # reads state back over REST, writes reward
```

To create a task, **copy an existing one** (e.g. `responder-lockout`) and edit four files:
`instruction.md`, `data/mattermost/fault.sh`, `solution/solve.sh`, `tests/run_verifier.sh`
(plus the `name`/`description` in `task.toml`). Everything else is identical boilerplate.

## The four files you write

**1. `data/mattermost/fault.sh`** — runs *inside the mattermost container* at seed time (server
on `localhost:8065`). Log in as admin, then break one thing over REST:

```bash
TOK="$(curl -s -i -X POST http://localhost:8065/api/v4/users/login -H 'Content-Type: application/json' \
  -d '{"login_id":"admin@demo.local","password":"AdminUser123!"}' | tr -d '\r' | awk 'tolower($1)=="token:"{print $2}')"
# ... use $TOK to deactivate a user / archive a channel / flip a config flag ...
```

**2. `instruction.md`** — state only the **symptom** and that the agent has the `slack` tool
(CLI + MCP). Do not reveal the root cause or the method to run.

**3. `solution/solve.sh`** — the oracle, runs *in the client* with the `slack` tool ready:

```bash
slack admin.users.setActive carol true   # whatever single `slack` method fixes the fault
```

If your fix needs a `slack` method that doesn't exist yet, add it to the `environment/slack`
wrapper (map it to the right `mmctl`/REST call) and keep the agent-facing name Slack-flavored.

**4. `tests/run_verifier.sh`** — runs *in the client*, logs in as admin, reads the fixed state
over REST, and writes `0`/`1` to `/logs/verifier/reward.txt`. Keep the check **outcome-based**
(does the end state match?) so any valid fix the agent finds passes.

## Two rules that keep it reliable

- **Seed entities via REST, mutate via REST.** If your fault or fix touches users/channels/roles,
  make sure those entities were created through the API (the shared `seed.py` already does this).
  Raw-SQL entities don't respond correctly to app-level operations — see
  [ENVIRONMENT.md](ENVIRONMENT.md).
- **Key the reward on the *fixed* state, set the *broken* state at seed time.** That guarantees a
  no-op agent scores 0 and the oracle scores 1.

## Validate before shipping

```bash
cd tasks/<name>/environment
docker compose up -d --build
docker cp ../tests client:/tests && docker cp ../solution client:/solution
docker compose exec -T client bash /tests/run_verifier.sh    # expect reward=0 (fault present)
docker compose exec -T client bash /solution/solve.sh
docker compose exec -T client bash /tests/run_verifier.sh    # expect reward=1 (fixed)
docker compose down -v
```

Then add the task name to `oddish/manifest.yaml` and `oddish/sweep.yaml`.

## Harbor compatibility checklist
- `task.toml` validates against Harbor's model (the `mcp_servers` entry uses `name` / `transport
  = "stdio"` / `command` / `args`).
- The build context is self-contained (no references outside the task dir).
- The compose file has **no explicit `networks:`** and pins `platform: linux/amd64`.
- `nop` → 0 and `oracle` → 1 both verified locally.
