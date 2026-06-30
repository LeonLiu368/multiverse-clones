# Coverage matrix — `sentry-clone`

Machine-checkable enumeration of the real Sentry agent-used surface, mapping each
capability to its HTTP endpoint + `sentry` CLI command + `sentry-mcp` MCP tool, with
the response-envelope-fidelity and assessment-grade flags. Every row is covered by the
`tests/` suite. Companion narrative: `docs/API_COMPATIBILITY.md`.

Columns: **AG** = assessment-grade (rich enough to discriminate tool-use / devops skill,
≥3 of: stateful round-trip · multi-step · realistic errors · query grammar · devops side-effect).
**Env** = response envelope matches Sentry (ids, prefixes, `{detail,error,statusCode}` errors).

| Capability | Endpoint | CLI | MCP tool | Env | AG | Tested |
|---|---|---|---|---|---|---|
| list orgs | `GET /api/0/organizations/` | `org list` | `list_organizations` | ✅ | — | ✅ |
| list projects | `GET /api/0/organizations/{org}/projects/` | `projects list` | `list_projects` | ✅ | — | ✅ |
| list issues (query grammar) | `GET /api/0/projects/{org}/{proj}/issues/` · `GET /api/0/organizations/{org}/issues/` | `issues list --query` | `list_issues` | ✅ | ✅ | ✅ |
| get issue | `GET /api/0/issues/{id}/` | `issues get` | `get_issue` | ✅ | — | ✅ |
| issue events | `GET /api/0/issues/{id}/events/` | `issues events` | `get_issue_events` | ✅ | — | ✅ |
| latest event | `GET /api/0/issues/{id}/events/latest/` | `issues latest-event` | `get_latest_event` | ✅ | — | ✅ |
| get event | `GET /api/0/projects/{org}/{proj}/events/{id}/` | `events get` | `get_event` | ✅ | — | ✅ |
| stacktrace | (derived from latest event) | `issues stacktrace` | `get_stacktrace` | ✅ | ✅ | ✅ |
| breadcrumbs | (derived from latest event) | `issues breadcrumbs` | `get_breadcrumbs` | ✅ | — | ✅ |
| issue tags | (derived from issue) | `issues tags` | `get_issue_tags` | ✅ | — | ✅ |
| suspect commits | `GET /api/0/issues/{id}/suspect-commits/` | `issues suspect-commits` | `get_suspect_commits` | ✅ | ✅ | ✅ |
| list releases | `GET /api/0/organizations/{org}/releases/` | `releases list` | `list_releases` | ✅ | — | ✅ |
| get release | `GET /api/0/organizations/{org}/releases/{version}/` | `releases get` | `get_release` | ✅ | — | ✅ |
| release commits | (derived from release) | `releases commits` | `get_release_commits` | ✅ | — | ✅ |
| list comments | `GET /api/0/issues/{id}/comments/` | `issues comments` | `list_comments` | ✅ | — | ✅ |
| add comment (write) | `POST /api/0/issues/{id}/comments/` | `issues comment` | `add_comment` | ✅ | ✅ | ✅ |
| assign (write) | `PUT /api/0/issues/{id}/` | `issues assign` | `assign_issue` | ✅ | ✅ | ✅ |
| resolve (write) | `PUT /api/0/issues/{id}/` | `issues resolve` | `resolve_issue` | ✅ | ✅ | ✅ |
| ignore (write) | `PUT /api/0/issues/{id}/` | `issues ignore` | `ignore_issue` | ✅ | ✅ | ✅ |
| reopen (write) | `PUT /api/0/issues/{id}/` | `issues reopen` | `reopen_issue` | ✅ | — | ✅ |
| list activity | `GET /api/0/issues/{id}/activity/` | `issues activity` | `list_activity` | ✅ | — | ✅ |
| ownership rules | `GET /api/0/projects/{org}/{proj}/ownership/` | `ownership list` | `list_ownership_rules` | ✅ | — | ✅ |
| whoami / config | `GET /api/0/user` | `whoami` · `config check` | *(identity/config helper — not a parity gap)* | ✅ | — | ✅ |

## Parity

Every MCP tool (22) maps 1:1 to a `sentry` CLI command. CLI exposes the same 22 plus
`whoami` and `config check`, which are identity/config helpers (no MCP counterpart by
design, not a parity gap). Both surfaces are thin clients of one HTTP API
(`SentryClient`) — no business logic in either. Parity is asserted by `tests/test_parity.py`.

## Assessment-grade capabilities (R5)

Eight rows are labelled assessment-grade (≥5 required):

1. **list issues (query grammar)** — `is:` / `level:` / `environment:` / `release:` /
   `assigned:none` / `project:` / arbitrary tag filters + `lastSeen/firstSeen/events/users`
   sorts. Multi-step + query grammar.
2. **stacktrace** — multi-step root-cause investigation (list → get → stacktrace).
3. **suspect commits** — root-cause investigation chaining issue → commit → release.
4. **add comment** — stateful write→read round-trip; recorded in the mutation log.
5. **assign** — devops write; observable on a later read.
6. **resolve** — devops write→read round-trip (resolve + `resolvedInRelease`), recorded
   in the mutation log. Exercised end-to-end by the bundled `payments-incident` task.
7. **ignore** — devops write; observable on a later read.
8. **reopen / regress** — status-transition write.

**Write→read round-trip (R5.2)** is exercised by the bundled Harbor task
`tasks/payments-incident` (resolve PAYMENTS-501 in the fix release + post a comment;
verifier reads both back through the API) and asserted in `tests/test_api_mutations.py`.
