# Image Release

Build locally:

```sh
docker build -f Dockerfile.service -t sentry-clone-service:local .
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

Pushes from `main` publish two tags:

```text
ghcr.io/abundant-ai/sentry-clone-service:main
ghcr.io/abundant-ai/sentry-clone-service:sha-<shortsha>
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
