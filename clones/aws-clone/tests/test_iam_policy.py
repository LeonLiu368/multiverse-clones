from __future__ import annotations

from aws_clone_shim.policy import evaluate

ALLOW_GET = {"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": ["arn:aws:s3:::bucket/*"]}
DENY_ALL_S3 = {"Effect": "Deny", "Action": "s3:*", "Resource": "*"}


def test_allow_match():
    result = evaluate("s3:GetObject", "arn:aws:s3:::bucket/key", identity_statements=[ALLOW_GET])
    assert result["decision"] == "allowed"
    assert result["matched_statements"]


def test_implicit_deny_when_nothing_matches():
    assert evaluate("s3:PutObject", "arn:aws:s3:::bucket/key", identity_statements=[ALLOW_GET])["decision"] == "implicitDeny"


def test_explicit_deny_wins_over_allow():
    assert evaluate("s3:GetObject", "arn:aws:s3:::bucket/key", identity_statements=[ALLOW_GET, DENY_ALL_S3])["decision"] == "explicitDeny"


def test_action_wildcard():
    statement = {"Effect": "Allow", "Action": "s3:Get*", "Resource": "*"}
    assert evaluate("s3:GetObject", "arn:aws:s3:::b/k", identity_statements=[statement])["decision"] == "allowed"
    assert evaluate("s3:PutObject", "arn:aws:s3:::b/k", identity_statements=[statement])["decision"] == "implicitDeny"


def test_resource_scoping():
    statement = {"Effect": "Allow", "Action": "s3:GetObject", "Resource": "arn:aws:s3:::public/*"}
    assert evaluate("s3:GetObject", "arn:aws:s3:::public/x", identity_statements=[statement])["decision"] == "allowed"
    assert evaluate("s3:GetObject", "arn:aws:s3:::private/x", identity_statements=[statement])["decision"] == "implicitDeny"


def test_not_action():
    statement = {"Effect": "Allow", "NotAction": "iam:*", "Resource": "*"}
    assert evaluate("s3:GetObject", "x", identity_statements=[statement])["decision"] == "allowed"
    assert evaluate("iam:CreateUser", "x", identity_statements=[statement])["decision"] == "implicitDeny"


def test_permission_boundary_intersection():
    allow_all = {"Effect": "Allow", "Action": "*", "Resource": "*"}
    boundary = [{"Effect": "Allow", "Action": "s3:*", "Resource": "*"}]
    assert evaluate("ec2:StartInstances", "*", identity_statements=[allow_all], boundary_statements=boundary)["decision"] == "implicitDeny"
    assert evaluate("s3:GetObject", "*", identity_statements=[allow_all], boundary_statements=boundary)["decision"] == "allowed"


def test_boundary_explicit_deny():
    allow_all = {"Effect": "Allow", "Action": "*", "Resource": "*"}
    boundary = [{"Effect": "Deny", "Action": "s3:DeleteObject", "Resource": "*"}]
    assert evaluate("s3:DeleteObject", "*", identity_statements=[allow_all], boundary_statements=boundary)["decision"] == "explicitDeny"


def test_condition_and_missing_context():
    statement = {"Effect": "Allow", "Action": "s3:GetObject", "Resource": "*", "Condition": {"StringEquals": {"aws:username": "alice"}}}
    assert evaluate("s3:GetObject", "x", identity_statements=[statement], context={"aws:username": "alice"})["decision"] == "allowed"
    assert evaluate("s3:GetObject", "x", identity_statements=[statement], context={"aws:username": "bob"})["decision"] == "implicitDeny"
    missing = evaluate("s3:GetObject", "x", identity_statements=[statement])
    assert missing["decision"] == "implicitDeny"
    assert "aws:username" in missing["missing_context_values"]


def test_action_match_is_case_insensitive():
    statement = {"Effect": "Allow", "Action": "S3:getobject", "Resource": "*"}
    assert evaluate("s3:GetObject", "x", identity_statements=[statement])["decision"] == "allowed"
