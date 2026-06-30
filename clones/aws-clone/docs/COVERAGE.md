# aws-clone — Functional Coverage Matrix (R4)

## Real service
- name: AWS service APIs (S3, SQS, SNS, DynamoDB, CloudWatch Logs, IAM/STS, Kinesis)
- api_base: AWS SDK/CLI service endpoints (LocalStack-backed)
- reference: https://docs.aws.amazon.com/
- version: botocore 1.x
- snapshot_date: 2026-06-30

Machine-checkable map of the **agent-used AWS surface** to its LocalStack
endpoint, its CLI command, its `aws-mcp` MCP tool, fidelity tier, and whether it
is **assessment-grade** (R5). The clone is **T3** (OSS-backed: LocalStack/moto
behind the real `aws`/`awslocal` CLI), with a thin **IAM hybrid shim** filling
the moto/LocalStack IAM gaps (`simulate-*`, credential report).

CLI = the real `aws`/`awslocal` command an agent runs. MCP = a tool in
`aws_clone.mcp.server` (see `aws_clone/mcp/tools.py`). Both the CLI and MCP are
**thin clients of the same LocalStack HTTP API** at `AWS_ENDPOINT_URL` — there is
no business logic in either, so they cannot drift (R3.2/R3.3). The operator rows
are reachable only through the token-gated admin API (`aws-clonectl` /
`aws_admin_*`) and are marked operator-only.

| Capability | AWS API / endpoint | CLI | MCP tool | Fidelity | Assessment-grade | Tested |
|---|---|---|---|---|---|---|
| S3 list buckets | `ListBuckets` | `awslocal s3 ls` / `s3api list-buckets` | `aws_s3_list_buckets` | T3 | no (read) | happy+error |
| S3 list objects | `ListObjectsV2` | `awslocal s3 ls s3://<b>/<prefix>` | `aws_s3_list_objects` | T3 | no (read) | happy+error |
| S3 get object | `GetObject` | `awslocal s3 cp s3://<b>/<k> -` | `aws_s3_get_object` | T3 | **yes** (multi-step; realistic `NoSuchKey`) | happy+error |
| S3 put object | `PutObject` | `awslocal s3 cp - s3://<b>/<k>` | `aws_s3_put_object` | T3 | **yes** (write→read round-trip) | happy+error |
| SQS list queues | `ListQueues` | `awslocal sqs list-queues` | `aws_sqs_list_queues` | T3 | no (read) | happy+error |
| SQS get queue url | `GetQueueUrl` | `awslocal sqs get-queue-url` | `aws_sqs_get_queue_url` | T3 | no | happy+error |
| SQS receive messages | `ReceiveMessage` | `awslocal sqs receive-message` | `aws_sqs_receive_messages` | T3 | **yes** (multi-step: resolve url→receive; attrs) | happy+error |
| SQS send message | `SendMessage` | `awslocal sqs send-message` | `aws_sqs_send_message` | T3 | **yes** (write→read round-trip) | happy+error |
| DynamoDB list tables | `ListTables` | `awslocal dynamodb list-tables` | `aws_dynamodb_list_tables` | T3 | no (read) | happy |
| DynamoDB get item | `GetItem` | `awslocal dynamodb get-item` | `aws_dynamodb_get_item` | T3 | **yes** (typed key; `ResourceNotFoundException`) | happy+error |
| DynamoDB put item | `PutItem` | `awslocal dynamodb put-item` | `aws_dynamodb_put_item` | T3 | **yes** (write→read round-trip, the bundled task) | happy+error |
| DynamoDB scan | `Scan` | `awslocal dynamodb scan` | `aws_dynamodb_scan` | T3 | no | happy |
| CloudWatch Logs describe groups | `DescribeLogGroups` | `awslocal logs describe-log-groups` | `aws_logs_describe_groups` | T3 | no (read) | happy |
| CloudWatch Logs filter events | `FilterLogEvents` | `awslocal logs filter-log-events` | `aws_logs_filter_events` | T3 | **yes** (filter-pattern query grammar) | happy+error |
| SSM get parameter | `GetParameter` | `awslocal ssm get-parameter` | `aws_ssm_get_parameter` | T3 | no | happy+error |
| Secrets Manager describe | `DescribeSecret` | `awslocal secretsmanager describe-secret` | `aws_secrets_describe` | T3 | no | happy+error |
| EventBridge list rules | `ListRules` | `awslocal events list-rules` | `aws_events_list_rules` | T3 | no (read) | happy |
| EventBridge list targets | `ListTargetsByRule` | `awslocal events list-targets-by-rule` | `aws_events_list_targets` | T3 | **yes** (multi-step: rule→targets) | happy |
| IAM simulate custom policy | `SimulateCustomPolicy` (shim) | `awslocal iam simulate-custom-policy` | `aws_iam_simulate_custom_policy` | T3 (shim) | **yes** (devops shape; computed decision) | happy+error |
| IAM simulate principal policy | `SimulatePrincipalPolicy` (shim) | `awslocal iam simulate-principal-policy` | `aws_iam_simulate_principal_policy` | T3 (shim) | **yes** (devops shape; live policy eval) | happy |
| IAM credential report | `Generate/GetCredentialReport` (shim) | `awslocal iam get-credential-report` | `aws_iam_get_credential_report` | T3 (shim) | **yes** (devops; real CSV bytes) | happy |
| STS caller identity | `GetCallerIdentity` | `awslocal sts get-caller-identity` | `aws_sts_get_caller_identity` | T3 | no | happy |
| Kinesis list streams | `ListStreams` | `awslocal kinesis list-streams` | `aws_kinesis_list_streams` | T3 | no (read) | happy |
| Kinesis describe stream summary | `DescribeStreamSummary` | `awslocal kinesis describe-stream-summary` | `aws_kinesis_describe_stream_summary` | T3 | **yes** (shard/iterator chaining) | happy |
| Admin: clone state | `GET /api/_clone/state` (token) | `aws-clonectl state` | `aws_admin_state` (operator-only) | T1 | n/a (operator) | happy+error |
| Admin: mutation log | `GET /api/_clone/mutations` (token) | `aws-clonectl mutations` | `aws_admin_mutations` (operator-only) | T1 | n/a (operator) | happy |

