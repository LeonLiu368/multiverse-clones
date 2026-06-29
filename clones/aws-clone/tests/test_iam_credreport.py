from __future__ import annotations

import csv
import io

from aws_clone_shim.credreport import COLUMNS, build_credential_report


def _rows(content: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(content.decode("utf-8"))))


def test_header_root_and_user_rows():
    users = [
        {
            "user": "alice",
            "arn": "arn:aws:iam::000000000000:user/alice",
            "user_creation_time": "2026-01-01T00:00:00+00:00",
            "password_enabled": True,
            "mfa_active": False,
            "access_keys": [{"active": True, "last_rotated": "2025-01-01T00:00:00+00:00"}],
        }
    ]
    rows = _rows(build_credential_report(users))
    assert rows[0] == COLUMNS
    assert rows[1][0] == "<root_account>"
    assert rows[2][0] == "alice"
    assert rows[2][COLUMNS.index("password_enabled")] == "true"
    assert rows[2][COLUMNS.index("mfa_active")] == "false"
    assert rows[2][COLUMNS.index("access_key_1_active")] == "true"
    assert rows[2][COLUMNS.index("access_key_2_active")] == "false"


def test_user_without_keys_defaults_to_false():
    users = [{"user": "svc", "arn": "arn:aws:iam::0:user/svc", "password_enabled": False, "mfa_active": True, "access_keys": []}]
    rows = _rows(build_credential_report(users))
    assert rows[2][COLUMNS.index("access_key_1_active")] == "false"
    assert rows[2][COLUMNS.index("mfa_active")] == "true"


def test_empty_report_still_has_header_and_root():
    rows = _rows(build_credential_report([]))
    assert rows[0] == COLUMNS
    assert rows[1][0] == "<root_account>"
    assert len(rows) == 2
