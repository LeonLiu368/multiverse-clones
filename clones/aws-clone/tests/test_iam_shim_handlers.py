from __future__ import annotations

import json

import pytest

from aws_clone_shim import handlers


class FakeIam:
    def __init__(self, *, role_inline=None, role_attached=None, role_boundary_arn=None, managed=None,
                 users=None, login_profiles=None, mfa=None, access_keys=None):
        self.role_inline = role_inline or {}
        self.role_attached = role_attached or []
        self.role_boundary_arn = role_boundary_arn
        self.managed = managed or {}
        self.users = users or []
        self.login_profiles = set(login_profiles or [])
        self.mfa = mfa or {}
        self.access_keys = access_keys or {}

    def list_role_policies(self, RoleName):
        return {"PolicyNames": list(self.role_inline)}

    def get_role_policy(self, RoleName, PolicyName):
        return {"PolicyDocument": self.role_inline[PolicyName]}

    def list_attached_role_policies(self, RoleName):
        return {"AttachedPolicies": self.role_attached}

    def get_role(self, RoleName):
        role = {}
        if self.role_boundary_arn:
            role["PermissionsBoundary"] = {"PermissionsBoundaryArn": self.role_boundary_arn}
        return {"Role": role}

    def get_policy(self, PolicyArn):
        return {"Policy": {"DefaultVersionId": "v1"}}

    def get_policy_version(self, PolicyArn, VersionId):
        return {"PolicyVersion": {"Document": self.managed.get(PolicyArn, {})}}

    def list_users(self):
        return {"Users": self.users}

    def get_login_profile(self, UserName):
        if UserName in self.login_profiles:
            return {"LoginProfile": {"UserName": UserName}}
        raise RuntimeError("NoSuchEntity")

    def list_mfa_devices(self, UserName):
        return {"MFADevices": self.mfa.get(UserName, [])}

    def list_access_keys(self, UserName):
        return {"AccessKeyMetadata": self.access_keys.get(UserName, [])}

    def get_access_key_last_used(self, AccessKeyId):
        return {"AccessKeyLastUsed": {}}


@pytest.fixture(autouse=True)
def _reset_cache():
    handlers._iam_client_cache = None
    yield
    handlers._iam_client_cache = None


def _doc(statements):
    return {"Version": "2012-10-17", "Statement": statements}


def test_simulate_principal_policy_implicit_deny():
    handlers._iam_client_cache = FakeIam(role_inline={"p": _doc([{"Effect": "Allow", "Action": ["sqs:ReceiveMessage"], "Resource": "*"}])})
    out = handlers.simulate_principal_policy({
        "PolicySourceArn": "arn:aws:iam::000000000000:role/payment-worker-role",
        "ActionNames": ["s3:GetObject"],
        "ResourceArns": ["arn:aws:s3:::acme/private"],
    })
    result = out["EvaluationResults"][0]
    assert result["EvalActionName"] == "s3:GetObject"
    assert result["EvalDecision"] == "implicitDeny"
    assert result["ResourceSpecificResults"][0]["EvalResourceName"] == "arn:aws:s3:::acme/private"


def test_simulate_principal_policy_allow_via_managed_and_boundary():
    handlers._iam_client_cache = FakeIam(
        role_attached=[{"PolicyArn": "arn:aws:iam::aws:policy/AmazonS3FullAccess"}],
        managed={"arn:aws:iam::aws:policy/AmazonS3FullAccess": _doc([{"Effect": "Allow", "Action": "s3:*", "Resource": "*"}])},
        role_boundary_arn="arn:aws:iam::0:policy/boundary",
    )
    # boundary only allows s3:Get*, so PutObject (allowed by identity) is boundary-denied
    handlers._iam_client_cache.managed["arn:aws:iam::0:policy/boundary"] = _doc([{"Effect": "Allow", "Action": "s3:Get*", "Resource": "*"}])
    out = handlers.simulate_principal_policy({
        "PolicySourceArn": "arn:aws:iam::0:role/r",
        "ActionNames": ["s3:GetObject", "s3:PutObject"],
    })
    by_action = {r["EvalActionName"]: r["EvalDecision"] for r in out["EvaluationResults"]}
    assert by_action["s3:GetObject"] == "allowed"
    assert by_action["s3:PutObject"] == "implicitDeny"


def test_simulate_custom_policy_explicit_deny():
    out = handlers.simulate_custom_policy({
        "PolicyInputList": [json.dumps(_doc([{"Effect": "Deny", "Action": "*", "Resource": "*"}]))],
        "ActionNames": ["s3:GetObject"],
    })
    assert out["EvaluationResults"][0]["EvalDecision"] == "explicitDeny"


def test_generate_and_get_credential_report():
    handlers._iam_client_cache = FakeIam(
        users=[{"UserName": "alice", "Arn": "arn:aws:iam::0:user/alice", "CreateDate": None}],
        login_profiles=["alice"],
        access_keys={"alice": [{"AccessKeyId": "AKIA1", "Status": "Active", "CreateDate": None}]},
    )
    assert handlers.generate_credential_report({})["State"] == "COMPLETE"
    report = handlers.get_credential_report({})
    assert report["ReportFormat"] == "text/csv"
    assert b"alice" in report["Content"]
    assert b"<root_account>" in report["Content"]


def test_before_call_passthrough_for_unshimmed_operation():
    class Model:
        name = "ListUsers"

    assert handlers._before_call(model=Model(), params={}, context={}) is None


def test_before_call_short_circuits_shimmed_operation():
    pytest.importorskip("botocore")

    class Model:
        name = "GenerateCredentialReport"

    response = handlers._before_call(model=Model(), params={}, context={handlers._STASH_KEY: {}})
    assert response is not None
    http, parsed = response
    assert http.status_code == 200
    assert parsed["State"] == "COMPLETE"
