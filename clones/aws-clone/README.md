# aws-clone

`aws-clone` is a LocalStack-backed AWS-local task harness for SWE and on-call agent benchmarks. It packages a reusable sidecar service that gives agents realistic AWS CLI workflows without real AWS credentials, internet at runtime, LocalStack Pro, or a from-scratch AWS implementation.

The service image is:

```text
ghcr.io/abundant-ai/aws-clone-service:main
```

The gateway is published as an image trio (see `docs/IMAGE-RELEASE.md`):

```text
ghcr.io/abundant-ai/aws-clone-service:main      # base API + tools, no data
ghcr.io/abundant-ai/aws-clone-service:prod-v1   # corpus baked in — boots mount-free
ghcr.io/abundant-ai/aws-clone-service:empty     # base API — per-task fixture mounted in
```

The Python package is `aws_clone`, the service hostname used by task packs should be `aws`, and the agent-facing tools are:

- `/usr/local/bin/aws`
- `/usr/local/bin/awslocal`
- `/usr/local/bin/aws-mcp` — the MCP server (stdio), in **CLI↔MCP parity**: every
  agent capability reachable from the CLI is also an MCP tool and vice-versa
  (see `docs/COVERAGE.md`). It is a thin client of the **same** LocalStack endpoint
  (`AWS_ENDPOINT_URL`) the CLI uses — boto3 calls in `aws_clone/mcp/tools.py`.

The admin/debug tool is:

- `/usr/local/bin/aws-clonectl` (mirrored by the operator-only MCP tools
  `aws_admin_state` / `aws_admin_mutations`)

Do not copy `aws-clonectl` into agent containers. Do not pass `AWS_CLONE_ADMIN_TOKEN` to agents. Do not mount raw AWS clone seed state into agent containers.

## Quick Start

```bash
docker build -f Dockerfile.service -t aws-clone-service:local .
docker compose -f examples/docker-compose.yaml up -d
docker compose -f examples/docker-compose.yaml exec -T aws awslocal s3 ls
AWS_CLONE_ADMIN_TOKEN=test-admin-token-acme-eval bin/aws-clonectl state
docker compose -f examples/docker-compose.yaml down -v
```

The example service reads `examples/data/aws-clone/state.json`, copies it to mutable runtime state at `/var/lib/aws-clone/state.json`, seeds LocalStack deterministically, and exposes admin endpoints on `localhost:4580`.

## Task-Pack Sidecar Pattern

Agent images should copy only the AWS tools and their support libraries:

```dockerfile
FROM ghcr.io/abundant-ai/aws-clone-service:<tag>@sha256:<digest> AS aws-tools
COPY --from=aws-tools /usr/local/bin/aws /usr/local/bin/awslocal /usr/local/bin/
COPY --from=aws-tools /opt/awscli /opt/awscli
ENV PYTHONPATH=/opt/awscli
ENV AWS_ENDPOINT_URL=http://aws:4566
ENV AWS_ACCESS_KEY_ID=test
ENV AWS_SECRET_ACCESS_KEY=test
ENV AWS_DEFAULT_REGION=us-east-1
```

Copying `/opt/awscli` also brings the IAM hybrid shim (`aws_clone_shim` + `sitecustomize.py`) that auto-loads with `PYTHONPATH=/opt/awscli` — no extra steps. It serves `iam simulate-principal-policy`, `simulate-custom-policy`, and `generate`/`get-credential-report` (the moto/LocalStack gaps) while every other call passes through to LocalStack. See `docs/LOCALSTACK-COMPATIBILITY.md`.

Sidecars mount seed state and runtime state:

```yaml
aws:
  image: ghcr.io/abundant-ai/aws-clone-service:<tag>@sha256:<digest>
  hostname: aws
  environment:
    AWS_CLONE_STATE_FILE: /data/aws-clone/state.json
    AWS_CLONE_RUNTIME_STATE_FILE: /var/lib/aws-clone/state.json
    AWS_CLONE_ENABLE_ADMIN_API: "1"
    AWS_CLONE_ADMIN_TOKEN: ${AWS_CLONE_ADMIN_TOKEN}
  volumes:
    - ./data/aws-clone/state.json:/data/aws-clone/state.json:ro
    - aws-clone-runtime:/var/lib/aws-clone
```

Agents should receive:

```text
AWS_ENDPOINT_URL=http://aws:4566
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_DEFAULT_REGION=us-east-1
```

See `examples/task-pack-compose/` for a runnable two-container example.

For benchmark task packs, consume a published digest-pinned image such as:

```text
ghcr.io/abundant-ai/aws-clone-service:main@sha256:<digest>
```

Do not rebuild this repository from inside task packs.

## Supported v1 Services

P0 coverage is backed by LocalStack for S3, SQS, SNS, DynamoDB, EventBridge, CloudWatch Logs, SSM Parameter Store, Secrets Manager metadata, IAM/STS basics, and Lambda metadata/log/event-source mapping fixtures.

Lambda execution is intentionally not required in v1. Task authors can seed function metadata, event source mappings, and CloudWatch logs without relying on Docker socket access inside task containers.

## Bundled task

A runnable Harbor/Oddish task lives at `oddish/tasks/payment-reconcile/` (agent +
`aws` gateway, `tests/test.sh`→`/logs/verifier/reward.txt`, `solution/solve.sh`).
It is a DynamoDB write→read round-trip: reconcile a stuck payment by recovering the
resolution from the SQS message, CloudWatch log, and S3 runbook. **nop=0, oracle=1**
(verified). See its `instruction.md` and `task.toml`.

## More Docs

- `docs/COVERAGE.md` — capability → endpoint → CLI → MCP tool matrix (R4/R5)
- `docs/TOOLS.md`
- `docs/STATE_SCHEMA.md`
- `docs/CREATING-TASKS.md`
- `docs/LOCALSTACK-COMPATIBILITY.md`
- `docs/IMAGE-RELEASE.md`
- `docs/PROD-OVERLAY.md` — canon advisories (identity N/A, operator boundary)
