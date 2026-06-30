"""The one capability matrix shared by the MCP server (and mirrored by the CLI).

Every function here is a **thin client** of an existing HTTP surface:

* the AWS/data-plane tools (``s3_*``, ``sqs_*``, ``dynamodb_*``, ``logs_*``,
  ``ssm_*``, ``secrets_*``, ``events_*``, ``iam_*``, ``sts_*``, ``kinesis_*``)
  call **boto3 against ``AWS_ENDPOINT_URL``** — the same LocalStack endpoint the
  agent's ``aws``/``awslocal`` CLI hits. No business logic lives here; LocalStack
  (plus the IAM hybrid shim that loads via ``sitecustomize`` when
  ``PYTHONPATH`` includes ``/opt/awscli``) is the single source of truth.
* the operator reads (``admin_*``) call the token-gated admin HTTP API via the
  same ``AwsCloneAdminClient`` the ``aws-clonectl`` CLI uses.

This module deliberately has **no dependency on the ``mcp`` package**, so the
capability surface is unit-testable and the CLI<->MCP parity tests can import it
directly. ``server.py`` registers each function as a FastMCP tool.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any


def endpoint_url() -> str:
    return os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")


def region() -> str:
    return os.environ.get("AWS_DEFAULT_REGION", "us-east-1")


@lru_cache(maxsize=None)
def _client(service: str) -> Any:
    import boto3

    return boto3.client(
        service,
        endpoint_url=endpoint_url(),
        region_name=region(),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    )


def reset_clients() -> None:
    """Drop cached boto3 clients (tests that retarget AWS_ENDPOINT_URL use this)."""
    _client.cache_clear()


def _json_safe(obj: Any) -> Any:
    """boto3 returns datetimes / bytes / Decimals; normalise to JSON-able values."""
    return json.loads(json.dumps(obj, default=str))


# ---------------------------------------------------------------------------
# S3
# ---------------------------------------------------------------------------
def s3_list_buckets() -> dict[str, Any]:
    """List S3 buckets (mirrors ``aws s3api list-buckets`` / ``aws s3 ls``)."""
    return _json_safe(_client("s3").list_buckets())


def s3_list_objects(bucket: str, prefix: str | None = None) -> dict[str, Any]:
    """List objects in an S3 bucket, optionally under a key prefix."""
    kwargs: dict[str, Any] = {"Bucket": bucket}
    if prefix:
        kwargs["Prefix"] = prefix
    return _json_safe(_client("s3").list_objects_v2(**kwargs))


def s3_get_object(bucket: str, key: str) -> dict[str, Any]:
    """Fetch an S3 object's body + metadata (mirrors ``aws s3 cp s3://.. -``)."""
    resp = _client("s3").get_object(Bucket=bucket, Key=key)
    body = resp["Body"].read()
    text = body.decode("utf-8", errors="replace")
    out: dict[str, Any] = {
        "bucket": bucket,
        "key": key,
        "content_type": resp.get("ContentType"),
        "metadata": resp.get("Metadata", {}),
        "body": text,
    }
    try:
        out["body_json"] = json.loads(text)
    except json.JSONDecodeError:
        pass
    return out


