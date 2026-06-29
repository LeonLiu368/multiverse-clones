from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from tests.helpers import docker_available


COMPOSE = ["docker", "compose", "-f", "examples/task-pack-compose/docker-compose.yaml"]


def test_task_pack_compose_smoke() -> None:
    if os.environ.get("AWS_CLONE_RUN_DOCKER_SMOKE") != "1":
        return
    if not docker_available() or not shutil.which("docker"):
        return

    subprocess.run(["docker", "build", "-f", "Dockerfile.service", "-t", "aws-clone-service:local", "."], check=True, timeout=300)
    subprocess.run([*COMPOSE, "up", "-d", "--build"], check=True, timeout=240)
    try:
        subprocess.run([*COMPOSE, "exec", "-T", "agent", "test", "!", "-e", "/data/aws-clone/state.json"], check=True, timeout=10)
        subprocess.run([*COMPOSE, "exec", "-T", "agent", "sh", "-lc", "command -v aws && command -v awslocal && ! command -v aws-clonectl"], check=True, timeout=10)
        assert "acme-payment-exports" in _run([*COMPOSE, "exec", "-T", "agent", "awslocal", "s3", "ls"])
        manifest = _json(_run([*COMPOSE, "exec", "-T", "agent", "awslocal", "s3", "cp", "s3://acme-payment-exports/exports/2026-06-07/manifest.json", "-"]))
        assert manifest["records"] == 128
        assert "payment-webhook-retry" in _run([*COMPOSE, "exec", "-T", "agent", "awslocal", "sqs", "list-queues"])
        received = _json(_run([*COMPOSE, "exec", "-T", "agent", "sh", "-lc", "QUEUE_URL=$(awslocal sqs get-queue-url --queue-name payment-webhook-retry --query QueueUrl --output text) && awslocal sqs receive-message --queue-url \"$QUEUE_URL\" --max-number-of-messages 10 --message-attribute-names All"]))
        assert received["Messages"][0]["Body"] == '{"event_id":"evt_001","status_code":409}'
        item = _json(_run([*COMPOSE, "exec", "-T", "agent", "awslocal", "dynamodb", "get-item", "--table-name", "payment-idempotency", "--key", '{"event_id":{"S":"evt_001"}}']))
        assert item["Item"]["state"]["S"] == "scheduled"
        log_events = _json(_run([*COMPOSE, "exec", "-T", "agent", "awslocal", "logs", "filter-log-events", "--log-group-name", "/aws/lambda/payment-webhook-worker", "--filter-pattern", "validation_conflict"]))
        assert "validation_conflict" in log_events["events"][0]["message"]
        parameter = _json(_run([*COMPOSE, "exec", "-T", "agent", "awslocal", "ssm", "get-parameter", "--name", "/payments/retry/max_attempts"]))
        assert parameter["Parameter"]["Value"] == "3"
        secret = _json(_run([*COMPOSE, "exec", "-T", "agent", "awslocal", "secretsmanager", "describe-secret", "--secret-id", "payments/provider/api-key"]))
        assert any("AWSCURRENT" in stages for stages in secret["VersionIdsToStages"].values())
        assert _json(_run([*COMPOSE, "exec", "-T", "aws", "sh", "-lc", "AWS_CLONE_ADMIN_URL=http://localhost AWS_CLONE_ADMIN_TOKEN=test-admin-token-acme-eval aws-clonectl mutations"])) == []
    finally:
        subprocess.run([*COMPOSE, "down", "-v"], check=False, timeout=90)


def _run(args: list[str]) -> str:
    result = subprocess.run(args, check=True, text=True, capture_output=True, timeout=30)
    return result.stdout


def _json(text: str) -> Any:
    return json.loads(text)
