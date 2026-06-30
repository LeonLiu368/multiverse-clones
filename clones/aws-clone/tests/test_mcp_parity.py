"""CLI <-> MCP parity tests (R3.3, R6.2).

Two layers:

1. **Structural parity (always runs, no backend):** every agent-facing capability
   in ``aws_clone.mcp.tools`` is registered as an MCP tool, and there are >=10
   tools. Because the CLI surface (``aws``/``awslocal``) and the MCP tools both
   call the SAME boto3-against-AWS_ENDPOINT_URL functions in ``tools.py``, parity
   holds by construction — there is no second implementation to drift.

2. **Live parity (gated on AWS_CLONE_RUN_LIVE=1 + a running LocalStack gateway):**
   for s3/sqs/dynamodb, the MCP tool result equals the real ``awslocal`` CLI JSON
   output for the same call — proving both front-ends hit the same state.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess

import pytest

from aws_clone.mcp import tools
from aws_clone.mcp.server import build_server


# Agent-facing capability functions in tools.py that MUST have a 1:1 MCP tool.
AGENT_TOOLS = {
    "aws_s3_list_buckets": tools.s3_list_buckets,
    "aws_s3_list_objects": tools.s3_list_objects,
    "aws_s3_get_object": tools.s3_get_object,
    "aws_s3_put_object": tools.s3_put_object,
    "aws_sqs_list_queues": tools.sqs_list_queues,
    "aws_sqs_get_queue_url": tools.sqs_get_queue_url,
    "aws_sqs_receive_messages": tools.sqs_receive_messages,
    "aws_sqs_send_message": tools.sqs_send_message,
    "aws_dynamodb_list_tables": tools.dynamodb_list_tables,
    "aws_dynamodb_get_item": tools.dynamodb_get_item,
    "aws_dynamodb_put_item": tools.dynamodb_put_item,
    "aws_dynamodb_scan": tools.dynamodb_scan,
    "aws_logs_describe_groups": tools.logs_describe_groups,
    "aws_logs_filter_events": tools.logs_filter_events,
    "aws_ssm_get_parameter": tools.ssm_get_parameter,
    "aws_secrets_describe": tools.secrets_describe,
    "aws_events_list_rules": tools.events_list_rules,
    "aws_events_list_targets": tools.events_list_targets,
    "aws_iam_simulate_custom_policy": tools.iam_simulate_custom_policy,
    "aws_iam_simulate_principal_policy": tools.iam_simulate_principal_policy,
    "aws_iam_get_credential_report": tools.iam_get_credential_report,
    "aws_sts_get_caller_identity": tools.sts_get_caller_identity,
    "aws_kinesis_list_streams": tools.kinesis_list_streams,
    "aws_kinesis_describe_stream_summary": tools.kinesis_describe_stream_summary,
}
OPERATOR_TOOLS = {"aws_admin_state", "aws_admin_mutations"}


def _tool_names() -> set[str]:
    server = build_server()
    return {t.name for t in asyncio.run(server.list_tools())}


def test_mcp_lists_at_least_ten_tools() -> None:
    names = _tool_names()
    assert len(names) >= 10, names


def test_every_agent_capability_has_an_mcp_tool() -> None:
    names = _tool_names()
    missing = set(AGENT_TOOLS) - names
    assert not missing, f"capabilities missing an MCP tool: {sorted(missing)}"


def test_operator_capabilities_exposed_separately() -> None:
    names = _tool_names()
    assert OPERATOR_TOOLS <= names


def test_no_orphan_tools() -> None:
    # Every registered tool maps to a known capability (no MCP-only surface).
    names = _tool_names()
    known = set(AGENT_TOOLS) | OPERATOR_TOOLS
    assert names <= known, f"unexpected MCP tools: {sorted(names - known)}"


# --------------------------------------------------------------------------
# Live parity (gated): MCP-tool result == real CLI JSON for the same call.
#
# Runs INSIDE the gateway container (pinned botocore 1.33 + shim), the realistic
# verifier path. The MCP side calls aws_clone.mcp.tools.<fn>(); the CLI side runs
# the real `awslocal`. Same state -> same data.
# --------------------------------------------------------------------------
import shutil  # noqa: E402

from tests.helpers import docker_available  # noqa: E402

LIVE = os.environ.get("AWS_CLONE_RUN_LIVE") == "1"
CONTAINER = os.environ.get("AWS_CLONE_LIVE_CONTAINER", "")
_live_skip = pytest.mark.skipif(
    not LIVE or not CONTAINER or not shutil.which("docker") or not docker_available(),
    reason="set AWS_CLONE_RUN_LIVE=1 and AWS_CLONE_LIVE_CONTAINER=<gateway> with Docker",
)


def _exec(cmd: list[str]) -> str:
    out = subprocess.run(["docker", "exec", CONTAINER, *cmd], text=True, capture_output=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout


def _cli_json(args: list[str]) -> dict:
    return json.loads(_exec(["awslocal", *args, "--output", "json"]))


def _mcp_json(func: str) -> dict:
    script = f"import json; from aws_clone.mcp import tools; print(json.dumps(tools.{func}()))"
    return json.loads(_exec(["python", "-c", script]).strip().splitlines()[-1])


@_live_skip
def test_live_parity_s3_buckets() -> None:
    cli = _cli_json(["s3api", "list-buckets"])
    mcp = _mcp_json("s3_list_buckets")
    assert {b["Name"] for b in cli["Buckets"]} == {b["Name"] for b in mcp["Buckets"]}


@_live_skip
def test_live_parity_dynamodb_list_tables() -> None:
    cli = _cli_json(["dynamodb", "list-tables"])
    mcp = _mcp_json("dynamodb_list_tables")
    assert sorted(cli["TableNames"]) == sorted(mcp["TableNames"])


@_live_skip
def test_live_parity_sqs_list_queues() -> None:
    cli = _cli_json(["sqs", "list-queues"])
    mcp = _mcp_json("sqs_list_queues")
    assert sorted(cli.get("QueueUrls", [])) == sorted(mcp.get("QueueUrls", []))
