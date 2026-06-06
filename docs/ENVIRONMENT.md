# How the environment works (start to end)

This explains exactly what happens from the moment Oddish picks up a task to the moment a
reward is written — where the data comes from, how the two containers talk, and how the
verifier decides 0 or 1. Plain English, no prior Harbor knowledge assumed.

## The two containers

Every task is a `docker compose` project with two services:

- **`mattermost`** — the real Mattermost server (`mattermost/mattermost-team-edition:8.1.1`)
  with an **embedded Postgres** inside the same container. This is the "world" the agent
  operates on.
- **`client`** — a small Debian image where the **agent** runs. It carries the agent's
  Slack-branded tool (the `slack` CLI and `slack` MCP server, thin wrappers over `mmctl` /
  `mmctl-mcp`), **python + pytest**, and the **codebase at `/workspace`** whose test suite is
  failing — plus the verifier scripts.

They share one Docker network and find each other **by service name**: the client (via the
`slack` facade) talks to the server at `http://mattermost:8065`. We deliberately declare **no `networks:`** block in the
compose file, because the Harbor/Oddish runtime injects its own networking onto the client; an
explicit network would conflict with it. Both services pin `platform: linux/amd64` (Mattermost
and `mmctl` ship only for amd64).

## Step by step

### 1. Build & upload (self-contained)
Oddish uploads **only the task directory**. Everything needed to build both images lives inside
`tasks/<name>/environment/`:
- the `client` image's `Dockerfile` copies `mmctl` out of the Mattermost image and **compiles
  `mmctl-mcp` from a pinned commit** in a Go builder stage;
- the `mattermost` image's `Dockerfile` adds Postgres + a Python seeder to the product image.

Nothing references files outside the task folder, so the build is portable (this is what makes
it work on Modal).

### 2. The service boots and seeds itself
The `mattermost` container's entrypoint (`environment/mattermost/entrypoint.sh`):
1. starts the embedded Postgres (on port 5433, in tmpfs),
2. writes a `config.json` and launches the Mattermost server on `:8065`,
3. waits until `/api/v4/system/ping` responds,
4. runs the **seeder** (`environment/mattermost/seed.py`).

**Where the data comes from.** The seeder reads `environment/data/mattermost/scraped.json` — a
hand-authored file describing the workspace as a flat list of messages:

```json
{ "messages": [ { "channel": "incidents", "author": "carol", "content": "...", "timestamp": "2023-11-16T16:57:45+00:00" }, ... ] }
```

From that it creates: an **admin** (`admin@demo.local` / `AdminUser123!`), a **team**
(`test-demo`), the **channels** named in the file, the **users** named as authors, and the
**message history**. The seed is **heavy and noisy on purpose** (~500 messages across ~7
channels, generated deterministically by `environment/data/mattermost/generate.py`): the one
fact the agent needs is buried among distractors and **superseded** values, so finding it is
real, non-trivial tool use rather than a keyword lookup.

Two important implementation choices (learned the hard way):
- **Channels and users are created over the REST API, not raw SQL.** Raw-SQL rows exist in the
  database but the running server caches around them, so things like `channel list`, user
  *deactivation*, and role changes silently don't work. Creating them through the API makes them
  fully "app-managed" so every later operation behaves correctly.
- **Posts are inserted via SQL**, purely so we can preserve the original historical timestamps
  (the REST "create post" endpoint always stamps "now").

### 3. The "issue" = a failing codebase + a buried fact
There is **no fault script**. The broken state is baked into the **codebase** copied to
`/workspace`: a target function is unimplemented (or targets an outdated contract) so its tests
fail, while a sibling working module's tests pass. The information needed to fix it — the agreed
policy, the new contract, the incident root cause — is **not in the repo**; it lives only in the
seeded Slack history (step 2). A breadcrumb in the code (a docstring / README / `NotImplementedError`
message) points the agent at the workspace. Only the codebase + data differ per task; the
service/client images are identical.

### 4. The client wires up the agent's tools
The `client` container only starts once the server's healthcheck passes (`depends_on:
service_healthy`). Its entrypoint authenticates the workspace connection with the admin
credentials and waits until the workspace is seeded, so by the time the agent arrives the
`slack` CLI and `slack` MCP server "just work". The codebase is already at `/workspace` and
`python`/`pytest` are installed.

### 5. The agent acts
The agent reads `instruction.md` (the symptom + "you have the `slack` tool"), explores the heavy
chat with `slack` to recover the buried fact, edits the code at `/workspace`, and — for the
incident task — posts a postmortem back to Slack. See [TOOLS.md](TOOLS.md) for the surface.

### 6. The verifier scores
Harbor runs `tests/test.sh` → `tests/run_verifier.sh` **inside the client container**. It does
not trust the visible `/workspace/tests`: it copies the candidate's package **plus the trusted
tests** (the canonical invariant tests *and* a HIDDEN `test_grade_*.py` that pins the exact
answer) into a fresh **verifier-owned** dir (`/tmp/grade.$$`) and runs `pytest` there, scoring
`1` iff everything passes. Because the hidden grader's parameters appear only in Slack and the
grader is absent during the agent's run, the answer can't be read from the repo/visible tests,
and editing `/workspace/tests` can't game it. The `incident-fix-report` verifier additionally
checks (over REST) that a postmortem with the root cause was **posted to `#postmortems`** —
**both** the code fix and the communication are required. The result is written to
`/logs/verifier/reward.txt`.

> **pytest gotcha:** the hidden grader must be named `test_grade_*.py` — pytest only auto-collects
> `test_*.py`, so a `grade_*.py` silently won't run and grading would degrade to the invariants.

### 7. The reward is bracketed
Every task ships a reference `solution/solve.sh` (the **oracle**). Harbor runs each task with
two reference agents: **`nop`** (does nothing) must score **0**, and **`oracle`** must score
**1**. This proves the verifier actually distinguishes "fixed" from "not fixed". All three
tasks here pass that bracket.

## Why these choices make it a good benchmark
- **The fix-critical fact lives only in Slack, never on disk** → the agent *must* use the tool;
  the verifier's result genuinely reflects whether it did.
- **Heavy, noisy, deterministic seed** → identical starting state every run, and finding the
  fact is non-trivial (superseded values + distractors + a red herring; search is noisy).
- **Hidden grader pins the exact answer; visible tests are invariant-only** → the answer can't be
  read from the repo or visible tests; a wrong-but-plausible fix still scores 0.
- **Grading runs trusted tests in a verifier-owned dir** → editing/deleting `/workspace/tests`
  can't game it.
- **`nop`=0 / `oracle`=1 bracket on every task** (plus a wrong-impl=0 check) → catches a broken
  or gameable task immediately.
- **Action beyond coding** (incident task requires posting a postmortem) → measures tool use that
  isn't just editing files.
- **Self-contained, no explicit networks, amd64 pinned** → runs the same locally and on Modal.
