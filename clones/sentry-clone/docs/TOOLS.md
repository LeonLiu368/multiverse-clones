# Tools

## Environment

- `SENTRY_URL`: service URL, default `http://sentry`.
- `SENTRY_AUTH_TOKEN`: normal bearer token, default `test-token-acme-eval`.
- `SENTRY_ORG`: default organization, default `acme`.
- `SENTRY_CLONE_ADMIN_TOKEN`: verifier-only token for `sentry-clonectl`.

Do not pass `SENTRY_CLONE_ADMIN_TOKEN` to agents.

## `sentry`

Every command supports `--json`.

```sh
sentry config check --json
sentry whoami --json
sentry org list --json
sentry projects list --org acme --json
sentry issues list --project payments-api --query 'is:unresolved' --json
sentry issues list --org acme --query 'is:unresolved project:payments-api' --sort lastSeen --json
sentry issues get PAYMENTS-501 --json
sentry issues events PAYMENTS-501 --json
sentry issues latest-event PAYMENTS-501 --json
sentry issues stacktrace PAYMENTS-501 --json
sentry issues breadcrumbs PAYMENTS-501 --json
sentry issues tags PAYMENTS-501 --json
sentry issues suspect-commits PAYMENTS-501 --json
sentry issues activity PAYMENTS-501 --json
sentry issues comments PAYMENTS-501 --json
sentry issues comment PAYMENTS-501 --text "Investigated in PR #1" --json
sentry issues assign PAYMENTS-501 --team payments --json
sentry issues resolve PAYMENTS-501 --in-release payments-api@2026.06.07.2 --json
sentry issues ignore PAYMENTS-501 --reason "not actionable" --json
sentry issues reopen PAYMENTS-501 --json
sentry events get evt-1001-latest --project payments-api --json
sentry releases list --project payments-api --json
sentry releases get payments-api@2026.06.07.1 --project payments-api --json
sentry releases commits payments-api@2026.06.07.1 --project payments-api --json
sentry ownership list --project payments-api --json
```

Exit codes:

- `0`: success
- `1`: user/input error
- `2`: not found
- `3`: auth/config error
- `5`: backend unavailable
- `6`: unsupported command

## `sentry-mcp`

The stdio MCP server exposes:

`list_organizations`, `list_projects`, `list_issues`, `get_issue`, `get_issue_events`, `get_latest_event`, `get_event`, `get_stacktrace`, `get_breadcrumbs`, `get_issue_tags`, `get_suspect_commits`, `list_releases`, `get_release`, `get_release_commits`, `list_comments`, `add_comment`, `assign_issue`, `resolve_issue`, `ignore_issue`, `reopen_issue`, `list_activity`, and `list_ownership_rules`.

Use `sentry-mcp --disable-write` to hide `add_comment`, `assign_issue`, `resolve_issue`, `ignore_issue`, and `reopen_issue`.

## `sentry-clonectl`

Verifier-only commands:

```sh
sentry-clonectl state
sentry-clonectl mutations
```

Requires `SENTRY_CLONE_ADMIN_TOKEN` and an enabled admin API.
