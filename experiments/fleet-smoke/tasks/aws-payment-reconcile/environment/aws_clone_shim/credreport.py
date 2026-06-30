"""Build an IAM credential report (the CSV that GetCredentialReport returns) from IAM user state.

moto/LocalStack does not implement GenerateCredentialReport; this produces the AWS-format report so
"who has stale access keys / no MFA / unused passwords" SRE tasks work deterministically. Input is a
list of normalized user records (assembled from the live IAM API by handlers.py), so the report
always reflects current IAM state.
"""
from __future__ import annotations

import csv
import io
from typing import Any

COLUMNS = [
    "user", "arn", "user_creation_time", "password_enabled", "password_last_used",
    "password_last_changed", "password_next_rotation", "mfa_active",
    "access_key_1_active", "access_key_1_last_rotated", "access_key_1_last_used_date",
    "access_key_1_last_used_region", "access_key_1_last_used_service",
    "access_key_2_active", "access_key_2_last_rotated", "access_key_2_last_used_date",
    "access_key_2_last_used_region", "access_key_2_last_used_service",
    "cert_1_active", "cert_1_last_rotated", "cert_2_active", "cert_2_last_rotated",
]


def _bool(value: Any) -> str:
    return "true" if bool(value) else "false"


def _val(value: Any, default: str = "N/A") -> str:
    if value is None or value == "":
        return default
    return str(value)


def _access_key_cells(keys: list[dict[str, Any]], index: int) -> list[str]:
    if index < len(keys):
        key = keys[index]
        return [
            _bool(key.get("active")),
            _val(key.get("last_rotated")),
            _val(key.get("last_used_date"), "N/A"),
            _val(key.get("last_used_region"), "N/A"),
            _val(key.get("last_used_service"), "N/A"),
        ]
    return ["false", "N/A", "N/A", "N/A", "N/A"]


def _user_row(user: dict[str, Any]) -> list[str]:
    keys = list(user.get("access_keys", []))[:2]
    return [
        _val(user.get("user")),
        _val(user.get("arn")),
        _val(user.get("user_creation_time")),
        _bool(user.get("password_enabled")),
        _val(user.get("password_last_used"), "no_information"),
        _val(user.get("password_last_changed")),
        _val(user.get("password_next_rotation")),
        _bool(user.get("mfa_active")),
        *_access_key_cells(keys, 0),
        *_access_key_cells(keys, 1),
        _bool(user.get("cert_1_active")),
        _val(user.get("cert_1_last_rotated")),
        _bool(user.get("cert_2_active")),
        _val(user.get("cert_2_last_rotated")),
    ]


def _root_row(account_id: str, generated_time: str) -> list[str]:
    arn = f"arn:aws:iam::{account_id}:root"
    return [
        "<root_account>", arn, generated_time, "not_supported", "no_information",
        "not_supported", "not_supported", "false",
        "false", "N/A", "N/A", "N/A", "N/A",
        "false", "N/A", "N/A", "N/A", "N/A",
        "false", "N/A", "false", "N/A",
    ]


def build_credential_report(users: list[dict[str, Any]], *, account_id: str = "000000000000", generated_time: str = "") -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMNS)
    writer.writerow(_root_row(account_id, generated_time))
    for user in users:
        writer.writerow(_user_row(user))
    return buffer.getvalue().encode("utf-8")
