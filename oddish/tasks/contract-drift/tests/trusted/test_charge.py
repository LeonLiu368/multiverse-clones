# Canonical copy (restored by the verifier before grading): invariant tests only.
import json

from payments.charge import build_charge_request


def test_returns_json_serializable_dict():
    req = build_charge_request("12.50", "cus_42", "idem_abc")
    assert isinstance(req, dict)
    json.dumps(req)


def test_includes_customer_and_idem_values():
    req = build_charge_request("12.50", "cus_42", "idem_abc")
    vals = [str(v) for v in req.values()]
    assert "cus_42" in vals
    assert "idem_abc" in vals


def test_deterministic():
    assert build_charge_request("5.00", "c", "k") == build_charge_request("5.00", "c", "k")
