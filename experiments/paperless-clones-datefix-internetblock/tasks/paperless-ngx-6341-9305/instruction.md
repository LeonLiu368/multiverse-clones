## Your Task

I am debugging a document merge workflow where non-PDF inputs are not handled correctly during bulk merge operations, causing incorrect or failed merged output.

Please use Loki logs to determine the root cause in the merge path and implement the minimal fix. Validate with `pytest src/documents/tests/test_bulk_edit.py -k merge -q`.

## Available Tools
This is an observability task — use the observability + collaboration tools. The repo is at `/app/repo`.
- Logs (Grafana/Loki): `gcx logs query '{service="paperless-ngx"}'` (filter with `|= "500"` etc.), `gcx dashboards list`
- Issue tracker: `linear issue list`, `linear issue search "<term>"` (or the `jira` CLI)
- Team chat: `slack channels list`, `slack messages search "<term>"`
Correlate these, then fix the root cause in `/app/repo`. Do not modify the test suite.
