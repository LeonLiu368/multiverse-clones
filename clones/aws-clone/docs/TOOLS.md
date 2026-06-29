# Tools

Agents use normal AWS CLI workflows against LocalStack.

## Agent Environment

```text
AWS_ENDPOINT_URL=http://aws:4566
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_DEFAULT_REGION=us-east-1
```

No real AWS credentials are required or used.

## `awslocal`

`awslocal` automatically targets `AWS_ENDPOINT_URL`.

```bash
awslocal sts get-caller-identity
awslocal s3 ls
awslocal s3 ls s3://acme-payment-exports/exports/2026-06-07/
awslocal s3 cp s3://acme-payment-exports/exports/2026-06-07/manifest.json -
awslocal sqs list-queues
awslocal sqs get-queue-url --queue-name payment-webhook-retry
awslocal sqs receive-message --queue-url <url> --max-number-of-messages 10
awslocal dynamodb list-tables
awslocal dynamodb get-item --table-name payment-idempotency --key '{"event_id":{"S":"evt_001"}}'
awslocal logs describe-log-groups
awslocal logs filter-log-events --log-group-name /aws/lambda/payment-webhook-worker --filter-pattern validation_conflict
awslocal ssm get-parameter --name /payments/retry/max_attempts
awslocal secretsmanager describe-secret --secret-id payments/provider/api-key
awslocal events list-rules
awslocal events list-targets-by-rule --rule nightly-ledger-close
```

## `aws`

The regular AWS CLI is also available. Use `--endpoint-url "$AWS_ENDPOINT_URL"` when needed:

```bash
aws --endpoint-url "$AWS_ENDPOINT_URL" s3 ls
aws --endpoint-url "$AWS_ENDPOINT_URL" sts get-caller-identity
```

## Admin Tool

`aws-clonectl` is verifier/admin-only. It uses `AWS_CLONE_ADMIN_TOKEN` and the admin API.

Useful operator commands:

```bash
AWS_CLONE_ADMIN_TOKEN=test-admin-token-acme-eval aws-clonectl state
AWS_CLONE_ADMIN_TOKEN=test-admin-token-acme-eval aws-clonectl mutations
AWS_CLONE_ADMIN_TOKEN=test-admin-token-acme-eval aws-clonectl s3-buckets
AWS_CLONE_ADMIN_TOKEN=test-admin-token-acme-eval aws-clonectl s3-object --bucket acme-payment-exports --key exports/2026-06-07/manifest.json
AWS_CLONE_ADMIN_TOKEN=test-admin-token-acme-eval aws-clonectl sqs-messages --queue payment-webhook-retry
AWS_CLONE_ADMIN_TOKEN=test-admin-token-acme-eval aws-clonectl dynamodb-table --name payment-idempotency
AWS_CLONE_ADMIN_TOKEN=test-admin-token-acme-eval aws-clonectl logs --group /aws/lambda/payment-webhook-worker --pattern validation_conflict
```

Do not mention `aws-clonectl`, admin endpoints, raw seed paths, or verifier tokens in agent prompts.
