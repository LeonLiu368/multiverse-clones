# Seed Dashboard

A local tool to **see the data seeded into a service clone** — exactly as an agent's tools would
see it. It reproduces, on the host, how a Harbor/Oddish task assembles its workspace (pick a base
seed image → mount a per-task overlay → merge) and renders the result in a Slack-fidelity web UI
inside an app-launcher shell ("dashboard of apps") that extends to future clones.

Today there is no window into a seeded clone except the agent's own tool calls. This makes authoring
tasks and debugging clone bugs slow and blind. The viewer gives you eyes on the merged workspace.

## How it works (Slack)

The backend imports the Slack clone's own
`store.py` (reads) and `import_export.py` (merge) from the checkout on disk, so what the viewer shows
is byte-for-byte what the agent's CLI/MCP/HTTP tools return. Nothing is vendored → zero drift.

The seed process mirrors the clone's `slack-boot.sh`:

1. **Base corpus** — a baked SQLite DB extracted from a docker image (`slack-gateway:prod-v1` at
  `/opt/slack.prebuilt.db`, or `slack-seed:<dataset>` at `/slack.prebuilt.db`), or imported from a local Slack-export dir.
2. **Overlay** — a per-task Slack-export directory

## Scaling to other clones

`backend/adapters/base.py` defines a `CloneAdapter` protocol; routes and the frontend shell speak
only its normalized vocabulary (`containers`, `entities`, `messages`, `thread`, `search`). A new
clone (gh-clone, linear, ticketvector) ships **one** `adapters/<clone>.py` + **one** `apps/<clone>/`
view — no route or shell changes. `adapters/echo.py` is a fixture adapter that proves this: it shows
up and renders through the generic routes with zero wiring (see the test).

## Run

```bash
./run.sh                 # backend :8000 + frontend :5273 — open http://localhost:5273
# or point at a different clone checkout:
SLACK_CLONE_BASE=/path/to/abundant-slack-clone-mattermost/selfcontained/base ./run.sh
```

In the UI: open **Slack** → pick a **Base** (e.g. `slack-gateway:prod-v1`) → optionally **Choose
overlay folder** (a task's `environment/data/overlay`, uploaded from the browser) → **Load**.
Messages that come from the task overlay (not the base image) carry a small green **overlay** tag;
channels with overlay content are flagged in the sidebar. **Pull GHCR** fetches a registry tag on
demand.

### Editing the overlay

You can build/edit the overlay in place and download it: **+** next to "Channels" adds an overlay
channel, the **compose bar** adds an overlay message (author, text, optional date + time pickers),
and 🗑 removes an overlay channel/message. Every edit lands on the **overlay (task-seed) layer
only** — the server refuses to delete base corpus/image data.

**⬇ export dir** prompts for a directory name and downloads the edited overlay as a **zipped Slack-
export directory** (`<name>/channels.json`, `users.json`, `<channel>/<YYYY-MM-DD>.json`) — the exact
shape `import_export.py` / a task's `environment/data/overlay` expects, so it drops straight into a
task. (A raw `GET /overlay/export` JSON endpoint in `write_export` input shape is also available.)

### Building a workspace from scratch — the empty base image

`ghcr.io/abundant-ai/slack-gateway:empty` is an **empty workspace** (0 channels/users). Load it as
the Base, then add channels/messages with the editor and **export dir** to author a brand-new
overlay corpus with no base data underneath. Built host-side (empty SQLite baked onto the standard
`slack-seed` → `slack-gateway` images) so there's no amd64-emulation step.

### Loading a specific task / run

The bulk of the data lives in the **gateway sidecar** image (`ghcr.io/abundant-ai/slack-gateway:<task>`), not in
the `main`/agent image (somewhere like `ghcr.io/abundant-ai/experiments/<task>:run-<id>`), which is tools + codebase
only and carries no DB. Pull the sidecar tag — the viewer extracts its base DB **and** its baked
`/data/slack-overlay`, auto-merging them so you see the task's real seeded state from one image, no
separate overlay needed.

The clone images are published **linux/amd64-only**; on Apple Silicon a plain `docker pull` fails
with *"no matching manifest for linux/arm64"*. The viewer always pulls/extracts with
`--platform linux/amd64` (it only copies a file out, never runs the container), so this is handled.

## Layout

```
backend/
  app.py                 # generic, clone-agnostic FastAPI routes
  clone_bridge.py        # imports the clone's store/import code via SLACK_CLONE_BASE
  dockerutil.py          # list/pull images, extract baked SQLite DB
  adapters/
    base.py              # CloneAdapter protocol (the extension point)
    slack.py             # Slack adapter
    echo.py              # mock test adapter
  test_seed.py
frontend/                # React + Vite + TS
  src/App.tsx            # launcher shell
  src/apps/slack/        # Slack-fidelity view
  src/apps/GenericApp.tsx
```

## Test

```bash
cd backend && SLACK_CLONE_BASE=/path/to/clone/selfcontained/base .venv/bin/python -m pytest -v
```

## Requirements

- Python 3.11+, Node 18+, Docker (only for image-backed bases — local export dirs need no Docker).
- A Slack clone checkout (default `~/projects/abundant-slack-clone-mattermost`, override with
`SLACK_CLONE_BASE`).

