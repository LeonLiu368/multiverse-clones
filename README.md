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

## Jira (abundant-jira-clone)

A second clone, to prove the abstraction across a very different data model. The **Jira** tile loads
a ticketvector **`state.json`** (the format `abundant-jira-clone` ships) and renders it as an
**issue list + detail** view: project sidebar with status counts, a filterable issue list
(key/status/priority/assignee), and a detail panel (description + comments).

- **Store reuse:** the backend imports **ticketvector's `FakePlaneBackend`** by path
  (`TICKETVECTOR_BASE`, default `~/projects/ticketvector`) — the same code the `jira` CLI runs, zero
  drift. Base data + images come from `JIRA_DATA_BASE` (default `~/projects/abundant-jira-clone`).
- **Base seed:** a local `state.json` (`selfcontained/base/data/eng-prod-state.json`, a task's
  `tasks/*/environment/data/state.json`), the **empty** option, or a `jira-gateway` image
  (`prod-v1`/`empty`) — the viewer extracts the baked `/var/lib/ticketvector/state.json`.
- **Editor:** add issue, add comment (as an existing user), edit issue fields
  (status/priority/assignee), and delete issues/comments — **including base data** (base edits/deletes
  are recorded in the patch; the source state file is never mutated). Added rows show an `overlay`
  badge, changed base issues an `edited` badge.
- **Patch diff:** the **Changes** entry in the sidebar lists the pending diff (added/edited/deleted,
  with deleted issues as struck tombstones). **⬇ patch.json** downloads the task diff as an
  `apply_state_patch.py --patch` op-list (`{version:1, ops:[{op,entity,match,set}]}`) covering
  add/update/delete issues + add/delete comments — applied onto the base (`jira-gateway:prod-v1`) at
  task standup. (Extended the clone's `apply_state_patch.py` to support issue-add and comment-delete
  so one patch fully reproduces the edits.)

Adding it required only: one adapter (`backend/adapters/jira.py`) + a bridge function + one frontend
view (`frontend/src/apps/jira/`) + registry/launcher entries + one generic route
(`POST /overlay/op`). The other routes and the api client were reused unchanged.

## Other clones (read-only seed viewers)

Per [`clone-task-builder`](https://github.com/abundant-ai/) the remaining clones ship a single
per-task seed file (no shared prod corpus), so they get **read-only** viewers — load the seed, see it
rendered as the agent's tools would. Each is one adapter (subclassing `FileSeedAdapter`) + one view;
they expose the parsed seed through a generic `GET /api/{app}/view` instead of the chat/issue API.
Pick a bundled sample (under `samples/`) or **upload** any seed file (`POST /api/{app}/load_file`).

- **gauge** (`gauge.state.json`) — Loki/Grafana shape: a dark **log explorer** (pick a LogQL selector
  → level-colored log lines), plus dashboards (panels + exprs) and datasources.
- **Sentry** (`sentry.state.json`) — an **issue list + detail** with events and **stack traces**
  (frames + code context).
- **GitHub** (`seed.sh`) — parses the `gh` API calls into a **preview** of repos / issues / PRs (with
  nested reviews), plus the **raw script**.

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
channels with overlay content are flagged in the sidebar. Hover a message's **author name or avatar**
to see a profile card (real name, @username, email, timezone, base/overlay origin, user id). **Pull
GHCR** fetches a registry tag on demand.

### Editing the overlay

Slack uses a **two-artifact** model: bulk adds ship as a Slack-export overlay; edits/deletes of the
existing corpus ship as a patch op-list.

**Adds.** **+** next to "Channels" adds an overlay channel; the **compose bar** adds an overlay
message (author, text, optional date + time). The **author** field is a picker over existing
workspace users — choose one to post **as that user** (`as @user` hint; the server resolves the
username to the real id); an unknown name creates a new overlay user. **⬇ export dir** downloads
these as a **zipped Slack-export directory** (`<name>/channels.json`, `users.json`,
`<channel>/<YYYY-MM-DD>.json`) — the shape `import_export.py` / a task's `environment/data/overlay`
expects. (Raw JSON at `GET /overlay/export`.)

**Edit / delete messages.** Hover a message for **✎ edit** and **🗑 delete** — on **any** message,
base or overlay. Editing/deleting an overlay-added message updates the export dir; editing/deleting a
**base** message is recorded in the patch (the source corpus is never mutated). Edited base messages
show an `edited` badge. **⬇ patch.json** downloads those mutations as an `import_export.py --patch`
op-list (`{op:update|delete, entity:message, match:{channel,ts}, set:{text}}`), applied onto prod at
task standup. (Base **channels** stay delete-protected.)

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