## Counts

- `capabilities_total` = 26 (24 agent data-plane + 2 operator admin)
- `with_cli` = 26
- `with_mcp` = 26 (full CLI↔MCP parity; operator rows map CLI `aws-clonectl` ↔ MCP `aws_admin_*`)
- `assessment_grade` = 12 (≥5 required by R5.1)
- write→read round-trips = 3 (S3 put→get, SQS send→receive, **DynamoDB put→get** — the latter is exercised end-to-end by the `payment-reconcile` bundled task, satisfying R5.2)

## Assessment-grade rationale (R5)

Each row marked **yes** has ≥3 of the assessment-grade properties:

- **DynamoDB get/put item** — stateful (write observable on later read), multi-step
  (find key from buried context → write), realistic typed errors
  (`ResourceNotFoundException`, not a 500). The bundled `payment-reconcile` task
  exercises the full put→get round-trip.
- **SQS receive/send** — multi-step (resolve queue url → act), stateful, message
  attributes preserved.
- **S3 get/put object** — stateful round-trip, realistic `NoSuchKey`/`NoSuchBucket`.
- **CloudWatch Logs filter** — non-trivial filter-pattern query grammar.
- **IAM simulate-*/credential report** — side-effecting devops shape: the decision
  is *computed from live policy state* by the hybrid shim (not canned), the real
  `EvalDecision` envelope, and the CSV credential report mirrors real AWS bytes.
- **EventBridge list-targets / Kinesis shard summary** — multi-step chaining
  (rule→targets, stream→shards→iterator→records).

## Envelope fidelity (R4.3)

Because the data plane is LocalStack behind the real `aws`/`awslocal` CLI, response
envelopes are authentic: real `QueueUrl` shapes, DynamoDB attribute-typed items
(`{"S":"..."}`), `ResourceNotFoundException` / `NoSuchKey` error codes (not 500s),
and real credential-report CSV bytes. The IAM shim returns the genuine
`SimulatePolicyResponse` / `EvaluationResults` envelope.
