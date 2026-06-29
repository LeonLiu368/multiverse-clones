# LocalStack Compatibility

`aws-clone` uses LocalStack Community as the AWS-compatible backend. It does not implement AWS services from scratch.

## Used Services

The service image enables these LocalStack services:

- S3
- SQS
- SNS
- DynamoDB
- EventBridge (`events`)
- CloudWatch Logs
- SSM Parameter Store
- Secrets Manager
- IAM
- STS
- Lambda metadata APIs
- Kinesis Data Streams

## IAM Hybrid Shim

LocalStack/moto do not implement a few IAM operations that SRE tasks need. `aws-clone` serves them with a thin, deterministic shim that travels INSIDE `/opt/awscli` and auto-loads via `sitecustomize` (so it works for both `aws`/`awslocal` and any agent boto3 imported from `/opt/awscli`). It registers a botocore `before-call` handler for IAM ONLY; every other call passes straight through to LocalStack.

- `simulate-principal-policy` / `simulate-custom-policy`: evaluated from the principal's live identity policies (inline + attached managed) plus its permission boundary, against the requested actions/resources and context. Explicit `Deny` wins; permission boundary is an intersection; `Action`/`NotAction` use wildcards (case-insensitive), `Resource`/`NotResource` use wildcards (case-sensitive); common `Condition` operators are supported and referenced-but-missing context keys are reported in `MissingContextValues`. Not modeled: resource-based policies, SCPs/Organizations, session policies, and policy variables.
- `generate-credential-report` returns `State=COMPLETE`; `get-credential-report` builds the AWS-format CSV from live IAM users, overlaying deterministic dates from `awsclone:<column>` user tags (see `docs/STATE_SCHEMA.md`). `Content` is returned as raw CSV **bytes**, exactly like real AWS — read it via boto3 (`client.get_credential_report()["Content"].decode()`). The bundled awscli renders binary blobs poorly in plain `aws`/`awslocal` output (a CLI limitation that also affects real `aws iam get-credential-report`), so verifiers and report-parsing tasks should use the SDK.

If the shim hits an unexpected error it falls through to LocalStack's native behavior rather than masking it.

## Lambda

v1 intentionally avoids requiring real Lambda execution. Docker socket access is not assumed in Harbor/Oddish-style task containers, so task authors should seed:

- Lambda function metadata
- Event source mapping metadata
- CloudWatch log groups, streams, and events
- Optional static invocation clues outside the runtime path

Real Lambda execution can be evaluated later behind an explicit Docker-socket-enabled mode.

## Known Limitations

- LocalStack behavior is an AWS-compatible subset, not a perfect AWS account.
- IAM access-denied fixtures are state metadata; they are not a full policy enforcement engine.
- The admin mutation log records clone-managed mutations only. Verifiers should use admin snapshots and service APIs for final state checks.
- SQS admin message inspection uses AWS APIs and does not expose raw backend files.
- Secrets Manager values are fake local values; tasks should prefer metadata workflows.

## Running Commands

Inside an agent container:

```bash
awslocal sts get-caller-identity
awslocal s3 ls
awslocal sqs list-queues
```

With plain `aws`:

```bash
aws --endpoint-url "$AWS_ENDPOINT_URL" dynamodb list-tables
```

The service image pins AWS CLI/Botocore to a LocalStack 3.8-compatible 1.33-era release so SQS uses the Query protocol. Newer Botocore SQS JSON protocol models can make LocalStack 3.8 mark messages invisible while returning an empty `receive-message` response.
