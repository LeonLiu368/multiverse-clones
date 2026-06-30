from __future__ import annotations

import base64
import copy
import json
import os
import tempfile
import time
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any


DEFAULT_STATE_FILE = "/data/aws-clone/state.json"
DEFAULT_RUNTIME_STATE_FILE = "/var/lib/aws-clone/state.json"
DEFAULT_ENDPOINT_URL = "http://localhost:4566"
DEFAULT_ACCOUNT_ID = "000000000000"
DEFAULT_REGION = "us-east-1"


class StateError(ValueError):
    pass


REQUIRED_TOP_LEVEL: dict[str, type] = {
    "meta": dict,
    "s3": dict,
    "sqs": dict,
    "sns": dict,
    "dynamodb": dict,
    "eventbridge": dict,
    "cloudwatch_logs": dict,
    "ssm": dict,
    "secretsmanager": dict,
    "iam": dict,
    "lambda": dict,
    "mutation_log": list,
}


def state_file_from_env() -> Path:
    return Path(os.environ.get("AWS_CLONE_STATE_FILE", DEFAULT_STATE_FILE))


def runtime_state_file_from_env() -> Path:
    return Path(os.environ.get("AWS_CLONE_RUNTIME_STATE_FILE", DEFAULT_RUNTIME_STATE_FILE))


def endpoint_url_from_env() -> str:
    return os.environ.get("AWS_ENDPOINT_URL") or os.environ.get("LOCALSTACK_ENDPOINT_URL") or DEFAULT_ENDPOINT_URL


def validate_state(state: dict[str, Any]) -> None:
    if not isinstance(state, dict):
        raise StateError("state root must be an object")
    for key, expected_type in REQUIRED_TOP_LEVEL.items():
        if key not in state:
            raise StateError(f"missing required state key: {key}")
        if not isinstance(state[key], expected_type):
            raise StateError(f"state.{key} must be {expected_type.__name__}")

    meta = state["meta"]
    if not isinstance(meta.get("region", DEFAULT_REGION), str):
        raise StateError("meta.region must be a string")
    if not isinstance(meta.get("account_id", DEFAULT_ACCOUNT_ID), str):
        raise StateError("meta.account_id must be a string")

    _validate_named_collection(state["s3"].get("buckets", []), "s3.buckets")
    _validate_named_collection(state["sqs"].get("queues", []), "sqs.queues")
    _validate_named_collection(state["sns"].get("topics", []), "sns.topics")
    _validate_named_collection(state["dynamodb"].get("tables", []), "dynamodb.tables")
    _validate_named_collection(state["eventbridge"].get("rules", []), "eventbridge.rules")
    _validate_named_collection(state["cloudwatch_logs"].get("groups", []), "cloudwatch_logs.groups")
    _validate_named_collection(state["ssm"].get("parameters", []), "ssm.parameters")
    _validate_named_collection(state["secretsmanager"].get("secrets", []), "secretsmanager.secrets")
    _validate_named_collection(state["iam"].get("roles", []), "iam.roles")

    for table in state["dynamodb"].get("tables", []):
        if not isinstance(table.get("key_schema", []), list):
            raise StateError(f"dynamodb table {table.get('name')} key_schema must be a list")
        if not isinstance(table.get("attribute_definitions", []), list):
            raise StateError(f"dynamodb table {table.get('name')} attribute_definitions must be a list")


def _validate_named_collection(items: Any, path: str) -> None:
    if not isinstance(items, list):
        raise StateError(f"{path} must be a list")
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise StateError(f"{path}[{index}] must be an object")
        name = item.get("name") or item.get("function_name")
        if not isinstance(name, str) or not name:
            raise StateError(f"{path}[{index}].name is required")
        if name in seen:
            raise StateError(f"duplicate {path} name: {name}")
        seen.add(name)


def load_state(path: str | Path | None = None) -> dict[str, Any]:
    state_path = Path(path) if path else state_file_from_env()
    with state_path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    validate_state(state)
    return state


def ensure_runtime_state(seed_path: str | Path | None = None, runtime_path: str | Path | None = None) -> dict[str, Any]:
    seed = Path(seed_path) if seed_path else state_file_from_env()
    runtime = Path(runtime_path) if runtime_path else runtime_state_file_from_env()
    if runtime.exists():
        return load_state(runtime)
    state = load_state(seed)
    write_state_atomic(runtime, state)
    return state


