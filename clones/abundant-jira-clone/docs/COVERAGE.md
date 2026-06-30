# Coverage matrix — abundant-jira-clone (R4 / R5)

The agent-used surface of the Jira/Linear tooling layered on the **ticketvector** issue
engine. Every capability maps to a real ticketvector `/rpc` method **and** a `jira`/`linear`
CLI command **and** a `jira-mcp` MCP tool. CLI and MCP are thin clients of the **same**
`POST /rpc` HTTP API on the `jira` sidecar (`PLANE_BASE_URL`, default `http://jira:8765`),
so they cannot drift (R3). See `mcp/server.py` for the MCP tools and the upstream
`world_issues.cli` for the CLI.

**Boundary note (R2 structural).** The CLI, the `/rpc` HTTP API, the JQL engine, and the
seed generator live in the external `ghcr.io/abundant-ai/ticketvector-service` image. This
repo owns the converters, the image trio Dockerfiles, **the MCP server (`mcp/`)**, and the
tasks. The clone surface scored here is "the jira/linear tooling on the ticketvector
engine" — see `docs/PROD-OVERLAY.md` for the explicit boundary decision.

Fidelity tier: **T2** (real JQL query grammar). Envelope shape is the product's: issue ids
`ENG-####`, `{results, next_cursor}` pagination, error envelopes `{ok:false, error_type,
error}` with `error_type ∈ {NotFoundError, ConflictError, UnsupportedCommandError, ...}`.

## Matrix

| # | Capability | `/rpc` method | CLI command | MCP tool | R/W | Envelope OK | Assessment-grade | Tested |
|---|---|---|---|---|---|---|---|---|
| 1 | Get one issue (state, assignees, priority, labels) | `get_issue` | `jira issue view <ID>` | `get_issue` | R | ✓ | — | ✓ |
| 2 | Get issue + comments/links | `get_issue`+`list_comments`/`list_links` | `jira issue view <ID> --comments --links` | `get_issue(comments,links)` | R | ✓ | — | ✓ |
| 3 | **JQL query** | `issue_list(filters=…)` | `jira jql "<JQL>"` | `search_issues(jql=…)` | R | ✓ | **★ assessment-grade** | ✓ |
| 4 | Structured issue query (assignee/state/label/priority…) + pagination | `issue_list(filters=…,cursor=…)` | `jira issue query --assignee … --cursor …` | `search_issues(assignee=…,cursor=…)` | R | ✓ | **★ assessment-grade** | ✓ |
| 5 | Free-text issue search | `issue_list(query=…)` | `jira issue search <text>` / `linear issue search` | `search_issues(query=…)` | R | ✓ | — | ✓ |
| 6 | List my issues | `issue_mine(actor)` | `linear issue mine` | `issue_mine` | R | ✓ | — | ✓ |
| 7 | List comments | `list_comments` | `jira issue view <ID> --comments` | `get_comments` | R | ✓ | — | ✓ |
| 8 | List links | `list_links` | `jira issue view <ID> --links` | `list_links` | R | ✓ | — | ✓ |
| 9 | Issue change history | `history_list` | `jira issue history <ID>` | `issue_history` | R | ✓ | — | ✓ |
| 10 | List projects | `project_list` | `jira project list` | `list_projects` | R | ✓ | — | ✓ |
| 11 | List workflow states | `list_states` | `linear state list` | `list_states` | R | ✓ | — | ✓ |
| 12 | List labels | `list_labels` | `linear label list` | `list_labels` | R | ✓ | — | ✓ |
| 13 | **Transition issue state** | `update_issue(state=…)` | `jira issue transition <ID> "<state>"` | `transition_issue` | **W** | ✓ | **★ assessment-grade** | ✓ |
| 14 | **Add comment** | `add_comment` | `jira issue comment add <ID> --body "…"` | `add_comment` | **W** | ✓ | **★ assessment-grade** | ✓ |

All 14 capabilities have CLI **and** MCP coverage (parity), and all 14 are exercised by
`tests/` (happy + error paths). The MCP server exposes 11 tools (rows 2/7 collapse onto
`get_issue`+`get_comments`; row 5 folds into `search_issues`).

## Assessment-grade subset (R5 — ≥5 labelled; we have 5★)

An endpoint is assessment-grade when it has ≥3 of: stateful round-trip · multi-step ·
realistic errors · query grammar · side-effecting devops shape.

| Capability | Stateful | Multi-step | Realistic errors | Query grammar | Devops shape | Why |
|---|:---:|:---:|:---:|:---:|:---:|---|
| **JQL query** (#3) | — | ✓ | ✓ | ✓ | — | full JQL grammar (`status=…`, `priority in (…)`, `text ~ "…"`, `assignee=me`, `ORDER BY updated`); unknown clause → `UnsupportedCommandError`; chain query→inspect |
| **Issue query + pagination** (#4) | — | ✓ | ✓ | ✓ | ✓ | structured filters + `next_cursor` paging; list→filter→count is the canonical multi-step agent loop (see `tasks/jira-assignee-count`) |
| **Transition issue** (#13) | ✓ | ✓ | ✓ | — | ✓ | write→read round-trip: `transition` then `view` shows the new state; bad state → `NotFoundError: state not found`; mirrors real ops (move ticket through workflow) |
| **Add comment** (#14) | ✓ | ✓ | ✓ | — | ✓ | write→read round-trip: `comment add` then `view --comments` shows it; unknown issue → `NotFoundError`; mirrors triage/handoff comms |
| **Get issue** (#1) | — | ✓ | ✓ | — | ✓ | the universal read used to verify every mutation; unknown id → `NotFoundError: issue not found: <ID>` (the product's real envelope) |

**R5.2 (write→read round-trip exercised end-to-end by a bundled task):** the
`jira-transition-roundtrip` task transitions an issue via the CLI and the verifier reads
the new state back through the same API — a write the agent makes, observed on a later
read. (The existing `jira-assignee-count` task exercises #4's filter+pagination read loop.)

## Out of scope (present in ticketvector, not part of the agent-used clone surface)

`issue create/delete/assign/start/done/reopen`, `link/relation/attachment` writes,
`project/state/label create`, cycles/modules, the Plane provisioning adapter, the demo
world, `snapshot`, and all `world-issues admin/seed/runtime` subcommands — the last group
is **operator-only** and blocked in the agent by `WORLD_ISSUES_AGENT_MODE=1` (R2.g). These
are intentionally not mirrored into MCP; the matrix above is the agent-realistic surface
(R4.1). Add a row here (CLI + MCP together) before a task starts depending on any of them.
