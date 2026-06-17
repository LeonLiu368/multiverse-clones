---
name: slack-clone-task-builder
description: >
  Author a Harbor/Oddish agent-eval task that runs against the Slack clone. Covers (1) the Slack
  export data format and how to seed per-task data as an overlay on the shared "prod" corpus, and
  (2) the exact docker-compose / Dockerfile / task.toml / verifier files a Slack-backed task needs.
  Use whenever building, seeding, or debugging a task where the agent reads a realistic Slack
  workspace through the `slack` CLI / `slack-mcp` MCP and a verifier grades the result.
---

# Building a task on the Slack clone

## Mental model (read this first)

A Slack task runs as **two containers**:

```
┌────────────────────────────┐        ┌─────────────────────────────────────┐
│  main  (the agent)         │  HTTP  │  slack  (the workspace)             │
│  • slack CLI               │ ─────► │  • Slack Web API gateway (:80)      │
│  • slack-mcp (MCP server)  │        │  • SQLite DB = the chat data        │
│  • your codebase           │        │  • prod corpus + your task overlay  │
│  • NO data on disk         │        │                                     │
└────────────────────────────┘        └─────────────────────────────────────┘
        SLACK_API_URL=http://slack
```

- The `slack` sidecar holds **all** the chat data and serves a faithful subset of the Slack Web API.
  The agent can reach it **only over HTTP through the tools** — it cannot read the data off disk, so
  it can't cheat the grader.
- **Use ONE of two shared sidecar images — never build a per-task gateway image.** Your per-task
  data is delivered by **mounting** it into the chosen sidecar (Harbor honors sidecar `volumes:`;
  `figma-linear` does the same). `slack-boot` imports the mounted data at startup.
- The agent operates the workspace with the **`slack` CLI** and the **korotovsky `slack-mcp`** MCP
  server (both thin HTTP clients of the gateway). A verifier in `main` grades the result.

The only images you ever reference (all public on GHCR `ghcr.io/abundant-ai/`):
| image | what it is | per-task data |
|---|---|---|
| `slack-agent:slack-mcp-oss` | thin agent base (CLI + MCP, no data) — task `main` builds FROM this | — |
| `slack-gateway:prod-v1` | **shared** prod gateway + real corpus (88 channels, ~2.4M msgs, named users) | mount your **overlay** at `/data/slack-overlay` (merged on top of prod) |
| `slack-gateway:empty` | **shared** blank gateway (no data) | mount your **full small export** at `/data/slack-export` (becomes the whole workspace) |

Pick `prod-v1` when your task should live inside the big realistic corpus (plant a few messages on
top); pick `empty` when you want a clean, fully-custom mini-workspace. **Do not create new images.**

The clone source + helpers live in the `abundant-slack-clone-mattermost` repo under
`selfcontained/base/` (importer, `slack_export_writer.py`) and `selfcontained/prod/v1/catalog/`
(the author "directory" of real channels/users for `prod-v1`).

---

# Part 1 — Slack export format & seeding task data

## 1a. The Slack export format

A Slack export is a **directory** shaped exactly like this:

```
export/
├── channels.json                    # array of channel objects
├── users.json                       # array of user objects
├── engineering/                     # one folder per channel (folder name == channel name)
│   ├── 2025-12-18.json              # one file per day, an ARRAY of message objects
│   └── 2025-12-19.json
└── deploys/
    └── 2025-12-19.json
```

**`channels.json`** — `[{ ... }]`:
```json
{
  "id": "C72917EF6C1", "name": "engineering",
  "created": 1614971255, "creator": "U0123ABC",
  "is_archived": false, "is_general": false,
  "members": ["U0123ABC", "U0456DEF"],
  "topic":   {"value": "", "creator": "", "last_set": 0},
  "purpose": {"value": "", "creator": "", "last_set": 0}
}
```

**`users.json`** — `[{ ... }]`:
```json
{
  "id": "U0123ABC", "team_id": "T0EXACME01", "name": "alex.okafor",
  "real_name": "Alex Okafor", "is_bot": false, "deleted": false,
  "profile": {"display_name": "Alex", "real_name": "Alex Okafor", "email": ""}
}
```

