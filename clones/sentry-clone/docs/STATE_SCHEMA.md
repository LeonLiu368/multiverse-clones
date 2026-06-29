# State Schema

The service reads one JSON seed file from `SENTRY_CLONE_STATE_FILE`. On startup it copies that seed to `SENTRY_CLONE_RUNTIME_STATE_FILE` if no runtime state exists. All mutations update only the runtime file atomically.

Required top-level keys:

- `meta`: object with `organization` and optional fixed `now`.
- `users`: users visible to the clone.
- `teams`: Sentry-like teams.
- `projects`: project records.
- `releases`: releases with deploy and commit evidence.
- `issues`: grouped issues.
- `events`: individual events linked to issues.
- `ownership_rules`: routing rules.
- `comments`: issue comments.
- `activity`: issue activity records.
- `mutation_log`: verifier-visible mutation records.

Optional keys:

- `deploys`
- `commits`

## Examples

Project:

```json
{"id":"proj-payments","slug":"payments-api","name":"Payments API","platform":"python","team_slug":"payments"}
```

Release with commit:

```json
{
  "version": "payments-api@2026.06.07.1",
  "project_slug": "payments-api",
  "dateCreated": "2026-06-07T11:43:00Z",
  "lastDeploy": {"environment":"production","dateFinished":"2026-06-07T11:45:00Z","commit":"abc1234"},
  "commits": [{"id":"abc1234","repository":"acme/payments-api","message":"Tighten webhook retry handling","author":"dev@example.local","files":["payments/retry_policy.py"]}]
}
```

Issue:

```json
{
  "id": "1001",
  "shortId": "PAYMENTS-501",
  "project_slug": "payments-api",
  "title": "RuntimeError: unsafe retry for validation conflict",
  "status": "unresolved",
  "substatus": "new",
  "firstSeen": "2026-06-07T11:54:00Z",
  "lastSeen": "2026-06-07T11:59:00Z",
  "count": 37,
  "userCount": 12,
  "tags": {"release":"payments-api@2026.06.07.1","environment":"production"},
  "suspectCommits": [{"id":"abc1234","repository":"acme/payments-api","files":["payments/retry_policy.py"]}],
  "latestEventId": "evt-1001-latest"
}
```

Event with stacktrace and breadcrumbs:

```json
{
  "id": "evt-1001-latest",
  "issue_id": "1001",
  "project_slug": "payments-api",
  "timestamp": "2026-06-07T11:59:15Z",
  "exception": {"type":"RuntimeError","value":"unsafe retry for validation conflict"},
  "stacktrace": {"frames":[{"filename":"payments/retry_policy.py","function":"should_retry_event","lineno":42,"context_line":"return status in RETRYABLE_STATUSES","in_app":true}]},
  "breadcrumbs": [{"timestamp":"2026-06-07T11:59:10Z","category":"gateway.response","level":"info","message":"provider returned 409 validation_conflict"}],
  "contexts": {"runtime":{"name":"CPython","version":"3.11"}},
  "user": {"id":"cust-123","email":"redacted@example.local"},
  "tags": {"environment":"production"}
}
```

Ownership:

```json
{"project_slug":"payments-api","match":"payments/**","owner":"team:payments"}
```

Mutation records are appended for every write:

```json
{"id":"1","ts":"2026-06-07T12:00:00Z","actor":"agent","action":"issue.resolve","target":"issue:1001","before":{},"after":{}}
```