def write_state_atomic(path: str | Path, state: dict[str, Any]) -> None:
    validate_state(state)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def seed_localstack(state: dict[str, Any] | None = None, endpoint_url: str | None = None) -> dict[str, Any]:
    actual_state = copy.deepcopy(state) if state is not None else ensure_runtime_state()
    validate_state(actual_state)
    endpoint = endpoint_url or endpoint_url_from_env()
    region = str(actual_state.get("meta", {}).get("region") or DEFAULT_REGION)
    clients = _clients(endpoint, region)
    summary: dict[str, Any] = {"endpoint_url": endpoint, "region": region, "seeded": []}

    for name, func in [
        ("s3", seed_s3),
        ("sqs", seed_sqs),
        ("sns", seed_sns),
        ("dynamodb", seed_dynamodb),
        ("eventbridge", seed_eventbridge),
        ("cloudwatch_logs", seed_logs),
        ("ssm", seed_ssm),
        ("secretsmanager", seed_secrets),
        ("iam", seed_iam),
        ("lambda", seed_lambda),
        ("kinesis", seed_kinesis),
    ]:
        started = time.time()
        func(actual_state, clients)
        summary["seeded"].append({"service": name, "seconds": round(time.time() - started, 3)})
    return summary


def _clients(endpoint_url: str, region: str) -> dict[str, Any]:
    import boto3

    session = boto3.session.Session(
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        region_name=region,
    )
    return {
        name: session.client(name, endpoint_url=endpoint_url, region_name=region)
        for name in [
            "s3",
            "sqs",
            "sns",
            "dynamodb",
            "events",
            "logs",
            "ssm",
            "secretsmanager",
            "iam",
            "lambda",
            "sts",
            "kinesis",
        ]
    }


def seed_s3(state: dict[str, Any], clients: dict[str, Any]) -> None:
    s3 = clients["s3"]
    region = str(state.get("meta", {}).get("region") or DEFAULT_REGION)
    for bucket in state["s3"].get("buckets", []):
        name = bucket["name"]
        try:
            kwargs: dict[str, Any] = {"Bucket": name}
            if region != "us-east-1":
                kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
            s3.create_bucket(**kwargs)
        except Exception as exc:
            if not _is_already_exists(exc):
                raise
        for obj in bucket.get("objects", []):
            body, content_type = _object_body(obj)
            kwargs = {
                "Bucket": name,
                "Key": obj["key"],
                "Body": body,
                "Metadata": {str(k): str(v) for k, v in obj.get("metadata", {}).items()},
            }
            if content_type:
                kwargs["ContentType"] = content_type
            s3.put_object(**kwargs)


def seed_sqs(state: dict[str, Any], clients: dict[str, Any]) -> None:
    sqs = clients["sqs"]
    queue_urls: dict[str, str] = {}
    for queue in state["sqs"].get("queues", []):
        attrs = {str(k): str(v) for k, v in queue.get("attributes", {}).items() if k != "RedrivePolicy"}
        queue_urls[queue["name"]] = sqs.create_queue(QueueName=queue["name"], Attributes=attrs)["QueueUrl"]
    for queue in state["sqs"].get("queues", []):
        redrive = queue.get("attributes", {}).get("RedrivePolicy")
        if redrive:
            sqs.set_queue_attributes(QueueUrl=queue_urls[queue["name"]], Attributes={"RedrivePolicy": str(redrive)})
    for queue in state["sqs"].get("queues", []):
        for message in queue.get("messages", []):
            sqs.send_message(
                QueueUrl=queue_urls[queue["name"]],
                MessageBody=_message_body(message),
                MessageAttributes=_message_attributes(message.get("attributes", {})),
            )


def seed_sns(state: dict[str, Any], clients: dict[str, Any]) -> None:
    sns = clients["sns"]
    sqs = clients["sqs"]
    queue_arns: dict[str, str] = {}
    for queue in state["sqs"].get("queues", []):
        url = sqs.get_queue_url(QueueName=queue["name"])["QueueUrl"]
        queue_arns[queue["name"]] = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]

    for topic in state["sns"].get("topics", []):
        topic_arn = sns.create_topic(Name=topic["name"])["TopicArn"]
        for sub in topic.get("subscriptions", []):
            protocol = sub.get("protocol", "sqs")
            endpoint = sub.get("endpoint")
            if protocol == "sqs" and sub.get("endpoint_queue"):
                endpoint = queue_arns[sub["endpoint_queue"]]
            response = sns.subscribe(TopicArn=topic_arn, Protocol=protocol, Endpoint=endpoint or "", ReturnSubscriptionArn=True)
            attrs: dict[str, str] = {}
            if "filter_policy" in sub:
                attrs["FilterPolicy"] = json.dumps(sub["filter_policy"], separators=(",", ":"))
            for key, value in attrs.items():
                sns.set_subscription_attributes(SubscriptionArn=response["SubscriptionArn"], AttributeName=key, AttributeValue=value)


