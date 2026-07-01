"""botocore hook that serves the IAM operations moto/LocalStack does not implement, by computing
the answer from the LIVE (seeded) IAM state. Registered on every IAM client via __init__.install().

Covered operations (everything else passes straight through to LocalStack untouched):
  - SimulatePrincipalPolicy  -> evaluate the principal's identity policies (+ permission boundary)
  - SimulateCustomPolicy     -> evaluate caller-supplied PolicyInputList
  - GenerateCredentialReport -> report State=COMPLETE
  - GetCredentialReport      -> build the AWS-format credential report CSV from IAM users

Mechanism: a ``before-call`` handler short-circuits the HTTP send by returning ``(http, parsed)``
(botocore's documented fake-response path), so no wire serialization is needed. The friendly request
params are stashed by a ``before-parameter-build`` handler so the ``before-call`` handler can read
them. Policy/user data is fetched with a normal IAM client (those reads are not intercepted), so the
shim always reflects current state.
"""
from __future__ import annotations

import json
import os
import urllib.parse
from datetime import datetime, timezone
from typing import Any

from . import policy as policy_eval
from . import credreport

_SHIMMED_OPERATIONS = (
    "SimulatePrincipalPolicy",
    "SimulateCustomPolicy",
    "GenerateCredentialReport",
    "GetCredentialReport",
)
_STASH_KEY = "_aws_clone_shim_params"
_iam_client_cache: Any = None


def _ok_http() -> Any:
    from botocore.awsrequest import AWSResponse

    return AWSResponse(url="", status_code=200, headers={}, raw=None)


def _meta() -> dict[str, Any]:
    return {"RequestId": "aws-clone-shim", "HTTPStatusCode": 200}


def _iso(value: Any) -> Any:
    if value is None or isinstance(value, str):
        return value
    try:
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    except Exception:
        return str(value)


def _iam_client() -> Any:
    global _iam_client_cache
    if _iam_client_cache is not None:
        return _iam_client_cache
    import botocore.session

    endpoint = os.environ.get("AWS_ENDPOINT_URL") or os.environ.get("LOCALSTACK_ENDPOINT_URL") or "http://localhost:4566"
    region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION") or "us-east-1"
    session = botocore.session.Session()
    _iam_client_cache = session.create_client(
        "iam",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    )
    return _iam_client_cache


# ---- policy document helpers ------------------------------------------------------------------

def _doc_statements(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, str):
        try:
            document = json.loads(urllib.parse.unquote(document))
        except Exception:
            return []
    if not isinstance(document, dict):
        return []
    statements = document.get("Statement", [])
    return statements if isinstance(statements, list) else [statements]


def _managed_statements(iam: Any, policy_arn: str) -> list[dict[str, Any]]:
    try:
        default_version = iam.get_policy(PolicyArn=policy_arn)["Policy"]["DefaultVersionId"]
        document = iam.get_policy_version(PolicyArn=policy_arn, VersionId=default_version)["PolicyVersion"]["Document"]
        return _doc_statements(document)
    except Exception:
        return []


def _principal(arn: str) -> tuple[str, str]:
    tail = arn.split(":")[-1]
    parts = tail.split("/")
    return parts[0], parts[-1]


def _collect_group_statements(iam: Any, user_name: str) -> list[dict[str, Any]]:
    """Gather inline + managed/attached policy statements for every group the user is in.

    Real AWS evaluates "all policies attached to groups the user is a member of" as part of
    SimulatePrincipalPolicy. Group memberships have no permission boundary of their own, so
    only their statements are folded into the identity policy set. Any lookup that fails
    (e.g. groups unsupported by the backend) is skipped so it can only ADD allows.
    """
    statements: list[dict[str, Any]] = []
    try:
        groups = iam.list_groups_for_user(UserName=user_name).get("Groups", [])
    except Exception:
        return statements
    for group in groups:
        group_name = group.get("GroupName") if isinstance(group, dict) else group
        if not group_name:
            continue
        try:
            for policy_name in iam.list_group_policies(GroupName=group_name).get("PolicyNames", []):
                statements += _doc_statements(
                    iam.get_group_policy(GroupName=group_name, PolicyName=policy_name).get("PolicyDocument")
                )
        except Exception:
            pass
        try:
            for attached in iam.list_attached_group_policies(GroupName=group_name).get("AttachedPolicies", []):
                statements += _managed_statements(iam, attached["PolicyArn"])
        except Exception:
            pass
    return statements


