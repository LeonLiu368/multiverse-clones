# Failing tests in the billing service

The `acme-billing` codebase is checked out at **`/workspace`**. Its test suite is currently
failing:

```bash
cd /workspace && python -m pytest -q
```

The overdue-fee calculation (`billing/fees.py::overdue_fee`) was never implemented. The team
**agreed the exact policy** — grace period, tier rates, minimum, cap, rounding, edge cases —
but it was settled in discussion, not written into the repo. Recover the agreed policy and
implement `overdue_fee` so the **whole suite passes**, without breaking tests that already
pass.

You have the **`slack`** workspace tool (CLI + MCP) — run `slack help` to see it. The policy
was hashed out there; note that several **earlier proposals were revised** before the team
settled, so read carefully and use the *agreed* values, not superseded ones.