def seed_dynamodb(state: dict[str, Any], clients: dict[str, Any]) -> None:
    dynamodb = clients["dynamodb"]
    for table in state["dynamodb"].get("tables", []):
        name = table["name"]
        try:
            kwargs: dict[str, Any] = {
                "TableName": name,
                "KeySchema": table["key_schema"],
                "AttributeDefinitions": table["attribute_definitions"],
            }
            if table.get("billing_mode", "PAY_PER_REQUEST") == "PAY_PER_REQUEST":
                kwargs["BillingMode"] = "PAY_PER_REQUEST"
            else:
                kwargs["ProvisionedThroughput"] = table.get("provisioned_throughput", {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5})
            dynamodb.create_table(**kwargs)
        except Exception as exc:
            if not _is_resource_in_use(exc):
                raise
        for item in table.get("items", []):
            dynamodb.put_item(TableName=name, Item=item)


def seed_eventbridge(state: dict[str, Any], clients: dict[str, Any]) -> None:
    events = clients["events"]
    for rule in state["eventbridge"].get("rules", []):
        kwargs: dict[str, Any] = {"Name": rule["name"], "State": rule.get("state", "ENABLED")}
        if rule.get("schedule"):
            kwargs["ScheduleExpression"] = rule["schedule"]
        if rule.get("event_pattern"):
            kwargs["EventPattern"] = json.dumps(rule["event_pattern"], separators=(",", ":"))
        if rule.get("description"):
            kwargs["Description"] = rule["description"]
        events.put_rule(**kwargs)
        targets = rule.get("targets", [])
        if targets:
            events.put_targets(
                Rule=rule["name"],
                Targets=[
                    {k: v for k, v in {"Id": t.get("id"), "Arn": t.get("arn"), "Input": _json_or_string(t.get("input"))}.items() if v is not None}
                    for t in targets
                ],
            )


def seed_logs(state: dict[str, Any], clients: dict[str, Any]) -> None:
    logs = clients["logs"]
    for group in state["cloudwatch_logs"].get("groups", []):
        try:
            logs.create_log_group(logGroupName=group["name"])
        except Exception as exc:
            if not _is_already_exists(exc):
                raise
        for stream in group.get("streams", []):
            try:
                logs.create_log_stream(logGroupName=group["name"], logStreamName=stream["name"])
            except Exception as exc:
                if not _is_already_exists(exc):
                    raise
            events = [
                {"timestamp": _timestamp_ms(event["timestamp"]), "message": str(event["message"])}
                for event in stream.get("events", [])
            ]
            if events:
                logs.put_log_events(logGroupName=group["name"], logStreamName=stream["name"], logEvents=sorted(events, key=lambda item: item["timestamp"]))


def seed_ssm(state: dict[str, Any], clients: dict[str, Any]) -> None:
    ssm = clients["ssm"]
    for param in state["ssm"].get("parameters", []):
        ssm.put_parameter(
            Name=param["name"],
            Type=param.get("type", "String"),
            Value=str(param.get("value", "")),
            Description=param.get("description", ""),
            Overwrite=True,
        )


def seed_secrets(state: dict[str, Any], clients: dict[str, Any]) -> None:
    secrets = clients["secretsmanager"]
    for secret in state["secretsmanager"].get("secrets", []):
        name = secret["name"]
        versions = secret.get("versions") or [{"version_id": "v1", "stages": ["AWSCURRENT"]}]
        version_ids = [str(version.get("version_id") or f"v{index + 1}") for index, version in enumerate(versions)]
        version_tokens = {version_id: _secret_version_token(name, version_id) for version_id in version_ids}
        try:
            secrets.create_secret(
                Name=name,
                Description=secret.get("description", ""),
                SecretString=secret.get("secret_string", "REDACTED"),
                ClientRequestToken=version_tokens[version_ids[0]],
            )
        except Exception as exc:
            if not _is_already_exists(exc):
                raise
        for index, version in enumerate(versions[1:], start=1):
            version_id = version_ids[index]
            secrets.put_secret_value(
                SecretId=name,
                ClientRequestToken=version_tokens[version_id],
                SecretString=version.get("secret_string", secret.get("secret_string", "REDACTED")),
                VersionStages=version.get("stages", []),
            )
        for index, version in enumerate(versions):
            version_id = version_ids[index]
            for stage in version.get("stages", []):
                try:
                    secrets.update_secret_version_stage(SecretId=name, VersionStage=stage, MoveToVersionId=version_tokens[version_id])
                except Exception:
                    pass