def _collect_principal_statements(iam: Any, source_arn: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    kind, name = _principal(source_arn)
    statements: list[dict[str, Any]] = []
    boundary: list[dict[str, Any]] | None = None
    if kind == "role":
        for policy_name in iam.list_role_policies(RoleName=name).get("PolicyNames", []):
            statements += _doc_statements(iam.get_role_policy(RoleName=name, PolicyName=policy_name).get("PolicyDocument"))
        for attached in iam.list_attached_role_policies(RoleName=name).get("AttachedPolicies", []):
            statements += _managed_statements(iam, attached["PolicyArn"])
        principal = iam.get_role(RoleName=name)["Role"]
    else:  # user (default)
        for policy_name in iam.list_user_policies(UserName=name).get("PolicyNames", []):
            statements += _doc_statements(iam.get_user_policy(UserName=name, PolicyName=policy_name).get("PolicyDocument"))
        for attached in iam.list_attached_user_policies(UserName=name).get("AttachedPolicies", []):
            statements += _managed_statements(iam, attached["PolicyArn"])
        # Real AWS also evaluates every policy attached to the groups the user belongs to.
        # Fold in each group's inline + managed/attached policies so a permission granted
        # only via a group is not wrongly reported implicitDeny.
        statements += _collect_group_statements(iam, name)
        principal = iam.get_user(UserName=name)["User"]
    boundary_arn = (principal.get("PermissionsBoundary") or {}).get("PermissionsBoundaryArn")
    if boundary_arn:
        boundary = _managed_statements(iam, boundary_arn)
    return statements, boundary


# ---- simulate ---------------------------------------------------------------------------------

def _context_from_params(params: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for entry in params.get("ContextEntries", []) or []:
        values = entry.get("ContextKeyValues") or []
        if entry.get("ContextKeyName"):
            context[entry["ContextKeyName"]] = values[0] if values else ""
    return context


def _matched(evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for statement in evaluation["matched_statements"]:
        out.append({
            "SourcePolicyId": str(statement.get("Sid") or "aws-clone-policy"),
            "SourcePolicyType": "IAM Policy",
            "StartPosition": {"Line": 1, "Column": 1},
            "EndPosition": {"Line": 1, "Column": 1},
        })
    return out


def _evaluation_results(params: dict[str, Any], identity: list[dict[str, Any]], boundary: list[dict[str, Any]] | None) -> dict[str, Any]:
    context = _context_from_params(params)
    resources = params.get("ResourceArns") or ["*"]
    results = []
    for action in params.get("ActionNames", []) or []:
        per_resource = [
            (resource, policy_eval.evaluate(action, resource, identity_statements=identity, boundary_statements=boundary, context=context))
            for resource in resources
        ]
        first_resource, first_eval = per_resource[0]
        result: dict[str, Any] = {
            "EvalActionName": action,
            "EvalResourceName": first_resource,
            "EvalDecision": first_eval["decision"],
            "MatchedStatements": _matched(first_eval),
            "MissingContextValues": first_eval["missing_context_values"],
        }
        if params.get("ResourceArns"):
            result["ResourceSpecificResults"] = [
                {
                    "EvalResourceName": resource,
                    "EvalResourceDecision": ev["decision"],
                    "MatchedStatements": _matched(ev),
                    "MissingContextValues": ev["missing_context_values"],
                }
                for resource, ev in per_resource
            ]
        results.append(result)
    return {"EvaluationResults": results, "IsTruncated": False, "ResponseMetadata": _meta()}


def simulate_principal_policy(params: dict[str, Any]) -> dict[str, Any]:
    iam = _iam_client()
    identity, boundary = _collect_principal_statements(iam, params["PolicySourceArn"])
    return _evaluation_results(params, identity, boundary)


def simulate_custom_policy(params: dict[str, Any]) -> dict[str, Any]:
    identity: list[dict[str, Any]] = []
    for document in params.get("PolicyInputList", []) or []:
        identity += _doc_statements(document)
    boundary: list[dict[str, Any]] | None = None
    boundary_docs = params.get("PermissionsBoundaryPolicyInputList")
    if boundary_docs:
        boundary = []
        for document in boundary_docs:
            boundary += _doc_statements(document)
    return _evaluation_results(params, identity, boundary)


# ---- credential report ------------------------------------------------------------------------

def _user_records(iam: Any) -> list[dict[str, Any]]:
    records = []
    for user in iam.list_users().get("Users", []):
        name = user["UserName"]
        record: dict[str, Any] = {
            "user": name,
            "arn": user.get("Arn"),
            "user_creation_time": _iso(user.get("CreateDate")),
            "password_last_used": _iso(user.get("PasswordLastUsed")),
        }
        try:
            iam.get_login_profile(UserName=name)
            record["password_enabled"] = True
        except Exception:
            record["password_enabled"] = False
        try:
            record["mfa_active"] = bool(iam.list_mfa_devices(UserName=name).get("MFADevices"))
        except Exception:
            record["mfa_active"] = False
        keys = []
        try:
            for key in iam.list_access_keys(UserName=name).get("AccessKeyMetadata", []):
                entry = {"active": key.get("Status") == "Active", "last_rotated": _iso(key.get("CreateDate"))}
                try:
                    last_used = iam.get_access_key_last_used(AccessKeyId=key["AccessKeyId"]).get("AccessKeyLastUsed", {})
                    entry["last_used_date"] = _iso(last_used.get("LastUsedDate"))
                    entry["last_used_region"] = last_used.get("Region")
                    entry["last_used_service"] = last_used.get("ServiceName")
                except Exception:
                    pass
                keys.append(entry)
        except Exception:
            pass
        record["access_keys"] = keys
        records.append(_overlay_user_tags(iam, name, record))
    return records


def _overlay_user_tags(iam: Any, name: str, record: dict[str, Any]) -> dict[str, Any]:
    """Overlay deterministic credential-report fields seeded as ``awsclone:<column>`` user tags.
    The IAM API cannot set key/login dates, so date- and last-used-based credential-report tasks rely
    on these tags; live API data (key status, MFA presence, key count) is used when no tag overrides."""
    try:
        tags = {tag["Key"]: tag["Value"] for tag in iam.list_user_tags(UserName=name).get("Tags", [])}
    except Exception:
        return record

    def tag(field: str) -> Any:
        return tags.get("awsclone:" + field)

    for field in ("user_creation_time", "password_last_used", "password_last_changed", "password_next_rotation"):
        if tag(field) is not None:
            record[field] = tag(field)
    if tag("password_enabled") is not None:
        record["password_enabled"] = str(tag("password_enabled")).lower() == "true"
    if tag("mfa_active") is not None:
        record["mfa_active"] = str(tag("mfa_active")).lower() == "true"

    keys = record.get("access_keys", [])
    for index in (1, 2):
        if tag(f"access_key_{index}_active") is not None and index - 1 >= len(keys):
            keys.append({})
        if index - 1 < len(keys):
            key = keys[index - 1]
            for field in ("last_rotated", "last_used_date", "last_used_region", "last_used_service"):
                if tag(f"access_key_{index}_{field}") is not None:
                    key[field] = tag(f"access_key_{index}_{field}")
            if tag(f"access_key_{index}_active") is not None:
                key["active"] = str(tag(f"access_key_{index}_active")).lower() == "true"
    record["access_keys"] = keys
    return record


def get_credential_report(_params: dict[str, Any]) -> dict[str, Any]:
    iam = _iam_client()
    account_id = os.environ.get("AWS_CLONE_ACCOUNT_ID", "000000000000")
    generated = datetime.now(timezone.utc)
    content = credreport.build_credential_report(_user_records(iam), account_id=account_id, generated_time=_iso(generated))
    return {"Content": content, "ReportFormat": "text/csv", "GeneratedTime": generated, "ResponseMetadata": _meta()}


def generate_credential_report(_params: dict[str, Any]) -> dict[str, Any]:
    return {"State": "COMPLETE", "Description": "report generated by aws-clone IAM shim", "ResponseMetadata": _meta()}


_DISPATCH = {
    "SimulatePrincipalPolicy": simulate_principal_policy,
    "SimulateCustomPolicy": simulate_custom_policy,
    "GenerateCredentialReport": generate_credential_report,
    "GetCredentialReport": get_credential_report,
}


# ---- botocore event handlers ------------------------------------------------------------------

def _stash_params(params: Any, context: dict[str, Any] | None = None, **kwargs: Any) -> None:
    if context is not None:
        context[_STASH_KEY] = dict(params or {})


def _before_call(model: Any = None, params: Any = None, context: dict[str, Any] | None = None, **kwargs: Any) -> Any:
    operation = getattr(model, "name", None)
    handler = _DISPATCH.get(operation)
    if handler is None:
        return None
    friendly = (context or {}).get(_STASH_KEY, {})
    try:
        parsed = handler(friendly)
    except Exception:
        # On any shim failure, fall through to LocalStack's native (likely-erroring) behavior
        # rather than masking it — keeps the surface honest and debuggable.
        return None
    return _ok_http(), parsed


def register(client: Any) -> None:
    try:
        if getattr(client.meta, "service_model", None) is None or client.meta.service_model.service_name != "iam":
            return
        events = client.meta.events
        for operation in _SHIMMED_OPERATIONS:
            events.register(f"before-parameter-build.iam.{operation}", _stash_params)
            events.register(f"before-call.iam.{operation}", _before_call)
    except Exception:
        pass
