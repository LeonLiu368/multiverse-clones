"""AWS clone seed viewer (multiverse aws-clone).

The aws-clone seeds LocalStack from a single `state.json` — an imperative manifest of mock AWS
resources ({meta, s3, sqs, sns, dynamodb, lambda, iam, cloudwatch_logs, ssm, secretsmanager,
kinesis, eventbridge}). We render it as a read-only AWS-console-style resource browser: a service
sidebar + per-service resource lists (S3 buckets → objects, SQS queues → messages, DynamoDB tables →
items, Lambda functions, IAM roles/users, …). The clone bakes the corpus at
/opt/aws-clone-corpus/state.json (prod-v1) or mounts /data/aws-clone/state.json (empty)."""
from __future__ import annotations

import json
from typing import Any

from adapters.fileseed import FileSeedAdapter

# service key -> (display label, list-holding subkey)
_SERVICES: list[tuple[str, str, str]] = [
    ("s3", "S3", "buckets"),
    ("sqs", "SQS", "queues"),
    ("sns", "SNS", "topics"),
    ("dynamodb", "DynamoDB", "tables"),
    ("lambda", "Lambda", "functions"),
    ("kinesis", "Kinesis", "streams"),
    ("eventbridge", "EventBridge", "rules"),
    ("cloudwatch_logs", "CloudWatch Logs", "groups"),
    ("ssm", "SSM Parameters", "parameters"),
    ("secretsmanager", "Secrets Manager", "secrets"),
]


class AwsAdapter(FileSeedAdapter):
    id = "aws"
    display_name = "AWS"
    status = "active"
    ui_module = "aws"
    sample_files = ("aws.state.json",)
    image_substrings = ("aws-clone-service", "aws-clone", "aws-gateway")
    image_state_paths = ("/opt/aws-clone-corpus/state.json", "/data/aws-clone/state.json",
                         "/var/lib/aws-clone/state.json")

    def _parse(self, raw: str, path: str) -> dict[str, Any]:
        d = json.loads(raw)
        services: dict[str, Any] = {}
        nav: list[dict] = []
        for key, label, sub in _SERVICES:
            items = (d.get(key) or {}).get(sub) or []
            services[key] = items
            if items:
                nav.append({"key": key, "label": label, "count": len(items)})
        # IAM is a special shape: {roles, users}
        iam = d.get("iam") or {}
        roles, users = iam.get("roles") or [], iam.get("users") or []
        services["iam"] = {"roles": roles, "users": users}
        if roles or users:
            nav.append({"key": "iam", "label": "IAM", "count": len(roles) + len(users)})

        return {
            "meta": d.get("meta") or {},
            "services": services,
            "nav": nav,
            "stats": {
                "s3_buckets": len(services.get("s3", [])),
                "sqs_queues": len(services.get("sqs", [])),
                "dynamodb_tables": len(services.get("dynamodb", [])),
                "lambda_functions": len(services.get("lambda", [])),
                "iam_principals": len(roles) + len(users),
                "services": len(nav),
            },
        }