def seed_iam(state: dict[str, Any], clients: dict[str, Any]) -> None:
    iam = clients["iam"]
    assume_policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}],
        }
    )
    for role in state["iam"].get("roles", []):
        try:
            iam.create_role(RoleName=role["name"], AssumeRolePolicyDocument=role.get("assume_role_policy_document", assume_policy))
        except Exception as exc:
            if not _is_already_exists(exc):
                raise
        for policy in role.get("policies", []):
            doc = {"Version": "2012-10-17", "Statement": policy.get("statements", [])}
            iam.put_role_policy(RoleName=role["name"], PolicyName=policy["name"], PolicyDocument=json.dumps(doc))
    # IAM users power the credential report (GetCredentialReport) and user-principal policy
    # simulation. "users" is OPTIONAL so pre-existing state files still validate. Access-key/login
    # CREATE DATES cannot be set through the IAM API, so deterministic credential-report dates are
    # carried as `awsclone:<column>` user tags and overlaid by the report shim.
    for user in state["iam"].get("users", []):
        name = user["name"]
        try:
            iam.create_user(UserName=name, Path=user.get("path", "/"))
        except Exception as exc:
            if not _is_already_exists(exc):
                raise
        for policy in user.get("policies", []):
            doc = {"Version": "2012-10-17", "Statement": policy.get("statements", [])}
            iam.put_user_policy(UserName=name, PolicyName=policy["name"], PolicyDocument=json.dumps(doc))
        for key in user.get("access_keys", []):
            try:
                created = iam.create_access_key(UserName=name)["AccessKey"]
                if str(key.get("status", "Active")) == "Inactive":
                    iam.update_access_key(UserName=name, AccessKeyId=created["AccessKeyId"], Status="Inactive")
            except Exception:
                pass
        if user.get("password_enabled"):
            try:
                iam.create_login_profile(UserName=name, Password=user.get("password", "Aws-Clone-Temp-1!Aa"), PasswordResetRequired=False)
            except Exception:
                pass
        if user.get("mfa_enabled"):
            try:
                serial = iam.create_virtual_mfa_device(VirtualMFADeviceName=f"{name}-mfa")["VirtualMFADevice"]["SerialNumber"]
                iam.enable_mfa_device(UserName=name, SerialNumber=serial, AuthenticationCode1="123456", AuthenticationCode2="234567")
            except Exception:
                pass
        report_meta = user.get("credential_report") or {}
        tags = [{"Key": f"awsclone:{k}", "Value": str(v)} for k, v in report_meta.items()]
        tags += [{"Key": str(k), "Value": str(v)} for k, v in (user.get("tags") or {}).items()]
        if tags:
            try:
                iam.tag_user(UserName=name, Tags=tags)
            except Exception:
                pass


def seed_lambda(state: dict[str, Any], clients: dict[str, Any]) -> None:
    lamb = clients["lambda"]
    region = str(state.get("meta", {}).get("region") or DEFAULT_REGION)
    account = str(state.get("meta", {}).get("account_id") or DEFAULT_ACCOUNT_ID)
    for function in state["lambda"].get("functions", []):
        name = function["function_name"]
        try:
            lamb.create_function(
                FunctionName=name,
                Runtime=function.get("runtime", "python3.11"),
                Role=function.get("role", f"arn:aws:iam::{account}:role/aws-clone-placeholder"),
                Handler=function.get("handler", "handler.main"),
                Code={"ZipFile": _lambda_zip_bytes()},
                Description=function.get("description", "Seeded metadata fixture for aws-clone"),
                Timeout=int(function.get("timeout", 3)),
                MemorySize=int(function.get("memory_size", 128)),
                Publish=False,
            )
        except Exception as exc:
            if not (_is_already_exists(exc) or _is_invalid_parameter(exc)):
                raise
        for mapping in function.get("event_source_mappings", []):
            try:
                lamb.create_event_source_mapping(
                    FunctionName=name,
                    EventSourceArn=mapping.get("event_source_arn"),
                    BatchSize=int(mapping.get("batch_size", 10)),
                    Enabled=bool(mapping.get("enabled", True)),
                )
            except Exception:
                pass
        log_group = function.get("log_group") or f"/aws/lambda/{name}"
        function.setdefault("function_arn", f"arn:aws:lambda:{region}:{account}:function:{name}")
        function.setdefault("log_group", log_group)


