# acme-payments

Client for the internal charges API. Run the test suite with:

```bash
cd /workspace && python -m pytest -q
```

Some tests are failing. The charges API was migrated to a **new contract** and
`payments/charge.py::build_charge_request` was left unimplemented for the new version (see the
note in that file). The exact new request shape — field names, units, required fields,
version — was communicated by the platform team in the workspace, not written into this repo.
Recover it and implement `build_charge_request` so the whole suite passes, without breaking
tests that already pass.
