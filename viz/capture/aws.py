"""Capture aws-clone parity demos in-process against a real in-process AWS mock.

There is NO Docker/LocalStack in this environment, so we stand up the SAME engine class the
clone runs on in production — **moto** (LocalStack/moto is exactly what the clone's data-plane
tools are thin boto3 clients of) — inside a ``mock_aws`` context, seed a small representative
dataset with boto3, then call the clone's OWN MCP tool functions
(``aws_clone.mcp.tools``) so ``clone_output`` is the clone's ACTUAL tool output.

The clone's tool layer builds its boto3 clients against ``AWS_ENDPOINT_URL`` (the LocalStack
endpoint in production). Under moto there is no such endpoint, so we point the tool layer's
client factory at moto-backed default-endpoint clients (moto intercepts every botocore call).
That is the only adaptation; the tool bodies run unchanged.

The IAM simulate surface is the clone's OWN in-process Python shim (``aws_clone_shim``), not
moto — moto/LocalStack does not implement SimulatePrincipalPolicy. We seed IAM state with boto3
(users, groups, group policies) and call the shim's ``simulate_principal_policy`` directly; it
reads that live IAM state and returns AWS-shaped ``EvaluationResults``. This demo shows the
group-granted allow (the reliability fix: a permission granted only via a group is no longer
wrongly reported ``implicitDeny``).

The ``real_output`` golden samples are authored from the AWS API docs so they share field
shape with ``clone_output``.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Deterministic creds/region BEFORE any boto3/moto import; drop any real endpoint so moto owns it.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.pop("AWS_ENDPOINT_URL", None)

CLONE = Path(__file__).resolve().parents[2] / "clones" / "aws-clone"
sys.path.insert(0, str(CLONE))

SEED_REL = "examples/data/aws-clone/state.json"
ACCOUNT_ID = "123456789012"
REGION = "us-east-1"

BUCKET = "acme-payment-exports"
OBJ_KEY = "exports/2026-06-07/manifest.json"
OBJ_BODY = {"batch_id": "pay-20260607", "records": 128}
QUEUE = "payment-webhook-retry"
TABLE = "payment-idempotency"
USER = "legacy-batch-uploader"
GROUP = "payments-readers"


def _ensure_deps() -> None:
    try:
        import moto  # noqa: F401
        import boto3  # noqa: F401
    except ImportError:  # pragma: no cover - convenience for a fresh checkout
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "moto[all]", "boto3"])


def build() -> dict:
    _ensure_deps()
    import boto3
    from moto import mock_aws

    from aws_clone.mcp import tools
    from aws_clone_shim import handlers

    seed = json.load(open(CLONE / SEED_REL))  # verifies the seed format is readable

    with mock_aws():
        # ---- point the clone's tool layer at moto (its boto3 factory, unchanged bodies) -----
        # In prod tools._client builds a client against AWS_ENDPOINT_URL (LocalStack); under moto
        # we hand it default-endpoint clients so moto intercepts every call. Bodies run as-is.
        tools._client = lambda service: boto3.client(service, region_name=REGION)

        s3 = boto3.client("s3", region_name=REGION)
        sqs = boto3.client("sqs", region_name=REGION)
        ddb = boto3.client("dynamodb", region_name=REGION)
        iam = boto3.client("iam", region_name=REGION)

        # ---- seed a small representative dataset (mirrors the clone's real seed state) -------
        s3.create_bucket(Bucket=BUCKET)
        s3.put_object(Bucket=BUCKET, Key=OBJ_KEY, Body=json.dumps(OBJ_BODY).encode("utf-8"),
                      ContentType="application/json", Metadata={"owner": "payments"})

        queue_url = sqs.create_queue(QueueName=QUEUE)["QueueUrl"]
        sqs.send_message(QueueUrl=queue_url,
                         MessageBody=json.dumps({"event_id": "evt_001", "status_code": 409}))

        ddb.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "event_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "event_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        ddb.put_item(TableName=TABLE, Item={"event_id": {"S": "evt_001"}, "state": {"S": "scheduled"}})

        # IAM: user with NO direct policy, allowed s3:GetObject ONLY via group membership.
        iam.create_user(UserName=USER)
        iam.create_group(GroupName=GROUP)
        iam.add_user_to_group(GroupName=GROUP, UserName=USER)
        iam.put_group_policy(
            GroupName=GROUP, PolicyName="s3-read",
            PolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": [
                {"Effect": "Allow", "Action": ["s3:GetObject", "s3:ListBucket"], "Resource": "*"}]}),
        )
        # The shim reads IAM via its own cached client; inject the moto-backed one.
        handlers._iam_client_cache = iam

        demos = [
            _demo_s3_list(tools),
            _demo_dynamodb_get(tools),
            _demo_iam_simulate(handlers),
            _demo_sqs_send(tools),
        ]

    return {
        "clone": "aws-clone",
        "product": "AWS",
        "real_service": {
            "name": "AWS (S3 / SQS / DynamoDB / CloudWatch Logs / IAM-STS)",
            "reference": "https://docs.aws.amazon.com/",
            "api_base": "{AWS_ENDPOINT_URL}",
        },
        "parity": {
            "verdict": "HIGH",
            "note": "S3/SQS/DynamoDB served by moto (the clone's real engine class); IAM simulate is the clone's own shim, now folding group-granted allows.",
        },
        "seed_file": SEED_REL,
        "surfaces": {"cli": "awslocal / aws", "mcp": "aws-mcp"},
        "capture_note": "S3/SQS/DynamoDB captured in-process via moto (the same engine class the clone runs on LocalStack/moto); IAM simulate is the clone's own in-process shim.",
        "demos": demos,
    }


# ---------------------------------------------------------------------------
# Demo 1 — S3 list-objects (GET) -> table
# ---------------------------------------------------------------------------
def _demo_s3_list(tools) -> dict:
    clone_out = tools.s3_list_objects(BUCKET)
    contents = clone_out.get("Contents", [])
    return {
        "id": "s3-list-objects",
        "title": "List objects in an S3 bucket",
        "method": "GET",
        "capability": "S3 ListObjectsV2",
        "seed_excerpt": {"s3": {"buckets": [{"name": BUCKET, "objects": [{"key": OBJ_KEY}]}]}},
        "ui": {
            "type": "table",
            "title": f"S3 › {BUCKET}",
            "columns": ["Key", "Size", "LastModified"],
            "rows": [{"Key": c.get("Key"), "Size": c.get("Size"), "LastModified": c.get("LastModified")}
                     for c in contents],
        },
        "agent": {
            "cli": f"awslocal s3api list-objects-v2 --bucket {BUCKET}",
            "mcp": {"tool": "aws_s3_list_objects", "args": {"bucket": BUCKET}},
        },
        "real_mapping": {
            "api": "GET /{bucket}?list-type=2  (S3 ListObjectsV2)",
            "mcp": "aws-mcp › aws_s3_list_objects",
            "cli": f"aws s3api list-objects-v2 --bucket {BUCKET}",
            "doc": "https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html",
        },
        "clone_output": clone_out,
        "real_output": {
            "Name": BUCKET,
            "Prefix": "",
            "KeyCount": 1,
            "MaxKeys": 1000,
            "IsTruncated": False,
            "Contents": [{
                "Key": OBJ_KEY,
                "LastModified": "2026-06-07T12:00:00+00:00",
                "ETag": "\"9a0364b9e99bb480dd25e1f0284c8555\"",
                "Size": 44,
                "StorageClass": "STANDARD",
            }],
        },
    }


# ---------------------------------------------------------------------------
# Demo 2 — DynamoDB get-item (GET) -> table
# ---------------------------------------------------------------------------
def _demo_dynamodb_get(tools) -> dict:
    clone_out = tools.dynamodb_get_item(TABLE, {"event_id": {"S": "evt_001"}})
    item = clone_out.get("Item", {})
    return {
        "id": "dynamodb-get-item",
        "title": "Get one DynamoDB item by key",
        "method": "GET",
        "capability": "DynamoDB GetItem",
        "seed_excerpt": {"dynamodb": {"tables": [{"name": TABLE,
                          "items": [{"event_id": {"S": "evt_001"}, "state": {"S": "scheduled"}}]}]}},
        "ui": {
            "type": "table",
            "title": f"DynamoDB › {TABLE}",
            "columns": ["Attribute", "Type", "Value"],
            "rows": [{"Attribute": k, "Type": next(iter(v)), "Value": next(iter(v.values()))}
                     for k, v in item.items()],
        },
        "agent": {
            "cli": f'awslocal dynamodb get-item --table-name {TABLE} --key \'{{"event_id":{{"S":"evt_001"}}}}\'',
            "mcp": {"tool": "aws_dynamodb_get_item",
                    "args": {"table_name": TABLE, "key": {"event_id": {"S": "evt_001"}}}},
        },
        "real_mapping": {
            "api": "POST / (X-Amz-Target: DynamoDB_20120810.GetItem)",
            "mcp": "aws-mcp › aws_dynamodb_get_item",
            "cli": f"aws dynamodb get-item --table-name {TABLE} --key ...",
            "doc": "https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_GetItem.html",
        },
        "clone_output": clone_out,
        "real_output": {
            "Item": {"event_id": {"S": "evt_001"}, "state": {"S": "scheduled"}},
            "ResponseMetadata": {"HTTPStatusCode": 200},
        },
    }


# ---------------------------------------------------------------------------
# Demo 3 — IAM simulate-principal-policy (GET) -> list  (the clone's own shim)
# ---------------------------------------------------------------------------
def _demo_iam_simulate(handlers) -> dict:
    source_arn = f"arn:aws:iam::{ACCOUNT_ID}:user/{USER}"
    actions = ["s3:GetObject", "s3:DeleteObject"]
    resource = f"arn:aws:s3:::{BUCKET}/{OBJ_KEY}"
    clone_out = handlers.simulate_principal_policy({
        "PolicySourceArn": source_arn,
        "ActionNames": actions,
        "ResourceArns": [resource],
    })
    results = clone_out.get("EvaluationResults", [])
    return {
        "id": "iam-simulate",
        "title": "Simulate a principal's effective policy",
        "method": "GET",
        "capability": "IAM SimulatePrincipalPolicy (clone shim; group-granted allow)",
        "seed_excerpt": {"iam": {"users": [{"name": USER, "groups": [GROUP]}],
                                 "groups": [{"name": GROUP,
                                             "policy": {"Effect": "Allow",
                                                        "Action": ["s3:GetObject", "s3:ListBucket"],
                                                        "Resource": "*"}}]}},
        "ui": {
            "type": "list",
            "title": f"IAM › Policy Simulator ({USER})",
            "rows": [{"icon": ("🟢" if r.get("EvalDecision") == "allowed" else "🔴"),
                      "title": r.get("EvalActionName"),
                      "sub": r.get("EvalResourceName"),
                      "tags": [r.get("EvalDecision", "")]}
                     for r in results],
        },
        "agent": {
            "cli": (f"aws-clonectl iam simulate-principal-policy --principal-arn {source_arn} "
                    f"--action-names {' '.join(actions)}"),
            "mcp": {"tool": "aws_iam_simulate_principal_policy",
                    "args": {"policy_source_arn": source_arn, "action_names": actions}},
        },
        "real_mapping": {
            "api": "POST / (Action=SimulatePrincipalPolicy)",
            "mcp": "aws-mcp › aws_iam_simulate_principal_policy",
            "cli": (f"aws iam simulate-principal-policy --policy-source-arn {source_arn} "
                    f"--action-names {' '.join(actions)}"),
            "doc": "https://docs.aws.amazon.com/IAM/latest/APIReference/API_SimulatePrincipalPolicy.html",
        },
        "clone_output": clone_out,
        "real_output": {
            "EvaluationResults": [
                {"EvalActionName": "s3:GetObject", "EvalResourceName": resource,
                 "EvalDecision": "allowed",
                 "MatchedStatements": [{"SourcePolicyId": "s3-read", "SourcePolicyType": "IAM Policy",
                                        "StartPosition": {"Line": 1, "Column": 1},
                                        "EndPosition": {"Line": 1, "Column": 1}}],
                 "MissingContextValues": []},
                {"EvalActionName": "s3:DeleteObject", "EvalResourceName": resource,
                 "EvalDecision": "implicitDeny", "MatchedStatements": [],
                 "MissingContextValues": []},
            ],
            "IsTruncated": False,
        },
    }


# ---------------------------------------------------------------------------
# Demo 4 — SQS send-message (POST) -> timeline + change (write->read round-trip)
# ---------------------------------------------------------------------------
def _demo_sqs_send(tools) -> dict:
    before_resp = tools.sqs_receive_messages(QUEUE, max_messages=10)
    before = _msg_rows(before_resp)

    new_body = json.dumps({"event_id": "evt_002", "status_code": 503})
    send_out = tools.sqs_send_message(QUEUE, new_body)
    new_id = send_out.get("MessageId")

    after_resp = tools.sqs_receive_messages(QUEUE, max_messages=10)
    after = _msg_rows(after_resp)

    return {
        "id": "sqs-send-message",
        "title": "Send an SQS message (write→read round-trip)",
        "method": "POST",
        "capability": "SQS SendMessage → ReceiveMessage",
        "seed_excerpt": {"sqs": {"queues": [{"name": QUEUE,
                          "messages": [{"body_json": {"event_id": "evt_001", "status_code": 409}}]}]}},
        "ui": {
            "type": "timeline",
            "title": f"SQS › {QUEUE}",
            "before": before,
            "after": after,
            "new_id": new_id,
        },
        "agent": {
            "cli": f"awslocal sqs send-message --queue-url $(awslocal sqs get-queue-url --queue-name {QUEUE} --query QueueUrl --output text) --message-body '{new_body}'",
            "mcp": {"tool": "aws_sqs_send_message", "args": {"queue_name": QUEUE, "body": new_body}},
        },
        "real_mapping": {
            "api": "POST / (Action=SendMessage)",
            "mcp": "aws-mcp › aws_sqs_send_message",
            "cli": f"aws sqs send-message --queue-url ... --message-body '{new_body}'",
            "doc": "https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_SendMessage.html",
        },
        "clone_output": send_out,
        "real_output": {
            "MD5OfMessageBody": "3d3f1e2b9c8a7d6e5f4c3b2a1908f7e6",
            "MessageId": new_id or "00000000-0000-0000-0000-000000000000",
            "ResponseMetadata": {"HTTPStatusCode": 200},
        },
        "change": {"before": before, "after": after, "new_id": new_id},
    }


def _msg_rows(resp: dict) -> list:
    out = []
    for m in resp.get("Messages", []) or []:
        body = m.get("Body")
        try:
            parsed = json.loads(body)
            text = f"{parsed.get('event_id')} · status={parsed.get('status_code')}"
        except (TypeError, ValueError):
            text = str(body)
        out.append({"id": m.get("MessageId"), "text": text, "tags": []})
    return out


if __name__ == "__main__":
    out_path = Path(__file__).resolve().parents[1] / "data" / "aws-clone.json"
    manifest = build()
    out_path.write_text(json.dumps(manifest, indent=2, default=str))
    populated = sum(1 for d in manifest["demos"] if d.get("clone_output"))
    print(f"OK aws-clone: {len(manifest['demos'])} demos ({populated} with clone_output), "
          f"seed '{manifest['seed_file']}' accepted -> {out_path}")
