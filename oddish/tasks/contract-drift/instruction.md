# Failing tests in the payments client

The `acme-payments` codebase is checked out at **`/workspace`**. Its test suite is currently
failing:

```bash
cd /workspace && python -m pytest -q
```

`payments/charge.py::build_charge_request` still targets the **old, deprecated** charges-API
request format. The API was migrated to a new contract — new field names, units (the amount
field changed), a version marker, and a newly-required field — and the client was never
updated. The new contract was communicated by the platform team in the workspace, not written
into this repo. Recover the **current** contract and update `build_charge_request` so the
**whole suite passes**, without breaking tests that already pass.

You have the **`slack`** workspace tool (CLI + MCP) — run `slack help` to see it. The migration
was announced there; read carefully, because at least one field name was **corrected** partway
through the discussion, and older messages still describe the deprecated format.