**`<channel>/<YYYY-MM-DD>.json`** — an **array** of messages:
```json
[
  {
    "type": "message",
    "user": "U0123ABC",
    "ts": "1766248200.000000",          // "<10-digit seconds>.<6-digit microseconds>" — STRING, unique per (channel, ts)
    "text": "fix is now live in production",
    "user_profile": {"name": "alex.okafor", "real_name": "Alex Okafor", "display_name": "Alex"},
    "thread_ts": "1766248100.000000",   // optional — present on threaded replies (== parent ts)
    "reactions": [{"name": "tada", "users": ["U0456DEF"], "count": 1}],  // optional
    "subtype": "channel_join"           // optional — system messages
  }
]
```

Notes that matter:
- **`ts` is a 10-digit-seconds string.** History and search sort lexicographically on it, which is safe
  for any real date (the 10-digit band runs 2001–2286). Keep them 10-digit.
- **IDs are content-hashed.** The importer maps any id/name to `C…`/`U… = "C"/"U" + sha1(name)`. The
  practical upshot for *you*: **a channel/user referenced by the same NAME resolves to the same ID** —
  this is what lets an overlay merge into a real prod channel (see 1c).
- Two real-world variants exist: a *complete* export (has `channels.json`/`users.json`) and an
  *anonymized* one (top-level files stripped, names like `[PERSON_NAME_1234]`). The importer handles
  both and can synthesize names (`--names synthetic`). You normally don't touch this — it's already
  baked into `prod-v1`.

## 1b. The seeding model: prod corpus + per-task overlay

You do **not** rebuild the big corpus. You write a **small overlay** — a Slack export folder
containing only your planted message(s) — and it is merged ON TOP of `prod-v1` at startup
(`import_export.py --overlay`, which preserves existing prod rows and adds yours).

Two hard rules for overlays:
1. **Attach to a prod channel/user by NAME.** Put your message in a folder named exactly like a real
   prod channel (e.g. `engineering/`) and the content hash makes it land *in that real channel*. Pick
   channels/users from the catalog (`selfcontained/prod/v1/catalog/{channels.json,users.json}`).
2. **Timestamp AFTER the corpus tail.** `prod-v1` ends **2025-12-19**. Date overlay messages just
   after (e.g. `2025-12-20`) so they're the most recent activity and never collide on `(channel, ts)`.

## 1c. Authoring the overlay

Use the helper `slack_export_writer.write_export()` (in `selfcontained/base/`). It turns a plain list
into a correct export dir (deterministic ids, Slack `ts`, threads):

```python
import sys; sys.path.insert(0, "<repo>/selfcontained/base")
import slack_export_writer as sw

sw.write_export([
    {"channel": "engineering",          # a REAL prod channel name -> merges into it (or a new name -> new channel)
     "author":  "robin.vega",           # a person handle; new handle -> new user, existing handle -> that user
     "content": "heads up — the v9.0.0 release goes live December 22.",
     "timestamp": "2025-12-20T16:30:00Z",   # AFTER the corpus tail (2025-12-19)
     # "thread_key": "t1",              # optional: group messages into a thread (earliest = parent)
    },
], "environment/data/overlay")          # writes channels.json/users.json/<channel>/<date>.json
```

Commit the generated `environment/data/overlay/` directory — that folder is the artifact that gets
baked into the sidecar. To change the overlay, re-run `write_export()`; don't hand-edit the JSON
(the ids and `ts` must stay consistent). If you want a record of how it was authored, keep the
`write_export([...])` call in the task.toml description or a comment — you don't need a separate
script.

## 1d. Deliver the overlay by MOUNTING it (no per-task image)

Do **not** build a per-task image. Commit `environment/data/overlay/` and **mount** it into the
shared sidecar in the compose (see Part 2):

```yaml
  slack:
    image: ghcr.io/abundant-ai/slack-gateway:prod-v1   # shared image, used as-is
    volumes:
      - ./data/overlay:/data/slack-overlay:ro          # your overlay, mounted in
```
`slack-boot.sh` inside the sidecar imports `/data/slack-overlay` on top of the prod DB at startup
automatically. For an **`empty`**-based task, instead author a full small export under
`environment/data/slack-export/` and mount it at `/data/slack-export` — it becomes the whole
workspace. Either way: zero images to build or push; the agent's container never sees the mount.

