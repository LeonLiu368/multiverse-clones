from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from tests.helpers import docker_available


COMPOSE = ["docker", "compose", "-f", "examples/docker-compose.yaml"]
ENV = {
    **os.environ,
    "AWS_ENDPOINT_URL": "http://localhost:4566",
    "AWS_ACCESS_KEY_ID": "test",
    "AWS_SECRET_ACCESS_KEY": "test",
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_CLONE_ADMIN_TOKEN": "test-admin-token-acme-eval",
    "PYTHONPATH": os.getcwd(),
}


def test_localstack_smoke() -> None:
    if os.environ.get("AWS_CLONE_RUN_DOCKER_SMOKE") != "1":
        return
    if not docker_available() or not shutil.which("docker"):
        return

    subprocess.run(["docker", "build", "-f", "Dockerfile.service", "-t", "aws-clone-service:local", "."], check=True, timeout=300)
    subprocess.run([*COMPOSE, "up", "-d"], check=True, timeout=240)
    try:
        assert "acme-payment-exports" in _run([*COMPOSE, "exec", "-T", "aws", "awslocal", "s3", "ls"])
        manifest = _json(_run([*COMPOSE, "exec", "-T", "aws", "awslocal", "s3", "cp", "s3://acme-payment-exports/exports/2026-06-07/manifest.json", "-"]))
        assert manifest == {"batch_id": "pay-20260607", "records": 128}

        queues = _json(_run([*COMPOSE, "exec", "-T", "aws", "awslocal", "sqs", "list-queues"]))
        assert any(url.endswith("/payment-webhook-retry") for url in queues["QueueUrls"])
        received = _json(_run([*COMPOSE, "exec", "-T", "aws", "sh", "-lc", "QUEUE_URL=$(awslocal sqs get-queue-url --queue-name payment-webhook-retry --query QueueUrl --output text) && awslocal sqs receive-message --queue-url \"$QUEUE_URL\" --max-number-of-messages 10 --message-attribute-names All"]))
        assert received["Messages"][0]["Body"] == '{"event_id":"evt_001","status_code":409}'
        assert received["Messages"][0]["MessageAttributes"]["error_type"]["StringValue"] == "validation_conflict"

        tables = _json(_run([*COMPOSE, "exec", "-T", "aws", "awslocal", "dynamodb", "list-tables"]))
        assert "payment-idempotency" in tables["TableNames"]
        item = _json(_run([*COMPOSE, "exec", "-T", "aws", "awslocal", "dynamodb", "get-item", "--table-name", "payment-idempotency", "--key", '{"event_id":{"S":"evt_001"}}']))
        assert item["Item"]["state"]["S"] == "scheduled"

        log_groups = _json(_run([*COMPOSE, "exec", "-T", "aws", "awslocal", "logs", "describe-log-groups"]))
        assert log_groups["logGroups"][0]["logGroupName"] == "/aws/lambda/payment-webhook-worker"
        log_events = _json(_run([*COMPOSE, "exec", "-T", "aws", "awslocal", "logs", "filter-log-events", "--log-group-name", "/aws/lambda/payment-webhook-worker", "--filter-pattern", "validation_conflict"]))
        assert "validation_conflict" in log_events["events"][0]["message"]

        parameter = _json(_run([*COMPOSE, "exec", "-T", "aws", "awslocal", "ssm", "get-parameter", "--name", "/payments/retry/max_attempts"]))
        assert parameter["Parameter"]["Value"] == "3"
        secret = _json(_run([*COMPOSE, "exec", "-T", "aws", "awslocal", "secretsmanager", "describe-secret", "--secret-id", "payments/provider/api-key"]))
        assert "AWSCURRENT" in next(stages for version_id, stages in secret["VersionIdsToStages"].items() if version_id.endswith("-v2"))

        rules = _json(_run([*COMPOSE, "exec", "-T", "aws", "awslocal", "events", "list-rules"]))
        assert rules["Rules"][0]["Name"] == "nightly-ledger-close"
        targets = _json(_run([*COMPOSE, "exec", "-T", "aws", "awslocal", "events", "list-targets-by-rule", "--rule", "nightly-ledger-close"]))
        assert targets["Targets"][0]["Id"] == "ledger-close-worker"

        streams = _json(_run([*COMPOSE, "exec", "-T", "aws", "awslocal", "kinesis", "list-streams"]))
        assert "payment-events-stream" in streams["StreamNames"]
        summary = _json(_run([*COMPOSE, "exec", "-T", "aws", "awslocal", "kinesis", "describe-stream-summary", "--stream-name", "payment-events-stream"]))
        assert summary["StreamDescriptionSummary"]["OpenShardCount"] == 2
        shard_id = _json(_run([*COMPOSE, "exec", "-T", "aws", "awslocal", "kinesis", "list-shards", "--stream-name", "payment-events-stream"]))["Shards"][0]["ShardId"]
        iterator = _json(_run([*COMPOSE, "exec", "-T", "aws", "awslocal", "kinesis", "get-shard-iterator", "--stream-name", "payment-events-stream", "--shard-id", shard_id, "--shard-iterator-type", "TRIM_HORIZON"]))["ShardIterator"]
        assert "Records" in _json(_run([*COMPOSE, "exec", "-T", "aws", "awslocal", "kinesis", "get-records", "--shard-iterator", iterator]))

        # IAM hybrid shim (moto/LocalStack gaps): simulate-principal-policy + credential report.
        simulation = _json(_run([*COMPOSE, "exec", "-T", "aws", "awslocal", "iam", "simulate-principal-policy",
                                 "--policy-source-arn", "arn:aws:iam::000000000000:role/payment-worker-role",
                                 "--action-names", "s3:GetObject", "sqs:ReceiveMessage"]))
        decisions = {result["EvalActionName"]: result["EvalDecision"] for result in simulation["EvaluationResults"]}
        assert decisions["sqs:ReceiveMessage"] == "allowed"
        assert decisions["s3:GetObject"] == "implicitDeny"
        assert _json(_run([*COMPOSE, "exec", "-T", "aws", "awslocal", "iam", "generate-credential-report"]))["State"] == "COMPLETE"
        # get-credential-report returns Content as bytes (exactly like real AWS); awscli renders binary
        # blobs poorly, so read it via boto3 (the realistic verifier path), matching real AWS semantics.
        report_csv = _run([*COMPOSE, "exec", "-T", "aws", "python", "-c",
                           "import boto3;print(boto3.client('iam', endpoint_url='http://localhost:4566', region_name='us-east-1', "
                           "aws_access_key_id='test', aws_secret_access_key='test').get_credential_report()['Content'].decode())"])
        assert "legacy-batch-uploader" in report_csv
        assert "2024-03-02" in report_csv  # deterministic last-used date overlaid from user tags

        state = _json(_run(["bin/aws-clonectl", "state"], env=ENV))
        assert state["_clone"]["live"]["dynamodb_tables"] == ["payment-idempotency"]
    finally:
        subprocess.run([*COMPOSE, "down", "-v"], check=False, timeout=90)


def _run(args: list[str], env: dict[str, str] | None = None) -> str:
    result = subprocess.run(args, env=env, check=True, text=True, capture_output=True, timeout=30)
    return result.stdout


def _json(text: str) -> Any:
    return json.loads(text)
