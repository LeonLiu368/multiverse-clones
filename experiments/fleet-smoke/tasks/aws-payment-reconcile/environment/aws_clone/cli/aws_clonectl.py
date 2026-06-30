from __future__ import annotations

import argparse

from .client import AwsCloneAdminClient, AwsCloneClientError
from .output import emit_json, error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aws-clonectl", description="aws-clone verifier/admin CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("state")
    sub.add_parser("mutations")
    sub.add_parser("s3-buckets")
    obj = sub.add_parser("s3-object")
    obj.add_argument("--bucket", required=True)
    obj.add_argument("--key", required=True)
    sqs = sub.add_parser("sqs-messages")
    sqs.add_argument("--queue", required=True)
    ddb = sub.add_parser("dynamodb-table")
    ddb.add_argument("--name", required=True)
    logs = sub.add_parser("logs")
    logs.add_argument("--group", required=True)
    logs.add_argument("--pattern")

    args = parser.parse_args(argv)
    client = AwsCloneAdminClient()
    try:
        if args.cmd == "state":
            emit_json(client.state())
        elif args.cmd == "mutations":
            emit_json(client.mutations())
        elif args.cmd == "s3-buckets":
            emit_json(client.s3_buckets())
        elif args.cmd == "s3-object":
            emit_json(client.s3_object(args.bucket, args.key))
        elif args.cmd == "sqs-messages":
            emit_json(client.sqs_messages(args.queue))
        elif args.cmd == "dynamodb-table":
            emit_json(client.dynamodb_table(args.name))
        elif args.cmd == "logs":
            emit_json(client.logs(args.group, args.pattern))
    except AwsCloneClientError as exc:
        error(str(exc))
        return getattr(exc, "exit_code", 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
