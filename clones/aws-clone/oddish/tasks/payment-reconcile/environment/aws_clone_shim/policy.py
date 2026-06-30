"""Focused IAM identity-policy evaluator backing SimulatePrincipalPolicy / SimulateCustomPolicy.

This is the deterministic substitute for moto/LocalStack's missing IAM policy simulator. It models
the part of AWS's evaluation logic that the common "why is this principal getting AccessDenied" SRE
task needs:

  - Explicit ``Deny`` has highest precedence (a matching Deny anywhere => ``explicitDeny``).
  - A permission boundary, when present, must also allow (intersection); otherwise ``implicitDeny``.
  - Otherwise a matching ``Allow`` => ``allowed``; nothing matches => ``implicitDeny``.
  - ``Action``/``NotAction`` matched with AWS wildcards (``*``/``?``), case-insensitive.
  - ``Resource``/``NotResource`` matched with AWS wildcards, case-sensitive.
  - Common ``Condition`` operators against a caller-supplied context; a statement whose conditions
    are not satisfied does not apply, and referenced-but-absent context keys are reported as
    ``MissingContextValues`` (AWS-faithful).

Deliberately NOT modeled (documented in docs/LOCALSTACK-COMPATIBILITY.md): resource-based policies,
SCPs/Organizations, session policies, and IAM policy variables. Those paths fall through to
``implicitDeny`` when no identity statement matches, which is the correct decision for the
unmodeled-allow case.
"""
from __future__ import annotations

import fnmatch
from typing import Any, Iterable


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _action_matches(patterns: Iterable[str], action: str) -> bool:
    action_l = action.lower()
    return any(fnmatch.fnmatchcase(action_l, str(pattern).lower()) for pattern in patterns)


def _resource_matches(patterns: Iterable[str], resource: str) -> bool:
    # Resource ARNs are case-sensitive; "*" matches everything.
    return any(pattern == "*" or fnmatch.fnmatchcase(resource, str(pattern)) for pattern in patterns)


_STRING_OPS = {
    "StringEquals": lambda ctx, vals: ctx in vals,
    "StringNotEquals": lambda ctx, vals: ctx not in vals,
    "StringEqualsIgnoreCase": lambda ctx, vals: ctx.lower() in {v.lower() for v in vals},
    "StringLike": lambda ctx, vals: any(fnmatch.fnmatchcase(ctx, v) for v in vals),
    "StringNotLike": lambda ctx, vals: not any(fnmatch.fnmatchcase(ctx, v) for v in vals),
    "ArnLike": lambda ctx, vals: any(fnmatch.fnmatchcase(ctx, v) for v in vals),
    "ArnEquals": lambda ctx, vals: ctx in vals,
    "ArnNotLike": lambda ctx, vals: not any(fnmatch.fnmatchcase(ctx, v) for v in vals),
}


def _condition_block_satisfied(operator: str, mapping: dict[str, Any], context: dict[str, Any], missing: set[str]) -> bool:
    base = operator
    if_exists = base.endswith("IfExists")
    if if_exists:
        base = base[: -len("IfExists")]
    for key, raw_values in mapping.items():
        values = [str(v) for v in _as_list(raw_values)]
        if base == "Null":
            present = key in context and context[key] is not None
            want_absent = str(values[0]).lower() == "true" if values else False
            if (present and want_absent) or (not present and not want_absent):
                return False
            continue
        if key not in context or context[key] is None:
            if if_exists:
                continue
            missing.add(key)
            return False
        ctx_value = str(context[key])
        if base == "Bool":
            if (str(ctx_value).lower() == "true") != (str(values[0]).lower() == "true"):
                return False
            continue
        op = _STRING_OPS.get(base)
        if op is None:
            # Unmodeled operator: be conservative — treat the statement as not applying.
            return False
        if not op(ctx_value, values):
            return False
    return True


def _conditions_satisfied(statement: dict[str, Any], context: dict[str, Any], missing: set[str]) -> bool:
    conditions = statement.get("Condition") or {}
    for operator, mapping in conditions.items():
        if not _condition_block_satisfied(operator, mapping, context, missing):
            return False
    return True


def _statement_applies(statement: dict[str, Any], action: str, resource: str, context: dict[str, Any], missing: set[str]) -> bool:
    if "Action" in statement:
        if not _action_matches(_as_list(statement["Action"]), action):
            return False
    elif "NotAction" in statement:
        if _action_matches(_as_list(statement["NotAction"]), action):
            return False
    else:
        return False  # neither Action nor NotAction -> not a usable statement
    if "Resource" in statement:
        if not _resource_matches(_as_list(statement["Resource"]), resource):
            return False
    elif "NotResource" in statement:
        if _resource_matches(_as_list(statement["NotResource"]), resource):
            return False
    # absent Resource/NotResource -> no resource constraint (matches any)
    return _conditions_satisfied(statement, context, missing)


def _eval(statements: Iterable[dict[str, Any]], action: str, resource: str, context: dict[str, Any]) -> dict[str, Any]:
    allow = False
    explicit_deny = False
    matched: list[dict[str, Any]] = []
    missing: set[str] = set()
    for statement in statements:
        if not isinstance(statement, dict):
            continue
        if not _statement_applies(statement, action, resource, context, missing):
            continue
        effect = str(statement.get("Effect", "Deny"))
        matched.append(statement)
        if effect == "Deny":
            explicit_deny = True
        elif effect == "Allow":
            allow = True
    return {"allow": allow, "explicit_deny": explicit_deny, "matched": matched, "missing": missing}


def evaluate(
    action: str,
    resource: str,
    *,
    identity_statements: Iterable[dict[str, Any]],
    boundary_statements: Iterable[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return {"decision": allowed|explicitDeny|implicitDeny, "matched_statements": [...],
    "missing_context_values": [...]} for one (action, resource) pair."""
    ctx = dict(context or {})
    identity = list(identity_statements or [])
    id_eval = _eval(identity, action, resource, ctx)
    missing = set(id_eval["missing"])

    if id_eval["explicit_deny"]:
        return _result("explicitDeny", id_eval["matched"], missing)

    if boundary_statements is not None:
        b_eval = _eval(list(boundary_statements), action, resource, ctx)
        missing |= b_eval["missing"]
        if b_eval["explicit_deny"]:
            return _result("explicitDeny", id_eval["matched"] + b_eval["matched"], missing)
        if not b_eval["allow"]:
            return _result("implicitDeny", id_eval["matched"], missing)

    if id_eval["allow"]:
        return _result("allowed", id_eval["matched"], missing)
    return _result("implicitDeny", id_eval["matched"], missing)


def _result(decision: str, matched: list[dict[str, Any]], missing: set[str]) -> dict[str, Any]:
    return {"decision": decision, "matched_statements": matched, "missing_context_values": sorted(missing)}
