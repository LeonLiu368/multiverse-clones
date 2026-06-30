# Image Release

## The image trio

The gateway ships as a **multi-arch** (`linux/amd64,linux/arm64`) image trio:

| Tag | Built from | Data | Use |
|---|---|---|---|
| `:latest` / `:main` / `:sha-<sha>` / `:empty` | `Dockerfile.service` (== `Dockerfile.empty`) | none — mount a fixture at `/data/sentry-clone/state.json` | per-task workspaces (empty + mount) |
| `:prod-v1` | `Dockerfile.prod-v1` (`FROM :empty`, bakes `corpus/state.json`) | corpus baked in at `$SENTRY_CLONE_CORPUS_FILE`; serves **mount-free** | prod/realistic tasks sharing one corpus |

A task switches `empty ↔ prod-v1` by the **image tag alone**. On `:prod-v1` the
entrypoint serves the baked corpus when no fixture is mounted; a fixture mount, if
supplied, takes precedence. The corpus is reproducible from `corpus/state.json` in this
repo (regenerate with the committed generator if you change the seed).

Build the trio locally:

```sh
docker build -f Dockerfile.service -t sentry-clone-service:local .
docker build -f Dockerfile.empty   -t sentry-clone-service:empty .
docker build -f Dockerfile.prod-v1 --build-arg BASE=sentry-clone-service:empty -t sentry-clone-service:prod-v1 .

# prod-v1 boots mount-free and serves the corpus:
docker run -d --name sc-prod -p 3001:80 sentry-clone-service:prod-v1
curl -sf -H 'Authorization: Bearer test-token-acme-eval' http://localhost:3001/api/0/organizations/acme/issues/
docker rm -f sc-prod
```

Run local smoke:

```sh
docker compose -f examples/docker-compose.yaml up -d
curl -sf http://localhost:3000/api/healthz
SENTRY_URL=http://localhost:3000 SENTRY_AUTH_TOKEN=test-token-acme-eval bin/sentry whoami --json
SENTRY_URL=http://localhost:3000 SENTRY_AUTH_TOKEN=test-token-acme-eval bin/sentry issues list --project payments-api --query 'is:unresolved' --json
SENTRY_URL=http://localhost:3000 SENTRY_CLONE_ADMIN_TOKEN=test-admin-token-acme-eval bin/sentry-clonectl mutations
docker compose -f examples/docker-compose.yaml down -v
```

Pushes from `main` publish the multi-arch trio:

```text
ghcr.io/abundant-ai/sentry-clone-service:main
ghcr.io/abundant-ai/sentry-clone-service:latest
ghcr.io/abundant-ai/sentry-clone-service:sha-<shortsha>
ghcr.io/abundant-ai/sentry-clone-service:empty
ghcr.io/abundant-ai/sentry-clone-service:prod-v1
```

Use `:main` only for quick testing because it moves on every main push. Use the `:sha-<shortsha>` tag for normal task-pack references.

For fully frozen benchmark inputs, pin both the commit tag and the digest:

```Dockerfile
FROM ghcr.io/abundant-ai/sentry-clone-service:sha-<shortsha>@sha256:<digest> AS sentry-tools
```

After a publish, inspect the package or run:

```sh
docker buildx imagetools inspect ghcr.io/abundant-ai/sentry-clone-service:sha-<shortsha>
```

Use the reported digest in task-pack Dockerfiles and compose files.
