# acme-billing

Internal billing utilities. Run the test suite with:

```bash
cd /workspace && python -m pytest -q
```

Some tests are currently failing. The billing **overdue-fee** rule
(`billing/fees.py::overdue_fee`) was never implemented — the exact policy was hashed out
and agreed by the team in the workspace (see the note in `billing/fees.py`). Implement it so
the whole suite passes, without breaking anything that already passes.
