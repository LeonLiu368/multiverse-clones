# Pager-fatigue incident: fix the alert and write the postmortem

The `acme-monitoring` codebase is checked out at **`/workspace`**. Its test suite is failing:

```bash
cd /workspace && python -m pytest -q
```

On-call has been getting paged at 3am all week. `monitoring/alerts.py::should_page` is
unimplemented after the team agreed a new paging policy *during the incident* — but that policy
was never written into the repo. Two things to do:

1. **Fix the code.** Recover the agreed paging policy and implement `should_page` so the whole
   suite passes (don't break tests that already pass).
2. **Write the postmortem.** Post a short postmortem to the **#postmortems** channel that states
   the **root cause** of the pager fatigue and the agreed fix.

You have the **`slack`** workspace tool (CLI + MCP) — run `slack help` to see it. The incident
was discussed and diagnosed there; read carefully (there is a red herring, and the *old* alert
thresholds still appear in older messages).
