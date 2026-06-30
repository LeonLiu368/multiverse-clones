# PROD-OVERLAY — the two-image + mount model for notion-clone

How a task author picks the gateway's data delivery.

## The image trio

| Image | FROM | Contents | Use |
|---|---|---|---|
| `ghcr.io/abundant-ai/notion-service` | `python:3.12-slim` | API + `notion-cli` + `notion-mcp`, **no data** | the base everything builds on |
| `…/notion-service:prod-v1` | base | the **corpus DB baked in** (`/srv/notion.db`) | prod/realistic tasks — served **mount-free** |
| `…/notion-service:empty` | base | **no data**, a mount target | tasks that want a custom workspace |

## Path A — Baked-DB (`:prod-v1`)  ← the default

The corpus is `COPY`d into the image. The entrypoint sees an existing `$NOTION_DB`
and serves it as-is (no seeding, no mount). A task just references the tag:

```yaml
services:
  notion:
    image: ghcr.io/abundant-ai/notion-service:prod-v1
```

Boot it with nothing mounted and seeded reads work — this is what R2.j requires, and
it is verified in `tests/` and the bundled task.

## Path B — Empty + mount

Author a canonical `fixture.json` (the `seed/schema.py` shape) and mount it into the
**gateway only**:

```yaml
services:
  notion:
    image: ghcr.io/abundant-ai/notion-service:empty
    environment: [ "NOTION_FIXTURE=/srv/fixture.json" ]
    volumes: [ "./fixture.json:/srv/fixture.json:ro" ]
```

Or push it into a running gateway via the token-gated control plane
(`POST /_control/seed` with `X-Control-Token`, `NOTION_CONTROL_TOKEN` set on the
gateway). Never mount the fixture into `main` — the agent must reach data only
through the API.

## Switching paths

`empty ↔ prod-v1` is the **image tag alone**. No code, compose-structure, or agent
changes.

## The build:+image: dual (no registry creds)

The bundled task's `notion` service carries both a `build:` (the task's
`notion.Dockerfile`, which bakes the corpus locally) and the published `image:` name.
`docker compose build` tags the local build as the `image:` name, so `up` never pulls
— the task runs with **no GHCR auth** (R1.5). Anyone who prefers to pull the
published multi-arch image can.
