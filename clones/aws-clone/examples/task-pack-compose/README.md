# AWS Clone Task-Pack Compose Example

This example shows the intended sidecar pattern for future task packs:

- `aws` runs `aws-clone-service` with LocalStack and the verifier-only admin API.
- `agent` receives only `aws` and `awslocal` plus normal local AWS credentials.
- The raw seed file is mounted only into the `aws` sidecar.
- `AWS_CLONE_ADMIN_TOKEN` and `aws-clonectl` are not present in the agent container.

Run:

```bash
docker build -f Dockerfile.service -t aws-clone-service:local .
docker compose -f examples/task-pack-compose/docker-compose.yaml up -d --build
docker compose -f examples/task-pack-compose/docker-compose.yaml exec -T agent awslocal s3 ls
docker compose -f examples/task-pack-compose/docker-compose.yaml down -v
```
