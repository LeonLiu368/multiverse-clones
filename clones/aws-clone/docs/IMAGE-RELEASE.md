# Image Release

The service image is published as:

```text
ghcr.io/abundant-ai/aws-clone-service:main
```

CI also emits `sha-<shortsha>` tags through Docker metadata. Task packs should pin a digest when freezing benchmark inputs:

```text
ghcr.io/abundant-ai/aws-clone-service:main@sha256:<digest>
```

## Local Build and Smoke

```bash
python -m pytest tests
docker build -f Dockerfile.service -t aws-clone-service:local .
docker compose -f examples/docker-compose.yaml up -d
docker compose -f examples/docker-compose.yaml exec -T aws awslocal s3 ls
AWS_CLONE_ADMIN_TOKEN=test-admin-token-acme-eval bin/aws-clonectl state
docker compose -f examples/docker-compose.yaml down -v
```

## Task-Pack Smoke

```bash
docker compose -f examples/task-pack-compose/docker-compose.yaml up -d --build
docker compose -f examples/task-pack-compose/docker-compose.yaml exec -T agent test ! -e /data/aws-clone/state.json
docker compose -f examples/task-pack-compose/docker-compose.yaml exec -T agent sh -lc 'command -v aws && command -v awslocal && ! command -v aws-clonectl'
docker compose -f examples/task-pack-compose/docker-compose.yaml exec -T agent awslocal s3 ls
docker compose -f examples/task-pack-compose/docker-compose.yaml down -v
```

## Publishing

On `main`, `.github/workflows/build-service-image.yml` runs Python tests, builds the service image, executes compose smoke tests, logs in to GHCR, and pushes `ghcr.io/abundant-ai/aws-clone-service`.

Manual pushes require a GitHub token that can write packages for `abundant-ai`:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u <github-user> --password-stdin
```

For manual publishing, build the platform your task runtime needs and push directly:

```bash
docker buildx build \
  --platform linux/amd64 \
  -f Dockerfile.service \
  -t ghcr.io/abundant-ai/aws-clone-service:main \
  --push .
```

Capture the pushed digest:

```bash
docker buildx imagetools inspect ghcr.io/abundant-ai/aws-clone-service:main
```

Task packs should consume the immutable reference:

```text
ghcr.io/abundant-ai/aws-clone-service:main@sha256:<digest>
```

Do not point benchmark task packs at `aws-clone-service:local`, an unpinned mutable tag, or a source build of `Dockerfile.service`.
