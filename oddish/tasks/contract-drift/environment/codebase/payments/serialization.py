"""Serialization helpers. These work and are covered by passing tests — leave them green."""
import json
from decimal import Decimal, ROUND_HALF_UP


def dollars_to_cents(amount_dollars) -> int:
    """Convert a dollar amount (str/Decimal/number) to integer cents, half-up."""
    d = Decimal(str(amount_dollars))
    return int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def dumps_canonical(obj) -> str:
    """Deterministic JSON (sorted keys) — used when signing request bodies."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))
