# State Schema

`aws-clone` reads task-authored JSON from `AWS_CLONE_STATE_FILE`, defaulting to `/data/aws-clone/state.json`. On startup it copies that read-only seed to `AWS_CLONE_RUNTIME_STATE_FILE`, defaulting to `/var/lib/aws-clone/state.json`, if the runtime file does not already exist.

Top-level fields:

- `meta`: `account_id`, `region`, and deterministic `now`.
- `s3.buckets`: buckets and seeded objects.
- `sqs.queues`: queues, attributes, redrive policies, and seeded messages.
- `sns.topics`: topics and subscriptions.
- `dynamodb.tables`: tables, key schema, attribute definitions, billing mode, and items.
- `eventbridge.rules`: rules, schedules, event patterns, and targets.
- `cloudwatch_logs.groups`: log groups, streams, and events.
- `ssm.parameters`: Parameter Store values.
- `secretsmanager.secrets`: secret names, version IDs, and staging labels.
- `iam.roles`: role and inline policy metadata.
- `iam.users` (optional): user metadata — inline policies, access keys, login profile, MFA — powering `get-credential-report` and user-principal policy simulation.
- `iam.access_denied_fixtures`: task-authored permission clues for prompts, docs, or verifier logic.
- `lambda.functions`: function metadata, log group references, and event source mappings.
- `kinesis.streams` (optional): Kinesis Data Streams and seeded records for shard / shard-iterator / consumer-lag tasks.
- `mutation_log`: verifier-visible mutation history reserved for admin/debug workflows.

> `iam.users` and `kinesis` are optional and may be absent from older state files; they default to empty.

## S3

```json
{
  "name": "acme-payment-exports",
  "objects": [
    {
      "key": "exports/2026-06-07/manifest.json",
      "body_json": {"batch_id": "pay-20260607", "records": 128},
      "metadata": {"owner": "payments"}
    }
  ]
}
```

Object bodies can use `body_json`, `body`, or `body_b64`.

## SQS and SNS

```json
{
  "name": "payment-webhook-retry",
  "attributes": {
    "VisibilityTimeout": "30",
    "RedrivePolicy": "{\"deadLetterTargetArn\":\"arn:aws:sqs:us-east-1:000000000000:payment-webhook-dlq\",\"maxReceiveCount\":\"3\"}"
  },
  "messages": [
    {
      "body_json": {"event_id": "evt_001", "status_code": 409},
      "attributes": {"error_type": "validation_conflict"}
    }
  ]
}
```

SNS subscriptions can refer to a seeded SQS queue with `endpoint_queue` and can include a `filter_policy`.

## DynamoDB

```json
{
  "name": "payment-idempotency",
  "key_schema": [{"AttributeName": "event_id", "KeyType": "HASH"}],
  "attribute_definitions": [{"AttributeName": "event_id", "AttributeType": "S"}],
  "billing_mode": "PAY_PER_REQUEST",
  "items": [
    {"event_id": {"S": "evt_001"}, "state": {"S": "scheduled"}}
  ]
}
```

Items use DynamoDB AttributeValue JSON so agents can use normal AWS CLI keys and filters.

## EventBridge

```json
{
  "name": "nightly-ledger-close",
  "schedule": "cron(55 23 * * ? *)",
  "targets": [
    {"id": "ledger-close-worker", "arn": "arn:aws:lambda:us-east-1:000000000000:function:ledger-close"}
  ]
}
```

Rules can use `schedule` or `event_pattern`.

## CloudWatch Logs

```json
{
  "name": "/aws/lambda/payment-webhook-worker",
  "streams": [
    {
      "name": "2026/06/07/[$LATEST]abc",
      "events": [
        {
          "timestamp": "2026-06-07T11:59:15Z",
          "message": "RuntimeError unsafe retry for validation_conflict event=evt_001"
        }
      ]
    }
  ]
}
```

## SSM and Secrets Manager

```json
{"name": "/payments/retry/max_attempts", "type": "String", "value": "3"}
```

```json
{
  "name": "payments/provider/api-key",
  "versions": [
    {"version_id": "v1", "stages": ["AWSPREVIOUS"]},
    {"version_id": "v2", "stages": ["AWSCURRENT"]}
  ]
}
```

Secret values default to the fake string `REDACTED`; tasks should usually rely on metadata and staging labels.

## IAM/STS and Lambda Metadata

IAM roles and inline policies are seeded as real LocalStack resources. STS caller identity is served by LocalStack.

`iam.users` are seeded as real users (inline policies via `put-user-policy`, access keys with `Active`/`Inactive` status, an optional login profile, and best-effort MFA). Because the IAM API cannot set access-key/login *dates*, deterministic credential-report values are carried as `awsclone:<column>` user tags and overlaid by the IAM shim when building the report.

```json
{
  "name": "legacy-batch-uploader",
  "policies": [{"name": "s3-read", "statements": [{"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": "*"}]}],
  "access_keys": [{"status": "Active"}],
  "credential_report": {
    "user_creation_time": "2023-11-01T00:00:00+00:00",
    "mfa_active": "false",
    "access_key_1_active": "true",
    "access_key_1_last_rotated": "2024-01-15T00:00:00+00:00",
    "access_key_1_last_used_date": "2024-03-02T00:00:00+00:00",
    "access_key_1_last_used_region": "us-east-1",
    "access_key_1_last_used_service": "s3"
  }
}
```

`credential_report` keys mirror the AWS credential-report CSV columns (e.g. `password_enabled`, `password_last_used`, `access_key_N_active`, `access_key_N_last_rotated`, `access_key_N_last_used_date`). The IAM hybrid shim (see `docs/LOCALSTACK-COMPATIBILITY.md`) serves `simulate-principal-policy`, `simulate-custom-policy`, `generate-credential-report`, and `get-credential-report`.

Lambda v1 fixtures seed function metadata and event source mappings when LocalStack supports them, but tasks should use CloudWatch logs and metadata rather than requiring real Lambda execution.

## Kinesis

```json
{
  "name": "payment-events-stream",
  "shard_count": 2,
  "stream_mode": "PROVISIONED",
  "retention_hours": 48,
  "tags": {"team": "payments"},
  "records": [
    {"partition_key": "merchant-acme", "data_json": {"event": "capture", "amount_cents": 1299}},
    {"partition_key": "merchant-globex", "data": "raw string payload"}
  ]
}
```

Streams are created (provisioned with `shard_count`, or `"stream_mode": "ON_DEMAND"`) and seeded with records via `put-records`. Record data accepts `data` (string), `data_json` (object), or `data_b64` (base64 bytes); an optional `explicit_hash_key` pins a record to a shard. Agents inspect streams with `describe-stream`, `list-shards`, `get-shard-iterator`, and `get-records`, exercising shard / shard-iterator / consumer-lag scenarios.
