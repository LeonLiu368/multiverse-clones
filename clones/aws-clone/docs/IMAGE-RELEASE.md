# Image Release

## The gateway image trio

The gateway is published as a three-image set (Clone Standard R2.b/j):

```text
ghcr.io/abundant-ai/aws-clone-service:main      # base API + tools, no data
ghcr.io/abundant-ai/aws-clone-service:prod-v1   # corpus state.json BAKED IN — boots mount-free
ghcr.io/abundant-ai/aws-clone-service:empty     # base API, no data — per-task fixture mounted in
```

Switching a task between the baked corpus and a custom workspace is the **image
tag alone** (`:prod-v1` ↔ `:empty`), never a compose-logic change:

- **`:prod-v1`** bakes `examples/data/aws-clone/state.json` into the image at
  `/opt/aws-clone-corpus/state.json` and points `AWS_CLONE_STATE_FILE` at it, so a
  cold `docker run :prod-v1` (no `-v`) boots healthy and serves the full corpus.
- **`:empty`** ships no data; mount a per-task `state.json` at
  `/data/aws-clone/state.json`.

All three are published **multi-arch** (`linux/amd64,linux/arm64`) so the sidecar
pulls cleanly on both arches (R2.k). CI also emits `sha-<shortsha>` tags through
Docker metadata. Task packs should pin a digest when freezing benchmark inputs:

```text
ghcr.io/abundant-ai/aws-clone-service:prod-v1@sha256:<digest>
```

Build the trio locally with `./build-images.sh` (tags
`aws-clone-service:{base,prod-v1,empty}`).

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

For manual publishing, build **multi-arch** and push directly (the base, then the
trio derived from it):

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -f Dockerfile.service \
  -t ghcr.io/abundant-ai/aws-clone-service:main \
  --push .

docker buildx build --platform linux/amd64,linux/arm64 \
  -f Dockerfile.prod-v1 --build-arg BASE=ghcr.io/abundant-ai/aws-clone-service:main \
  -t ghcr.io/abundant-ai/aws-clone-service:prod-v1 --push .

docker buildx build --platform linux/amd64,linux/arm64 \
  -f Dockerfile.empty --build-arg BASE=ghcr.io/abundant-ai/aws-clone-service:main \
  -t ghcr.io/abundant-ai/aws-clone-service:empty --push .
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
