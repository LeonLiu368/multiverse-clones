#!/usr/bin/env bash
set -euo pipefail

export AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-http://localhost:4566}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
export PYTHONPATH="/opt/aws-clone:/opt/awscli${PYTHONPATH:+:$PYTHONPATH}"
ADMIN_PID=""

LOCALSTACK_BIN="${LOCALSTACK_BIN:-/opt/code/localstack/.venv/bin/localstack}"
"$LOCALSTACK_BIN" start --host &
LOCALSTACK_PID="$!"

cleanup() {
  if [ -n "${LOCALSTACK_PID:-}" ]; then
    kill "$LOCALSTACK_PID" >/dev/null 2>&1 || true
  fi
  if [ -n "${ADMIN_PID:-}" ]; then
    kill "$ADMIN_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

python -m aws_clone.seed.wait_ready
python -m aws_clone.seed.load_state

python -m aws_clone.admin.app &
ADMIN_PID="$!"

wait -n "$LOCALSTACK_PID" "$ADMIN_PID"