## 1e. What the agent (and your oracle/verifier) can call

All over HTTP at `http://slack`, `Authorization: Bearer xoxp-acme-eval-0001`:
`conversations.list`, `conversations.info?channel=`, `conversations.history?channel=&limit=`,
`conversations.replies?channel=&ts=`, `search.messages?query=`, `users.list`, `users.info?user=`,
`team.info`, `chat.postMessage` (write tasks).
**Search supports** multi-term (ANDed), `"quoted phrases"`, and operators `in:#channel`,
`from:@user`, `before:/after:/on:YYYY-MM-DD`. Channels resolve by name or id; the channel column in
search results carries the channel id.

---

# Part 2 — Docker & task setup files

A task is a directory with this exact layout (this is the Harbor task contract):

```
<task-name>/
├── task.toml
├── instruction.md
├── environment/
│   ├── Dockerfile
│   ├── docker-compose.yaml
│   ├── .dockerignore
│   ├── codebase/                 # the agent's /workspace (a README placeholder for pure read tasks)
│   └── data/
│       └── overlay/              # the per-task overlay export (Part 1) — MOUNTED into the sidecar
│                                 #   (for an `empty`-based task: data/slack-export/ instead)
├── tests/
│   ├── test.sh                   # REQUIRED Harbor entrypoint -> writes /logs/verifier/reward.txt
│   ├── run_verifier.sh
│   └── verify.py
└── solution/
    └── solve.sh                  # the oracle (must score reward=1)
```

### environment/Dockerfile
```dockerfile
# main = thin agent (slack CLI + MCP) + the codebase. No gateway, no data.
FROM ghcr.io/abundant-ai/slack-agent:slack-mcp-oss
COPY codebase /workspace
```

### environment/docker-compose.yaml
```yaml
# Two services. The sidecar is one of the two SHARED images (prod-v1 here, or :empty); the per-task
# data is MOUNTED in — no per-task image. NO `networks:` block (the runtime injects network_mode on
# main; service-name DNS still resolves `slack`).
services:
  main:
    build: { context: ., dockerfile: Dockerfile }
    image: ${APEX_TASK_DOCKER_CLIENT_IMAGE_NAME:-<task-name>-main:local}
    platform: linux/amd64
    environment:
      SLACK_API_URL: http://slack
      SLACK_BOT_TOKEN: xoxp-acme-eval-0001
    depends_on:
      slack: { condition: service_healthy }
  slack:
    image: ${SLACK_GATEWAY_IMAGE:-ghcr.io/abundant-ai/slack-gateway:prod-v1}   # shared; or :empty
    platform: linux/amd64
    volumes:
      - ./data/overlay:/data/slack-overlay:ro    # prod-v1: overlay merged on top
      # for :empty instead ->  - ./data/slack-export:/data/slack-export:ro     # full custom workspace
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:80/api/auth.test >/dev/null || exit 1"]
      interval: 5s
      timeout: 5s
      retries: 90
      start_period: 30s
```

### environment/.dockerignore
```
**/__pycache__
**/*.pyc
**/.venv
**/.git
```

### task.toml
```toml
schema_version = "1.2"
name = "<experiment>/<task-name>"
description = "One paragraph: what the agent must do, where the planted info lives, the expected answer, nop=0/oracle=1."

[metadata]
category = "tool-use"          # or "swe" if there's a codebase + pytest
service  = "slack"
tools    = ["slack-cli", "slack-mcp"]
tags     = ["slack", "read", "tool-use"]

[agent]
timeout_sec = 1800
[verifier]
timeout_sec = 300

[environment]
custom_docker_compose = true   # REQUIRED — makes Harbor honor the two-service compose
cpus = 2
memory_mb = 4096
storage_mb = 8192
allow_internet = true
workdir = "/workspace"
build_timeout_sec = 1800

[[environment.mcp_servers]]
name = "slack"
transport = "stdio"
command = "slack-mcp"
```

### tests/test.sh  (REQUIRED — Harbor's verifier entrypoint)
```bash
#!/bin/bash
set -uo pipefail
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p /logs/verifier
bash "$TESTS_DIR/run_verifier.sh"
exit 0
```

