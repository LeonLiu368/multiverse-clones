#!/bin/bash
# Oracle solution for payment-reconcile.
#
# Recovers the reconcile target by USING THE TOOLS against the gateway:
#   1. read the failing SQS message  -> batch_id = pay-20260630-batch7, evt_042
#   2. read the worker log line       -> confirms validation_conflict on evt_042
#   3. read the S3 runbook            -> resolved_state = "reconciled"
# then writes the resolution into DynamoDB (the write->read round-trip the
# verifier checks). This mirrors an MCP-driven solve: the same boto3 calls back
# the aws-mcp tools, so an agent could do this via either surface.
set -euo pipefail

export AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-http://aws:4566}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

# 1. batch_id from the failing SQS message.
QUEUE_URL="$(awslocal sqs get-queue-url --queue-name payment-webhook-retry --query QueueUrl --output text)"
MSG="$(awslocal sqs receive-message --queue-url "$QUEUE_URL" --max-number-of-messages 10 --message-attribute-names All)"
BATCH="$(printf '%s' "$MSG" | python3 -c "import json,sys; m=json.load(sys.stdin)['Messages'][0]; print(json.loads(m['Body'])['batch_id'])")"
echo "oracle: batch_id=$BATCH"

# 2. confirm the failure in the worker logs (observability step).
awslocal logs filter-log-events \
  --log-group-name /aws/lambda/payment-webhook-worker \
  --filter-pattern validation_conflict >/dev/null

# 3. resolved_state from the S3 runbook.
RESOLVED="$(awslocal s3 cp s3://acme-payment-exports/runbooks/reconcile.json - \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['resolved_state'])")"
echo "oracle: resolved_state=$RESOLVED"

# 4. write the resolution (the round-trip the verifier reads back).
awslocal dynamodb put-item \
  --table-name payment-idempotency \
  --item "{\"event_id\":{\"S\":\"evt_042\"},\"state\":{\"S\":\"$RESOLVED\"},\"reconciled_batch\":{\"S\":\"$BATCH\"}}"

echo "oracle: reconciled evt_042 -> state=$RESOLVED batch=$BATCH"
