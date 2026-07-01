# Reliability pass — triaged from the real-API parity checks (2026-07-01)

**Goal:** not perfect fidelity — just enough that each clone can host **reliable, realistically
difficult devops tasks**. We fix only two classes of divergence:

1. **Silent-wrong** — the clone accepts a correct real-world request and quietly returns the wrong
   thing (no error). Corrupts eval results in both directions. *Worse than a loud error.*
2. **Broken / fake surface** — a capability a task must exercise doesn't actually return real data,
   or lives at a path/tool that doesn't exist.

Everything else from the parity report (envelope wrapper fields, `tags` dict-vs-array, auth-returns-200,
`page_size` clamp, host flattening, IAM position stubs, Jira's native envelope shape) is **cosmetic for
this goal and intentionally NOT fixed.** Pagination is fixed only on a clone where a task's difficulty
depends on paging through volume.

Parity verdicts (context): figma/notion/slack/gws/aws/gh-cli = HIGH · sentry/grafana/logfire = MEDIUM · jira = LOW.

---

## P0 — broken surface (blocks hard devops tasks on that clone)

| # | Clone | Fix | Acceptance |
|---|---|---|---|
| 1 | **grafana** | `POST /api/ds/query` returns empty `frames:[]` + a bespoke `data` block. Populate real Grafana dataframes (`results.{refId}.frames[].schema.fields` + `data.values`). | A PromQL/LogQL panel query returns rows under `frames`, readable by a real-dataframe parser. |
| 2 | **grafana** | Alerting paths `/api/alert-rules`, `/api/alert-instances`, `/api/alert-rules/{uid}/history` are fabricated. Serve real paths (`/api/v1/provisioning/alert-rules`, `/api/prometheus/grafana/api/v1/rules`) or drop the surface. | Alert-rule read hits a real Grafana path and returns the Grafana-shaped body. |

## P0 — silent-wrong (corrupts results on any clone)

| # | Clone | Fix | Acceptance |
|---|---|---|---|
| 3 | **sentry** | List-issues has no default `is:unresolved`; empty query returns ALL issues. Default to `is:unresolved` like real Sentry. | `issues list` with no query returns only unresolved. |
| 4 | **sentry** | `sort=events/users` sorts the numeric `count`/`userCount` **lexicographically**; also accepts only `lastSeen/firstSeen/events/users` (real: `date/new/freq/user`). Sort numerically; accept real sort values. | `sort=freq` orders by numeric event count desc. |
| 5 | **google-workspace** | Gmail `is:`/`has:`/`after:`/`before:` are accepted-but-ignored → unfiltered results returned silently. Enforce them, or reject unknown operators with 400. | `q="is:unread"` returns only unread (or a 400), never the full set. |
| 6 | **slack** | `conversations.history` ignores `oldest`/`latest`/`inclusive`/`cursor` (silent no-op). Honor the time window, or reject the params. | `oldest=`/`latest=` narrows the returned messages. |
| 7 | **aws** | IAM `SimulatePrincipalPolicy` omits **group-attached** policies for users → a user allowed only via a group is wrongly `implicitDeny`. Fold in group policies. | A group-granted permission simulates `allowed`. |

## P1 — agent-facing breaks (a real-tool-competent agent's correct call fails)

| # | Clone | Fix | Acceptance |
|---|---|---|---|
| 8 | **gh-cli** | `pr merge --method merge\|squash\|rebase` has no gh analog; real gh uses `--merge/--squash/--rebase` toggles. Accept the real flags. | `ghc pr merge N --squash` works. |
| 9 | **gh-cli** | `label delete` requires the numeric Forgejo id; real `gh label delete <name>` deletes by name. Accept a name. | `ghc label delete bug` deletes the `bug` label. |
| 10 | **logfire** | MCP tool `find_exceptions` doesn't exist upstream (real: `find_exceptions_in_file`); `arbitrary_query(sql,min/max)` vs real `arbitrary_query(query, age)`. Rename/realign, or pin task prompts to the clone's tool schema. | Task prompts and clone tool names agree; no "unknown tool". |
| 11 | **grafana** | MCP names drift from `mcp-grafana`: `alerting_list_rules`→`alerting_manage_rules`, `run_dashboard_panel_query`→`run_panel_query`, `get_datasource`→`get_datasource_by_uid`. Align, or pin tasks. | Tool names match the real mcp-grafana schema an agent is prompted with. |

## P2 — honest labeling (no code change, just stop over/under-claiming)

| # | Clone | Fix |
|---|---|---|
| 12 | **jira** | Relabel in COVERAGE.md/clone-spec as a *"Jira/Linear-flavored issue tool over ticketvector"*, not a Jira REST v3 emulator. Author tasks to the CLI/RPC surface it actually has. Fix the `ENG-####` claim (seeds use real `PROJ-N` keys — currently under-claiming). |
| 13 | **coverage overclaims** | Correct `Envelope ✅`/parity claims that the checks contradicted: logfire (MCP names), grafana (`/api/ds/query` envelope), figma (components `{status,error}` wrapper). Make `docs/COVERAGE.md` match observed. |

---

## Explicitly NOT doing (cosmetic for this goal)
- figma: comment `reactions`, components `{status,error}` wrapper, POST-comment 400 boolean shape.
- notion: invalid-token→200, `page_size` clamp, `Notion-Version` not validated.
- sentry: `tags` dict-vs-array, org-scoped issue paths (legacy works), stacktrace/breadcrumbs wrapper.
- slack: `search.messages` extra `files` key, missing permalink/username.
- gws: single-host base URL, `historyId` omission, `events.insert` summary over-validation.
- aws: `EvalDecisionDetails`/`PermissionsBoundaryDecisionDetail`, stubbed statement positions.
- Pagination generally — added per-clone only if a task's difficulty needs volume paging.

## After the code fixes
Each touched gateway needs its image trio + agent **rebuilt & republished**, then the clone's
`nop=0 / oracle=1` re-validated. Then feed these per-clone "author-against-this" limitations into
`clone-task-builder`, and move on to the real lever: **task difficulty / the discrimination gradient.**