### tests/run_verifier.sh  (must write the reward to /logs/verifier/reward.txt)
```bash
#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if python3 "$TESTS_DIR/verify.py"; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
echo "reward=$(cat /logs/verifier/reward.txt)"
```

### tests/verify.py  (deterministic check — read tasks usually grade /workspace/answer.txt)
```python
import re, sys, pathlib
raw = pathlib.Path("/workspace/answer.txt").read_text().strip().lower() if \
      pathlib.Path("/workspace/answer.txt").exists() else ""
ok = raw == "18:00"          # <- your expected answer; normalize generously
print(f"answer={raw!r} ok={ok}")
sys.exit(0 if ok else 1)
```
(For SWE tasks, `verify.py`/`run_verifier.sh` instead run the hidden pytest suite and exit non-zero on failure.)

### solution/solve.sh  (the oracle — reads the workspace via the gateway, must score reward=1)
```bash
#!/bin/bash
set -uo pipefail
python3 - <<'PY'
import os, json, urllib.request, urllib.parse
BASE = os.environ.get("SLACK_API_URL", "http://localhost").rstrip("/")
TOK  = os.environ.get("SLACK_BOT_TOKEN", "xoxp-acme-eval-0001")
def call(m, **p):
    u = f"{BASE}/api/{m}?" + urllib.parse.urlencode(p)
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"Authorization": f"Bearer {TOK}"})))
# e.g. find the planted message and extract the answer
matches = (call("search.messages", query="coming in at 6pm").get("messages", {}) or {}).get("matches", [])
ans = "18:00" if matches else ""
os.makedirs("/workspace", exist_ok=True)
open("/workspace/answer.txt", "w").write(ans + "\n")
print("oracle:", ans)
PY
```

---

# Conventions & gotchas (the things that break tasks)

- **`tests/test.sh` is mandatory** and the reward must land in `/logs/verifier/reward.txt`. If it's
  missing, Harbor validation reports **"0 tasks" / HARNESS_ERROR** (it is NOT a runtime bug).
- **`custom_docker_compose = true`** in `task.toml`, or Harbor ignores the two-service compose.
- **Use a shared sidecar image — never build a per-task `slack-gateway:<task>`.** The sidecar is
  always `slack-gateway:prod-v1` or `slack-gateway:empty`; the per-task data is **mounted** in via
  `volumes:` (Harbor honors sidecar mounts — confirmed by `figma-linear`). This keeps the image
  count at two, forever.
- **No `networks:`** block in the compose.
- Overlay messages: attach **by name**, timestamp **after** the corpus tail (2025-12-19).
- The agent reaches the gateway at **`http://slack`** (set via `SLACK_API_URL`). Oracle/verifier run
  in `main` and use the same URL.
- Keep it deterministic: pick a planted fact (and any real-prod anchor) that is **unique and
  unambiguous** — the corpus is large, so verify your search returns exactly the intended message,
  or a capable model may legitimately find a competing one and "fail" a flaky task.

# Validate before shipping (local, then cloud)

1. **Local two-container smoke** (native arch): run the shared sidecar with your overlay mounted
   (`docker run -v "$PWD/data/overlay:/data/slack-overlay:ro" slack-gateway:prod-v1`), build `main`
   from the Dockerfile, put them on a docker network with `SLACK_API_URL=http://slack`, then: confirm
   the agent has **no data on disk** (`ls /opt/slack.prebuilt.db` → absent in `main`), the planted
   message is findable via `slack search`, **nop → reward 0**, **oracle (solve.sh) → reward 1**.
2. **Cloud:** push the public sidecar image, put the task under an experiment `task_path` with a
   manifest (agents `nop`, `oracle`, and a model), open a PR, comment `/oddish`. Confirm
   nop=GOOD_FAILURE, oracle=GOOD_SUCCESS, model=GOOD_SUCCESS.

A minimal manifest (`<experiment>/<experiment>-manifest.yaml`):
```yaml
metadata:
  name: <experiment>
  enable_image_push: true
  description: |
    <what the task measures>
  task_path: experiments/<experiment>/tasks
  n_trials: 1
tasks:
  - <task-name>
agents:
  - name: nop
  - name: oracle
  - name: gemini-cli
    model_name: google/gemini-3.1-pro-preview
```
