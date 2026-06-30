#!/bin/bash
# Deterministic verification for payment-reconcile (a DynamoDB write->read round-trip).
#
# reward=1 iff the agent reconciled evt_042 by writing, into the live
# `payment-idempotency` DynamoDB table (read back through the SAME AWS API, never
# trusting narration):
#   - state            = "reconciled"  (from the S3 runbook resolved_state)
#   - reconciled_batch = "pay-20260630-batch7"  (the batch_id buried in the failing
#                        SQS message + the worker log line)
#
# The correct values are discoverable ONLY by using the tools against the gateway
# (S3 runbook + SQS message + CloudWatch log) — they are not present on the agent
# image. nop (no write / still "stuck") -> 0; oracle -> 1.
set -uo pipefail
mkdir -p /logs/verifier

export AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-http://aws:4566}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

item_json="$(awslocal dynamodb get-item \
  --table-name payment-idempotency \
  --key '{"event_id":{"S":"evt_042"}}' 2>/logs/verifier/getitem.err)"
echo "[verifier] get-item: $item_json"

reward="$(python3 - "$item_json" <<'PY'
import json, sys
try:
    data = json.loads(sys.argv[1] or "{}")
except Exception:
    print(0); raise SystemExit
item = data.get("Item") or {}
state = (item.get("state") or {}).get("S")
batch = (item.get("reconciled_batch") or {}).get("S")
print(1 if state == "reconciled" and batch == "pay-20260630-batch7" else 0)
PY
)"

echo "$reward" > /logs/verifier/reward.txt
echo "reward=$reward"
exit 0
