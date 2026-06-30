# Reconcile the stuck payment event

A payment webhook event is stuck. In the `payment-idempotency` DynamoDB table,
event `evt_042` is sitting in `state = "stuck"` and on-call needs it reconciled.

You have AWS tools that talk to the team's AWS account: the `aws` / `awslocal`
CLI and the `aws` MCP server (same surface). Use them to investigate and fix.

## What to do

1. Investigate why `evt_042` is stuck. The context is spread across services:
   - the `payment-webhook-retry` SQS queue holds the failing message,
   - the `/aws/lambda/payment-webhook-worker` CloudWatch log group has the error,
   - the `acme-payment-exports` S3 bucket has the on-call runbook.
2. Determine the correct resolution from the runbook and the failing message.
3. Write the resolution back into the `payment-idempotency` DynamoDB table for
   `event_id = evt_042`:
   - set `state` to the runbook's resolved state,
   - set `reconciled_batch` to the failing message's `batch_id`.

## Done when

The `payment-idempotency` item for `evt_042` reflects the reconciled state and
the correct batch id. The grader reads the item back through the AWS API.
