# acme-monitoring

Alerting/paging logic. Run the test suite with:

```bash
cd /workspace && python -m pytest -q
```

Some tests are failing. `monitoring/alerts.py::should_page` is unimplemented after a
pager-fatigue incident — the team agreed a new paging policy during the incident, but it was
never written into this repo (see the note in that file). Recover the agreed policy and
implement `should_page` so the whole suite passes, without breaking tests that already pass.
