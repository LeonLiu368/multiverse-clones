# Image release: the single `slack-service` image

The whole backend ships as **one image** we build and push: `ghcr.io/abundant-ai/slack-service`.
It contains real Mattermost (bound to localhost) + the Slack Web API gateway + the seeder + the
entrypoint. Every task **pulls** it for the `api` service — no task rebuilds the backend.

The agent container (`main`) is intentionally NOT this image: it's a thin `python:slim` build with
the codebase, so the agent box has zero Mattermost tells. That's the only "build" a task does, and
it's tiny. (We push one image; the agent base is the public `python:slim`.)

```
                 build once (CI)                pulled by every task
selfcontained/base/Dockerfile.service  ──►  ghcr.io/abundant-ai/slack-service:latest
                                              │
            task environment/                 ▼
              docker-compose.yaml   api:  image: ghcr.io/abundant-ai/slack-service   (PULLED)
              Dockerfile (thin)     main: build ./Dockerfile (python:slim + codebase) (BUILT)
```

## Why this works with Harbor/Oddish
Harbor force-builds **only** the `main` service (it injects a `build:` onto it). Any other service
with `image:` only — like `api` — is **pulled**, standard Docker Compose behaviour. So `api` can
reference a prebuilt registry image and never rebuild, while `main` builds the thin agent. (The
earlier all-`image:` attempt failed only because `main` had no Dockerfile.)

## Build / push
```bash
# Local (tags slack-service:local):
selfcontained/base/build.sh

# Local but tagged as the registry path (so task composes find it without pulling):
REGISTRY=ghcr.io/abundant-ai TAG=latest selfcontained/base/build.sh

# Push to GHCR:
REGISTRY=ghcr.io/abundant-ai TAG=latest PUSH=1 selfcontained/base/build.sh
```

CI does this automatically: **`.github/workflows/build-service-image.yml`** builds
`Dockerfile.service` and pushes `ghcr.io/abundant-ai/slack-service:latest` (+ `:<sha>`) on **every
push to `main`**, using the built-in `GITHUB_TOKEN` on a native x86_64 runner.

## GHCR one-time setup
- **Visibility:** new GHCR packages are private. Set `slack-service` to **public** (org → Packages →
  the package → visibility) so Modal/Oddish pull it with no credentials. (If kept private, give the
  runner a `read:packages` registry secret instead.)
- **Org policy:** confirm the `abundant-ai` org allows package publishing, or the first push 403s.
- **amd64:** Mattermost is amd64-only; CI runs on `ubuntu-latest` (x86_64) and both services pin
  `platform: linux/amd64`.

## How a run consumes it
The task compose references the image via env with a registry default:
```yaml
api:  image: ${SLACK_SERVICE_IMAGE:-ghcr.io/abundant-ai/slack-service:latest}
```
Oddish/Modal pulls it on `up`. Override `SLACK_SERVICE_IMAGE` to point at a local or pinned-`:<sha>`
copy. The task supplies only its `data/mattermost/` (mounted, seeded into the pulled service) and
`codebase/` (built into the thin agent).

## Per service clone
Same pattern generalises: `gh-service`, `linear-service`, etc. — one pushed image per clone, one
`Dockerfile.service` + workflow each; tasks pull it and add only data + codebase + the thin agent.