def seed_kinesis(state: dict[str, Any], clients: dict[str, Any]) -> None:
    """Seed Kinesis Data Streams + records so tasks can exercise shards, shard iterators,
    consumer lag / iterator age, and resharding. Kinesis state is OPTIONAL (older state files
    that predate this key still validate); a missing ``kinesis`` key is a no-op."""
    kinesis = clients["kinesis"]
    for stream in state.get("kinesis", {}).get("streams", []):
        name = stream["name"]
        create_kwargs: dict[str, Any] = {"StreamName": name}
        if str(stream.get("stream_mode", "PROVISIONED")).upper() == "ON_DEMAND":
            create_kwargs["StreamModeDetails"] = {"StreamMode": "ON_DEMAND"}
        else:
            create_kwargs["ShardCount"] = int(stream.get("shard_count", 1))
        try:
            kinesis.create_stream(**create_kwargs)
        except Exception as exc:
            if not (_is_already_exists(exc) or _is_resource_in_use(exc)):
                raise
        _wait_stream_active(kinesis, name)
        retention = stream.get("retention_hours")
        if retention is not None and int(retention) != 24:
            try:
                if int(retention) > 24:
                    kinesis.increase_stream_retention_period(StreamName=name, RetentionPeriodHours=int(retention))
                else:
                    kinesis.decrease_stream_retention_period(StreamName=name, RetentionPeriodHours=int(retention))
            except Exception:
                pass
        records = stream.get("records", [])
        for batch in _chunks(records, 500):
            entries = []
            for record in batch:
                entry: dict[str, Any] = {
                    "Data": _kinesis_record_data(record),
                    "PartitionKey": str(record.get("partition_key", "pk")),
                }
                if record.get("explicit_hash_key") is not None:
                    entry["ExplicitHashKey"] = str(record["explicit_hash_key"])
                entries.append(entry)
            if entries:
                kinesis.put_records(StreamName=name, Records=entries)
        tags = stream.get("tags") or {}
        if tags:
            try:
                kinesis.add_tags_to_stream(StreamName=name, Tags={str(k): str(v) for k, v in tags.items()})
            except Exception:
                pass


def _kinesis_record_data(record: dict[str, Any]) -> bytes:
    if "data_b64" in record:
        return base64.b64decode(record["data_b64"])
    if "data_json" in record:
        return json.dumps(record["data_json"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    return str(record.get("data", "")).encode("utf-8")


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _wait_stream_active(kinesis: Any, name: str, attempts: int = 40, delay: float = 0.5) -> None:
    for _ in range(attempts):
        try:
            status = kinesis.describe_stream_summary(StreamName=name)["StreamDescriptionSummary"]["StreamStatus"]
        except Exception:
            status = None
        if status == "ACTIVE":
            return
        time.sleep(delay)


def _object_body(obj: dict[str, Any]) -> tuple[bytes | str, str | None]:
    if "body_json" in obj:
        return json.dumps(obj["body_json"], sort_keys=True, separators=(",", ":")), "application/json"
    if "body_b64" in obj:
        return base64.b64decode(obj["body_b64"]), obj.get("content_type")
    return str(obj.get("body", "")), obj.get("content_type")


def _message_body(message: dict[str, Any]) -> str:
    if "body_json" in message:
        return json.dumps(message["body_json"], sort_keys=True, separators=(",", ":"))
    return str(message.get("body", ""))


def _message_attributes(attrs: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {str(key): {"DataType": "String", "StringValue": str(value)} for key, value in attrs.items()}


def _json_or_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"))


def _timestamp_ms(value: str | int | float) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    from datetime import datetime

    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _lambda_zip_bytes() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("handler.py", "def main(event, context):\n    return {'ok': True}\n")
    return buffer.getvalue()


def _secret_version_token(secret_name: str, version_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in f"{secret_name}-{version_id}")
    token = f"aws-clone-{safe}"
    if len(token) < 32:
        token = f"{token}-{'0' * (31 - len(token))}"
    return token[:64]


def _is_already_exists(exc: Exception) -> bool:
    text = str(exc)
    return any(code in text for code in ["AlreadyExists", "BucketAlreadyOwnedByYou", "EntityAlreadyExists", "ResourceAlreadyExists", "ResourceConflictException"])


def _is_resource_in_use(exc: Exception) -> bool:
    return "ResourceInUseException" in str(exc) or "Table already exists" in str(exc)


def _is_invalid_parameter(exc: Exception) -> bool:
    return "InvalidParameter" in str(exc) or "ValidationException" in str(exc)


def main() -> int:
    state = ensure_runtime_state()
    summary = seed_localstack(state)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
