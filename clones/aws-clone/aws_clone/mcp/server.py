"""stdio MCP server exposing the aws-clone AWS surface as MCP tools.

Every tool is a thin wrapper around a function in :mod:`aws_clone.mcp.tools`,
which itself is a thin boto3 client of the **same LocalStack endpoint**
(``AWS_ENDPOINT_URL``) the agent's ``aws``/``awslocal`` CLI uses — so the CLI and
MCP stay in lockstep by construction (one capability matrix, two front-ends).
The operator-only ``aws_admin_*`` tools wrap the token-gated admin API the
``aws-clonectl`` CLI uses; they require ``AWS_CLONE_ADMIN_TOKEN`` and are not
exposed to the agent in task packs.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import tools


def build_server() -> FastMCP:
    mcp = FastMCP("abundant-aws-clone")

    # ---- S3 ----
    @mcp.tool()
    def aws_s3_list_buckets() -> dict:
        """List all S3 buckets."""
        return tools.s3_list_buckets()

    @mcp.tool()
    def aws_s3_list_objects(bucket: str, prefix: str | None = None) -> dict:
        """List objects in an S3 bucket, optionally under a key prefix."""
        return tools.s3_list_objects(bucket, prefix)

    @mcp.tool()
    def aws_s3_get_object(bucket: str, key: str) -> dict:
        """Fetch an S3 object's body and metadata; parses JSON bodies into body_json."""
        return tools.s3_get_object(bucket, key)

    @mcp.tool()
    def aws_s3_put_object(bucket: str, key: str, body: str) -> dict:
        """Write a UTF-8 string to an S3 object key."""
        return tools.s3_put_object(bucket, key, body)

    # ---- SQS ----
    @mcp.tool()
    def aws_sqs_list_queues() -> dict:
        """List SQS queue URLs."""
        return tools.sqs_list_queues()

    @mcp.tool()
    def aws_sqs_get_queue_url(queue_name: str) -> dict:
        """Resolve an SQS queue name to its URL."""
        return tools.sqs_get_queue_url(queue_name)

    @mcp.tool()
    def aws_sqs_receive_messages(queue_name: str, max_messages: int = 10) -> dict:
        """Receive up to max_messages from a queue (by name), including attributes."""
        return tools.sqs_receive_messages(queue_name, max_messages)

    @mcp.tool()
    def aws_sqs_send_message(queue_name: str, body: str) -> dict:
        """Send a message body to a queue (by name)."""
        return tools.sqs_send_message(queue_name, body)

    # ---- DynamoDB ----
    @mcp.tool()
    def aws_dynamodb_list_tables() -> dict:
        """List DynamoDB table names."""
        return tools.dynamodb_list_tables()

    @mcp.tool()
    def aws_dynamodb_get_item(table_name: str, key: dict[str, Any]) -> dict:
        """Get one item by typed key, e.g. {"event_id": {"S": "evt_001"}}."""
        return tools.dynamodb_get_item(table_name, key)

    @mcp.tool()
    def aws_dynamodb_put_item(table_name: str, item: dict[str, Any]) -> dict:
        """Put a typed item, e.g. {"event_id": {"S": "evt_002"}, "state": {"S": "done"}}."""
        return tools.dynamodb_put_item(table_name, item)

    @mcp.tool()
    def aws_dynamodb_scan(table_name: str) -> dict:
        """Scan all items in a table."""
        return tools.dynamodb_scan(table_name)

    # ---- CloudWatch Logs ----
    @mcp.tool()
    def aws_logs_describe_groups() -> dict:
        """List CloudWatch log groups."""
        return tools.logs_describe_groups()

    @mcp.tool()
    def aws_logs_filter_events(log_group_name: str, filter_pattern: str | None = None, limit: int = 100) -> dict:
        """Filter log events in a group by a CloudWatch filter pattern."""
        return tools.logs_filter_events(log_group_name, filter_pattern, limit)

    # ---- SSM / Secrets ----
    @mcp.tool()
    def aws_ssm_get_parameter(name: str, with_decryption: bool = False) -> dict:
        """Read an SSM Parameter Store parameter by name."""
        return tools.ssm_get_parameter(name, with_decryption)

    @mcp.tool()
    def aws_secrets_describe(secret_id: str) -> dict:
        """Describe a Secrets Manager secret's metadata and version stages."""
        return tools.secrets_describe(secret_id)

    # ---- EventBridge ----
    @mcp.tool()
    def aws_events_list_rules() -> dict:
        """List EventBridge rules."""
        return tools.events_list_rules()

    @mcp.tool()
    def aws_events_list_targets(rule: str) -> dict:
        """List the targets attached to an EventBridge rule."""
        return tools.events_list_targets(rule)

    # ---- IAM ----
    @mcp.tool()
    def aws_iam_simulate_custom_policy(policy_input_list: list[str], action_names: list[str]) -> dict:
        """Simulate custom IAM policy documents against a list of actions."""
        return tools.iam_simulate_custom_policy(policy_input_list, action_names)

    @mcp.tool()
    def aws_iam_simulate_principal_policy(policy_source_arn: str, action_names: list[str]) -> dict:
        """Simulate the effective policy of an IAM principal (role/user ARN) against actions."""
        return tools.iam_simulate_principal_policy(policy_source_arn, action_names)

    @mcp.tool()
    def aws_iam_get_credential_report() -> dict:
        """Fetch the IAM credential report (Content decoded to CSV text)."""
        return tools.iam_get_credential_report()

    # ---- STS ----
    @mcp.tool()
    def aws_sts_get_caller_identity() -> dict:
        """Return the caller's account, ARN, and user id."""
        return tools.sts_get_caller_identity()

    # ---- Kinesis ----
    @mcp.tool()
    def aws_kinesis_list_streams() -> dict:
        """List Kinesis stream names."""
        return tools.kinesis_list_streams()

    @mcp.tool()
    def aws_kinesis_describe_stream_summary(stream_name: str) -> dict:
        """Describe a Kinesis stream summary (shard count, retention, status)."""
        return tools.kinesis_describe_stream_summary(stream_name)

    # ---- Operator-only admin reads (require AWS_CLONE_ADMIN_TOKEN) ----
    @mcp.tool()
    def aws_admin_state() -> Any:
        """Operator-only: snapshot of clone state (requires AWS_CLONE_ADMIN_TOKEN)."""
        return tools.admin_state()

    @mcp.tool()
    def aws_admin_mutations() -> Any:
        """Operator-only: the clone mutation log (requires AWS_CLONE_ADMIN_TOKEN)."""
        return tools.admin_mutations()

    return mcp


def main() -> None:
    """Entry point: run the MCP server over stdio."""
    build_server().run()


if __name__ == "__main__":
    main()
