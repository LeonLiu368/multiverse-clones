# HIDDEN grading test (staged by the verifier only at grade time; never in the agent's
# container during the run). Pins the EXACT v2 charges-API contract: field names
# (api_version, amount_cents, customer, currency, idempotency_key), integer-cent units, the
# version marker, the currency default and override. These appear ONLY here and in the
# workspace platform announcements — never in the repo or visible tests — so passing requires
# recovering the agreed contract from the workspace (including the customer_id -> customer
# correction).
from decimal import Decimal, ROUND_HALF_UP

from payments.charge import build_charge_request


def _expected(amount, customer, idem, currency="usd"):
    cents = int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return {
        "api_version": 2,
        "amount_cents": cents,
        "customer": customer,
        "currency": currency,
        "idempotency_key": idem,
    }


def test_charge_request_matches_v2_contract():
    cases = [
        (("12.50", "cus_42", "idem_abc"), {}),
        (("0.99", "c1", "k1"), {}),
        (("100", "c2", "k2"), {}),
        (("5.00", "c3", "k3"), {"currency": "eur"}),
    ]
    for args, kw in cases:
        got = build_charge_request(*args, **kw)
        want = _expected(*args, **kw)
        assert got == want, (args, kw, got, want)
