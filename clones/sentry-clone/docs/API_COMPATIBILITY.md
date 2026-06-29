# API Compatibility

Sentry-clone implements a benchmark-focused subset of Sentry-shaped APIs. It is not a full Sentry implementation.

## Endpoints

- `GET /api/0/organizations/`: list organizations.
- `GET /api/0/organizations/{org_slug}/projects/`: list projects.
- `GET /api/0/projects/{org_slug}/{project_slug}/`: get project.
- `GET /api/0/projects/{org_slug}/{project_slug}/issues/`: list project issues.
- `GET /api/0/organizations/{org_slug}/issues/`: list organization issues.
- `GET /api/0/issues/{issue_id}/`: get issue by numeric id or short id.
- `PUT /api/0/issues/{issue_id}/`: update issue fields.
- `GET /api/0/issues/{issue_id}/events/`: list events.
- `GET /api/0/issues/{issue_id}/events/latest/`: get latest event.
- `GET /api/0/projects/{org_slug}/{project_slug}/events/{event_id}/`: get event.
- `GET /api/0/organizations/{org_slug}/releases/`: list releases.
- `GET /api/0/organizations/{org_slug}/releases/{version}/`: get release.
- `GET /api/0/issues/{issue_id}/suspect-commits/`: list suspect commits.
- `GET /api/0/issues/{issue_id}/comments/`: list comments.
- `POST /api/0/issues/{issue_id}/comments/`: add comment.
- `GET /api/0/issues/{issue_id}/activity/`: list activity.

Verifier-only endpoints:

- `GET /api/_clone/state`
- `GET /api/_clone/mutations`

These require `SENTRY_CLONE_ENABLE_ADMIN_API=1` and `SENTRY_CLONE_ADMIN_TOKEN`. Normal `SENTRY_AUTH_TOKEN` receives `403` or `404`.

## Query Syntax

Issue lists support:

- `is:unresolved`
- `is:resolved`
- `is:ignored`
- `is:regressed`
- `is:for_review`
- `is:escalating`
- `level:error`
- `environment:production`
- `release:<version>`
- `assigned:none`
- `project:<slug>`
- arbitrary tag filters such as `error_type:validation_conflict`

Sorting supports `lastSeen`, `firstSeen`, `events`, and `users`.

`statsPeriod=24h` and `statsPeriod=14d` are deterministic fixture fields or no-op fields; no live time-series aggregation is performed.

## Unsupported Areas

Sentry-clone does not implement ingestion DSNs, real auth providers, source maps, alert rules, performance tracing, org membership management, billing, or Sentry Cloud behavior outside this local benchmark subset.
