# Image release: the single `slack-service` image

The whole backend ships as **one image** we build and push: `ghcr.io/abundant-ai/slack-service`.
It's a lightweight `python:3.12-slim` image (~112 MB, **no Mattermost, no Postgres**) containing the
SQLite-backed Slack Web API gateway, the importer, our `slack` CLI, and the off-the-shelf korotovsky
`slack-mcp` binary (patched + wrapped). Every task builds its `main` container **FROM** this image
and adds only the codebase.

```
                 build once (CI)                base for every task's `main`
selfcontained/base/Dockerfile.service  ──►  ghcr.io/abundant-ai/slack-service:latest
                                              │
            task environment/                 ▼
              Dockerfile          FROM ghcr.io/abundant-ai/slack-service:latest + COPY codebase  (BUILT by Harbor)
              docker-compose.yaml main: build ./Dockerfile ; mounts ./data/slack-export
```

## Why this works with Harbor/Oddish
Harbor force-builds the `main` service (it injects a `build:` onto it). `main`'s Dockerfile is
`FROM ghcr.io/abundant-ai/slack-service:latest` — Docker pulls that base once (cached thereafter) and
layers the codebase on top. The heavy backend is never rebuilt per task; the per-task build is a tiny
`COPY codebase`.

## Build / push
```bash
# Local — IMPORTANT on Apple Silicon: build a NATIVE image (amd64 emulation hangs locally):
docker build -f selfcontained/base/Dockerfile.service -t ghcr.io/abundant-ai/slack-service:latest selfcontained/base
# (selfcontained/base/build.sh does the same with REGISTRY/TAG/PUSH env knobs.)
```

CI does this automatically: **`.github/workflows/build-service-image.yml`** builds
`Dockerfile.service` and pushes `ghcr.io/abundant-ai/slack-service:latest` (+ `:<sha>`) on **every
push to `main`**, using the built-in `GITHUB_TOKEN` on a native x86_64 runner. The image includes a
**Go build stage** (golang:1.25) that clones + patches + compiles the korotovsky MCP — CI has the
network/toolchain for it.

## GHCR one-time setup
- **Visibility:** new GHCR packages are private. Set `slack-service` to **public** (org → Packages →
  the package → visibility) so Modal/Oddish pull it with no credentials. (If kept private, give the
  runner a `read:packages` registry secret instead.)
- **Org policy:** confirm the `abundant-ai` org allows package publishing, or the first push 403s.
- **amd64:** CI runs on `ubuntu-latest` (x86_64) and `main` pins `platform: linux/amd64`. Locally on
  arm64, build a native image (the Dockerfile is arch-agnostic) — amd64-on-arm64 emulation hangs.

## How a run consumes it
The task `Dockerfile` does `FROM ghcr.io/abundant-ai/slack-service:latest`; Oddish/Modal pulls the
base on build. The task supplies only its `data/slack-export/` (mounted + imported at boot) and
`codebase/` (built into `main`).

## Per service clone
Same pattern generalises: `gh-service`, `linear-service`, etc. — one pushed image per clone, one
`Dockerfile.service` + workflow each; tasks build FROM it and add only data + codebase.