def s3_put_object(bucket: str, key: str, body: str) -> dict[str, Any]:
    """Write an S3 object (mirrors ``aws s3 cp - s3://..`` / ``put-object``)."""
    return _json_safe(_client("s3").put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8")))


# ---------------------------------------------------------------------------
# SQS
# ---------------------------------------------------------------------------
def sqs_list_queues() -> dict[str, Any]:
    """List SQS queue URLs (mirrors ``aws sqs list-queues``)."""
    return _json_safe(_client("sqs").list_queues())


def sqs_get_queue_url(queue_name: str) -> dict[str, Any]:
    """Resolve a queue name to its URL (mirrors ``aws sqs get-queue-url``)."""
    return _json_safe(_client("sqs").get_queue_url(QueueName=queue_name))


def sqs_receive_messages(queue_name: str, max_messages: int = 10) -> dict[str, Any]:
    """Receive messages from a queue by name (mirrors ``aws sqs receive-message``)."""
    sqs = _client("sqs")
    url = sqs.get_queue_url(QueueName=queue_name)["QueueUrl"]
    return _json_safe(
        sqs.receive_message(
            QueueUrl=url,
            MaxNumberOfMessages=min(max_messages, 10),
            VisibilityTimeout=0,
            WaitTimeSeconds=0,
            MessageAttributeNames=["All"],
            AttributeNames=["All"],
        )
    )


def sqs_send_message(queue_name: str, body: str) -> dict[str, Any]:
    """Send a message to a queue by name (mirrors ``aws sqs send-message``)."""
    sqs = _client("sqs")
    url = sqs.get_queue_url(QueueName=queue_name)["QueueUrl"]
    return _json_safe(sqs.send_message(QueueUrl=url, MessageBody=body))


# ---------------------------------------------------------------------------
# DynamoDB
# ---------------------------------------------------------------------------
def dynamodb_list_tables() -> dict[str, Any]:
    """List DynamoDB tables (mirrors ``aws dynamodb list-tables``)."""
    return _json_safe(_client("dynamodb").list_tables())


def dynamodb_get_item(table_name: str, key: dict[str, Any]) -> dict[str, Any]:
    """Get one item by typed key, e.g. key={"event_id":{"S":"evt_001"}} (``get-item``)."""
    return _json_safe(_client("dynamodb").get_item(TableName=table_name, Key=key))


def dynamodb_put_item(table_name: str, item: dict[str, Any]) -> dict[str, Any]:
    """Put a typed item (mirrors ``aws dynamodb put-item``)."""
    return _json_safe(_client("dynamodb").put_item(TableName=table_name, Item=item))


def dynamodb_scan(table_name: str) -> dict[str, Any]:
    """Scan a table (mirrors ``aws dynamodb scan``)."""
    return _json_safe(_client("dynamodb").scan(TableName=table_name))


# ---------------------------------------------------------------------------
# CloudWatch Logs
# ---------------------------------------------------------------------------
def logs_describe_groups() -> dict[str, Any]:
    """List CloudWatch log groups (mirrors ``aws logs describe-log-groups``)."""
    return _json_safe(_client("logs").describe_log_groups())


def logs_filter_events(log_group_name: str, filter_pattern: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Filter log events by pattern (mirrors ``aws logs filter-log-events``)."""
    kwargs: dict[str, Any] = {"logGroupName": log_group_name, "limit": limit}
    if filter_pattern:
        kwargs["filterPattern"] = filter_pattern
    return _json_safe(_client("logs").filter_log_events(**kwargs))


# ---------------------------------------------------------------------------
# SSM Parameter Store
# ---------------------------------------------------------------------------
def ssm_get_parameter(name: str, with_decryption: bool = False) -> dict[str, Any]:
    """Read an SSM parameter (mirrors ``aws ssm get-parameter``)."""
    return _json_safe(_client("ssm").get_parameter(Name=name, WithDecryption=with_decryption))


# ---------------------------------------------------------------------------
# Secrets Manager
# ---------------------------------------------------------------------------
def secrets_describe(secret_id: str) -> dict[str, Any]:
    """Describe a secret's metadata/versions (mirrors ``aws secretsmanager describe-secret``)."""
    return _json_safe(_client("secretsmanager").describe_secret(SecretId=secret_id))


# ---------------------------------------------------------------------------
# EventBridge
# ---------------------------------------------------------------------------
def events_list_rules() -> dict[str, Any]:
    """List EventBridge rules (mirrors ``aws events list-rules``)."""
    return _json_safe(_client("events").list_rules())


def events_list_targets(rule: str) -> dict[str, Any]:
    """List a rule's targets (mirrors ``aws events list-targets-by-rule``)."""
    return _json_safe(_client("events").list_targets_by_rule(Rule=rule))


# ---------------------------------------------------------------------------
# IAM (LocalStack + hybrid shim for simulate-* / credential report)
# ---------------------------------------------------------------------------
def iam_simulate_custom_policy(policy_input_list: list[str], action_names: list[str]) -> dict[str, Any]:
    """Simulate custom policies against actions (mirrors ``aws iam simulate-custom-policy``)."""
    return _json_safe(
        _client("iam").simulate_custom_policy(PolicyInputList=policy_input_list, ActionNames=action_names)
    )


def iam_simulate_principal_policy(policy_source_arn: str, action_names: list[str]) -> dict[str, Any]:
    """Simulate a principal's effective policy (mirrors ``aws iam simulate-principal-policy``)."""
    return _json_safe(
        _client("iam").simulate_principal_policy(PolicySourceArn=policy_source_arn, ActionNames=action_names)
    )


def iam_get_credential_report() -> dict[str, Any]:
    """Fetch the credential report; decodes Content to text (``aws iam get-credential-report``)."""
    resp = _client("iam").get_credential_report()
    content = resp.get("Content", b"")
    if isinstance(content, (bytes, bytearray)):
        text = content.decode("utf-8", errors="replace")
    else:
        text = str(content)
    out = _json_safe({k: v for k, v in resp.items() if k != "Content"})
    out["Content"] = text
    return out


# ---------------------------------------------------------------------------
# STS
# ---------------------------------------------------------------------------
def sts_get_caller_identity() -> dict[str, Any]:
    """Return the caller identity (mirrors ``aws sts get-caller-identity``)."""
    return _json_safe(_client("sts").get_caller_identity())


# ---------------------------------------------------------------------------
# Kinesis
# ---------------------------------------------------------------------------
def kinesis_list_streams() -> dict[str, Any]:
    """List Kinesis streams (mirrors ``aws kinesis list-streams``)."""
    return _json_safe(_client("kinesis").list_streams())


def kinesis_describe_stream_summary(stream_name: str) -> dict[str, Any]:
    """Describe a stream summary (mirrors ``aws kinesis describe-stream-summary``)."""
    return _json_safe(_client("kinesis").describe_stream_summary(StreamName=stream_name))


# ---------------------------------------------------------------------------
# Operator-only admin reads (same surface as the aws-clonectl CLI)
# ---------------------------------------------------------------------------
def _admin_client() -> Any:
    from aws_clone.cli.client import AwsCloneAdminClient

    return AwsCloneAdminClient()


def admin_state() -> Any:
    """Operator snapshot of clone state (mirrors ``aws-clonectl state``)."""
    return _admin_client().state()


def admin_mutations() -> Any:
    """Operator mutation log (mirrors ``aws-clonectl mutations``)."""
    return _admin_client().mutations()
