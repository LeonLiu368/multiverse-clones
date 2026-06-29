"""slackgw — a task-scoped Slack Web API gateway over a local SQLite store.

The agent talks to this gateway exactly as it would talk to Slack (Web API methods,
`{"ok": true, ...}` envelopes, `C…`/`U…` ids, `ts` strings, threads, reactions, snake_case error
codes, a bearer token). `app.py` serves the methods; `store.py` is the SQLite data layer, seeded
from a real Slack export by `import_export.py`. No external backend — the store is the source of truth.
"""
