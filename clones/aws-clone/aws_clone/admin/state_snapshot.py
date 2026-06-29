from __future__ import annotations

import copy
import json
import os
import urllib.parse
from typing import Any

from aws_clone.seed.load_state import DEFAULT_ENDPOINT_URL, ensure_runtime_state, endpoint_url_from_env, load_state, runtime_state_file_from_env


def state_snapshot() -> dict[str, Any]:
    seed_or_runtime = _runtime_state()
    snapshot = copy.deepcopy(seed_or_runtime)
    snapshot["_clone"] = {"backend": "localstack", "endpoint_url": endpoint_url_from_env()}
    try:
        snapshot["_clone"]["live"] = live_summary()
    except Exception as exc:
        snapshot["_clone"]["live_error"] = f"{type(exc).__name__}: {exc}"
    return snapshot


def mutation_log() -> list[dict[str, Any]]:
    return list(_runtime_state().get("mutation_log", []))


def s3_buckets() -> list[dict[str, Any]]:
    s3 = _client("s3")
    return [{"name": item["Name"], "creation_date": item["CreationDate"].isoformat()} for item in s3.list_buckets().get("Buckets", [])]


def s3_object(bucket: str, key: str) -> dict[str, Any]:
    s3 = _client("s3")
    response = s3.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read()
    text = body.decode("utf-8", errors="replace")
    payload: dict[str, Any] = {
        "bucket": bucket,
        "key": key,
        "content_type": response.get("ContentType"),
        "metadata": response.get("Metadata", {}),
        "body": text,
    }
    try:
        payload["body_json"] = json.loads(text)
    except json.JSONDecodeError:
        pass
    return payload


def sqs_messages(queue: str, max_messages: int = 10) -> dict[str, Any]:
    sqs = _client("sqs")
    queue_url = sqs.get_queue_url(QueueName=queue)["QueueUrl"]
    attrs = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["All"]).get("Attributes", {})
    response = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=min(max_messages, 10),
        VisibilityTimeout=0,
        WaitTimeSeconds=0,
        MessageAttributeNames=["All"],
        AttributeNames=["All"],
    )
    return {"queue": queue, "queue_url": queue_url, "attributes": attrs, "messages": response.get("Messages", [])}


def dynamodb_table(name: str) -> dict[str, Any]:
    dynamodb = _client("dynamodb")
    description = dynamodb.describe_table(TableName=name).get("Table", {})
    items = dynamodb.scan(TableName=name).get("Items", [])
    return {"table": description, "items": items}


def logs(group: str, pattern: str | None = None, limit: int = 100) -> dict[str, Any]:
    logs_client = _client("logs")
    kwargs: dict[str, Any] = {"logGroupName": group, "limit": limit}
    if pattern:
        kwargs["filterPattern"] = pattern
    response = logs_client.filter_log_events(**kwargs)
    return {"group": group, "events": response.get("events", [])}


def live_summary() -> dict[str, Any]:
    summary: dict[str, Any] = {}
    summary["s3_buckets"] = s3_buckets()
    summary["sqs_queues"] = _client("sqs").list_queues().get("QueueUrls", [])
    summary["dynamodb_tables"] = _client("dynamodb").list_tables().get("TableNames", [])
    summary["log_groups"] = [item["logGroupName"] for item in _client("logs").describe_log_groups().get("logGroups", [])]
    summary["ssm_parameters"] = [item["Name"] for item in _client("ssm").describe_parameters().get("Parameters", [])]
    summary["secrets"] = [item["Name"] for item in _client("secretsmanager").list_secrets().get("SecretList", [])]
    summary["eventbridge_rules"] = [item["Name"] for item in _client("events").list_rules().get("Rules", [])]
    return summary


def _runtime_state() -> dict[str, Any]:
    runtime = runtime_state_file_from_env()
    if runtime.exists():
        return load_state(runtime)
    return ensure_runtime_state()


def _client(service: str) -> Any:
    import boto3

    state = _runtime_state()
    region = state.get("meta", {}).get("region") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    endpoint = endpoint_url_from_env() or DEFAULT_ENDPOINT_URL
    return boto3.client(
        service,
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    )


def quote_path(value: str) -> str:
    return urllib.parse.quote(value, safe="")
