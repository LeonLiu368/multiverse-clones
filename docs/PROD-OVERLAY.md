# Shared prod corpus + per-task overlay

A model for Slack tasks where many tasks reuse **one large, realistic "prod" workspace** and each
task plants only its own small data on top — instead of baking a full standalone dataset per task.

## The pieces

- **`slack-gateway:prod-v1`** — the shared prod sidecar: the SQLite gateway + a baked, canonicalized
  prod corpus (88 channels, ~2.4M messages, **named** users). Built once from the real export and
  pushed; pulled as-is by every task. The prod base layers (incl. the ~558 MB DB) are identical
  across tasks, so the runner pulls them once and caches them.
- **`selfcontained/prod/v1/catalog/{channels.json,users.json}`** — the published **author directory**.
  Browse it to pick which prod channel/user to plant against (by **name**).
- **Per-task overlay** — a tiny Slack-export-shaped dir (`environment/data/overlay/`) carrying just the
  planted messages. Delivered as a **per-task sidecar image layer** (`slack-gateway:<task>` =
  `FROM slack-gateway:prod-v1` + `COPY overlay /data/slack-overlay`); `slack-boot.sh` imports it on
  top of the prod DB at standup (`--overlay`: preserves prod rows, adds the planted data).

> Why an image layer and not a `volumes:` mount? Harbor task validation rejects host bind-mounts on a
> sidecar. The overlay layer is a few KB on top of the shared, cached prod base, so it's cheap.

## How IDs line up (why overlays attach by name)

The importer assigns IDs by content hash — `C/U + sha1(name)` — so the **same channel/user name maps
to the same id** in the prod corpus and in an overlay. An overlay message in channel `engineering`
therefore lands in the *real* prod `#engineering` (`C72917EF6C1`). New names (a new channel or a new
person) hash to fresh ids and are simply added. Posting **as an existing prod user** needs that user's
raw id (names are display labels, not ids); planting **as a new person** just uses a new name.

Overlay timestamps must **post-date the prod corpus** (prod-v1 ends 2025-12-19) so `(channel_id, ts)`
never collides with a real message.

## Authoring a task

1. Pick a target channel from the catalog (e.g. `engineering`).
2. Author the overlay with `slack_export_writer.write_export(...)` — see
   `<task>/environment/data/gen_overlay.py`:
   ```python
   write_export([{ "channel": "engineering", "author": "robin.vega",
                   "content": "…I'm coming in at 6pm…", "timestamp": "2025-12-22T18:05:00Z" }],
                out_dir)   # -> environment/data/overlay/
   ```
3. Build + push the per-task sidecar:
   ```bash
   OVERLAY_DIR=<task>/environment/data TAG=<task> \
     REGISTRY=ghcr.io/abundant-ai PUSH=1 PLATFORM=linux/amd64 \
     selfcontained/base/build-overlay.sh
   ```
4. Point the task's `docker-compose.yaml` `slack` service at `slack-gateway:<task>` (no volume), set
   `custom_docker_compose = true`, and write the verifier/oracle. Required task shape (Harbor):
   `task.toml`, `instruction.md`, `environment/{Dockerfile,docker-compose.yaml,codebase}`,
   `tests/test.sh` (entrypoint → writes `/logs/verifier/reward.txt`), `solution/solve.sh`.

See `experiments/slack-prod-overlay/tasks/arrival-time` for a worked example.

## Building / refreshing the prod corpus

```bash
# 1. canonicalize + name the anonymized export (writes channels.json/users.json with synthetic names)
python3 selfcontained/base/import_export.py --export-dir <export> --write-metadata --names synthetic --force
# 2. build the named DB
SLACK_TEAM=acme python3 selfcontained/base/import_export.py --export-dir <export> --db /tmp/prod-v1.db
# 3. bake + push the prod gateway
DB_FILE=/tmp/prod-v1.db DATASET=prod-v1 REGISTRY=ghcr.io/abundant-ai PUSH=1 PLATFORM=linux/amd64 \
  selfcontained/base/build-seed.sh
DATASET=prod-v1 REGISTRY=ghcr.io/abundant-ai PUSH=1 PLATFORM=linux/amd64 \
  selfcontained/base/build-gateway.sh
# 4. publish the catalog (selfcontained/prod/v1/catalog/) for authors
```

IDs and names are deterministic (content-hashed), so rebuilds are stable.

## Compatibility

Any standard Slack export drops in for **chat read/post** tasks (history, replies, search, channels,
users, post). Not modeled: files, canvases, huddles, pins, bookmarks, rich blocks, and Slack-accurate
tokenized search (search is substring `LIKE`). Each container is fresh — no runtime reset endpoint.
