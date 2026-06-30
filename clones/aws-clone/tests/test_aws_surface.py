"""Per-capability AWS endpoint + tool tests against a LIVE gateway (R6.1).

These run **inside the running gateway container** (where the pinned
botocore 1.33 + the IAM hybrid shim live), because that is the realistic
verifier path: the host's newer botocore speaks a SQS/JSON protocol LocalStack
3.8.1 does not, and the IAM shim only loads when ``/opt/awscli`` is on
``PYTHONPATH`` (i.e. inside the image). Each capability gets a happy path and,
where the product returns one, a realistic typed error (the real AWS error code,
not a 500). The in-container calls go through ``aws_clone.mcp.tools`` — the same
functions the CLI and MCP both use.

Gated on:
  AWS_CLONE_RUN_LIVE=1
  AWS_CLONE_LIVE_CONTAINER=<name of a running aws-clone gateway container>

Stand up a gateway (e.g. `docker run --name awsfix_prodv1 aws-clone-service:prod-v1`),
wait for healthy, then:

    AWS_CLONE_RUN_LIVE=1 AWS_CLONE_LIVE_CONTAINER=awsfix_prodv1 \
      python -m pytest tests/test_aws_surface.py -q
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from tests.helpers import docker_available

LIVE = os.environ.get("AWS_CLONE_RUN_LIVE") == "1"
CONTAINER = os.environ.get("AWS_CLONE_LIVE_CONTAINER", "")
pytestmark = pytest.mark.skipif(
    not LIVE or not CONTAINER or not shutil.which("docker") or not docker_available(),
    reason="set AWS_CLONE_RUN_LIVE=1 and AWS_CLONE_LIVE_CONTAINER=<gateway> with Docker",
)


def call(func: str, *json_args: object) -> object:
    """Invoke aws_clone.mcp.tools.<func>(*args) inside the gateway container.

    Returns the parsed result on success, or raises AssertionError carrying the
    captured error class + AWS error code so error-path tests can assert on it.
    """
    args_literal = ", ".join(json.dumps(a) for a in json_args)
    script = (
        "import json,sys\n"
        "from aws_clone.mcp import tools\n"
        "try:\n"
        f"    print('OK'+json.dumps(tools.{func}({args_literal})))\n"
        "except Exception as e:\n"
        "    code=getattr(e,'response',{}).get('Error',{}).get('Code')\n"
        "    print('ERR'+json.dumps({'cls':type(e).__name__,'code':code,'msg':str(e)}))\n"
    )
    out = subprocess.run(
        ["docker", "exec", "-e", "PYTHONPATH=/opt/aws-clone:/opt/awscli", CONTAINER, "python", "-c", script],
        text=True, capture_output=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    line = out.stdout.strip().splitlines()[-1]
    if line.startswith("OK"):
        return json.loads(line[2:])
    raise _ToolError(json.loads(line[3:]))


class _ToolError(Exception):
    def __init__(self, info: dict) -> None:
        super().__init__(info.get("msg"))
        self.code = info.get("code")
        self.cls = info.get("cls")


# ---- S3 ----
def test_s3_list_buckets_happy() -> None:
    assert any(b["Name"] == "acme-payment-exports" for b in call("s3_list_buckets")["Buckets"])


def test_s3_get_object_happy() -> None:
    obj = call("s3_get_object", "acme-payment-exports", "exports/2026-06-07/manifest.json")
    assert obj["body_json"]["records"] == 128


def test_s3_get_object_missing_key_error() -> None:
    with pytest.raises(_ToolError) as exc:
        call("s3_get_object", "acme-payment-exports", "does/not/exist.json")
    assert exc.value.code in ("NoSuchKey", "404", "NotFound")


# ---- SQS ----
def test_sqs_list_queues_happy() -> None:
    assert any(u.endswith("/payment-webhook-retry") for u in call("sqs_list_queues")["QueueUrls"])


def test_sqs_receive_messages_happy() -> None:
    msgs = call("sqs_receive_messages", "payment-webhook-retry")["Messages"]
    assert any("evt_001" in m["Body"] for m in msgs)


def test_sqs_unknown_queue_error() -> None:
    with pytest.raises(_ToolError) as exc:
        call("sqs_get_queue_url", "no-such-queue")
    assert "NonExistentQueue" in (exc.value.code or "")


# ---- DynamoDB (the assessment-grade round-trip) ----
def test_dynamodb_get_item_happy() -> None:
    item = call("dynamodb_get_item", "payment-idempotency", {"event_id": {"S": "evt_001"}})["Item"]
    assert item["state"]["S"] == "scheduled"


def test_dynamodb_put_then_get_roundtrip() -> None:
    call("dynamodb_put_item", "payment-idempotency", {"event_id": {"S": "evt_rt"}, "state": {"S": "done"}})
    got = call("dynamodb_get_item", "payment-idempotency", {"event_id": {"S": "evt_rt"}})["Item"]
    assert got["state"]["S"] == "done"


def test_dynamodb_missing_table_error() -> None:
    with pytest.raises(_ToolError) as exc:
        call("dynamodb_get_item", "no_such_table", {"event_id": {"S": "x"}})
    assert exc.value.code == "ResourceNotFoundException"


# ---- CloudWatch Logs ----
def test_logs_filter_events_query_grammar() -> None:
    events = call("logs_filter_events", "/aws/lambda/payment-webhook-worker", "validation_conflict")["events"]
    assert events and "validation_conflict" in events[0]["message"]


# ---- SSM / Secrets ----
def test_ssm_get_parameter_happy() -> None:
    assert call("ssm_get_parameter", "/payments/retry/max_attempts")["Parameter"]["Value"] == "3"


def test_ssm_missing_parameter_error() -> None:
    with pytest.raises(_ToolError) as exc:
        call("ssm_get_parameter", "/payments/retry/does-not-exist")
    assert exc.value.code == "ParameterNotFound"


def test_secrets_describe_happy() -> None:
    desc = call("secrets_describe", "payments/provider/api-key")
    assert any("AWSCURRENT" in stages for stages in desc["VersionIdsToStages"].values())


# ---- EventBridge ----
def test_events_rules_and_targets() -> None:
    assert call("events_list_rules")["Rules"][0]["Name"] == "nightly-ledger-close"
    assert call("events_list_targets", "nightly-ledger-close")["Targets"][0]["Id"] == "ledger-close-worker"


# ---- IAM (hybrid shim) ----
def test_iam_simulate_principal_policy_devops() -> None:
    sim = call(
        "iam_simulate_principal_policy",
        "arn:aws:iam::000000000000:role/payment-worker-role",
        ["sqs:ReceiveMessage", "s3:GetObject"],
    )
    decisions = {r["EvalActionName"]: r["EvalDecision"] for r in sim["EvaluationResults"]}
    assert decisions["sqs:ReceiveMessage"] == "allowed"
    assert decisions["s3:GetObject"] == "implicitDeny"


def test_iam_credential_report_bytes() -> None:
    report = call("iam_get_credential_report")
    assert "legacy-batch-uploader" in report["Content"]


# ---- STS ----
def test_sts_caller_identity() -> None:
    assert call("sts_get_caller_identity")["Account"] == "000000000000"


# ---- Kinesis ----
def test_kinesis_streams_summary() -> None:
    assert "payment-events-stream" in call("kinesis_list_streams")["StreamNames"]
    summary = call("kinesis_describe_stream_summary", "payment-events-stream")
    assert summary["StreamDescriptionSummary"]["OpenShardCount"] == 2
