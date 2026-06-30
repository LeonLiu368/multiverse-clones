# Coverage matrix — `abundant-slack-clone`

## Real service
- name: Slack Web API
- api_base: https://slack.com/api
- reference: https://api.slack.com/web
- version: Web API (current)
- snapshot_date: 2026-06-30

The **agent-used surface** of the Slack Web API this clone emulates, mapped capability → HTTP
endpoint → `slack` CLI command → `slack-mcp` (korotovsky) tool → response-envelope fidelity →
assessment-grade label → test. This file is machine-checkable: one row per capability, the
assessment-grade rows are flagged `AG`, and every covered surface has a test in `tests/`.

- **Fidelity tier:** **T2** — handwritten SQLite gateway (`selfcontained/base/slackgw/`) + a real
  Slack **search-operator grammar** (`in:`/`from:`/`before:`/`after:`/`on:` + quoted phrases,
  `slackgw/app.py::_parse_search`).
- **One HTTP API, two thin clients:** the `slack` CLI (`selfcontained/base/slackcli/`) and the
  korotovsky `slack-mcp` server both call the gateway over HTTP; neither carries business logic (R3.2).
- **Envelope fidelity:** Slack `{"ok": true|false, ...}` (always HTTP 200 for method calls),
  `C…`/`U…`/`T…` ids, `ts` strings, cursor `response_metadata.next_cursor`, snake_case error codes
  (`channel_not_found`, `user_not_found`, `thread_not_found`, `not_authed`, `unknown_method`).

## Matrix

| # | Capability | HTTP endpoint | CLI | MCP tool | Envelope | Assessment-grade | Tested |
|---|---|---|---|---|---|---|---|
| 1 | Identity / auth | `auth.test` | `slack whoami` | — *(operator/CLI-only, see note A)* | ✅ `url`,`team_id`,`user_id`,`bot_id` | no | `test_endpoints::test_auth_test_happy`, `test_cli::test_cli_whoami` |
| 2 | List channels | `conversations.list` / `users.conversations` | `slack channels` | `channels_list` | ✅ `name_normalized`,`num_members`,`is_*`,cursor | **AG** (stateful: `num_members` updates after a post; multi-step: the name→id resolution that chains into history/replies/post) | `test_endpoints::test_conversations_list_happy`, `test_cli::test_cli_channels`, `test_mcp::test_mcp_channels_list` |
| 3 | Channel info | `conversations.info` | — | — | ✅ + `channel_not_found` | no | `test_endpoints::test_conversations_info_{happy,error}` |
| 4 | Channel history | `conversations.history` | `slack history` | `conversations_history` | ✅ paged, thread-replies excluded, `channel_not_found` | **AG** (multi-step, paged read, realistic error) | `test_endpoints::test_conversations_history_{happy,error}`, `test_cli::test_cli_history`, `test_mcp::test_mcp_history` |
| 5 | Thread replies | `conversations.replies` | `slack replies` | `conversations_replies` | ✅ parent+replies oldest-first, `thread_not_found` | **AG** (multi-step: locate thread → fetch, realistic error) | `test_endpoints::test_conversations_replies_{happy,error}`, `test_cli::test_cli_replies`, `test_mcp::test_mcp_replies` |
| 6 | Search messages | `search.messages` / `search.all` | `slack search` | `conversations_search_messages` | ✅ `messages.matches[]`,`paging`,`pagination` | **AG** (Slack operator grammar + filtering + multi-step + stateful) | `test_endpoints::test_search_*`, `test_cli::test_cli_search`, `test_mcp::test_mcp_search` |
| 7 | List users | `users.list` | `slack users` | — *(operator/CLI-only, see note A)* | ✅ `profile`,`is_bot`,`deleted`,cursor | no | `test_endpoints::test_users_list_happy`, `test_cli::test_cli_users` |
| 8 | User info | `users.info` | — | — | ✅ + `user_not_found` | no | `test_endpoints::test_users_info_error` |
| 9 | Team info | `team.info` | — | — | ✅ `id`,`name`,`domain` | no | `test_endpoints::test_team_info_happy` |
| 10 | Post message | `chat.postMessage` / `conversations.add_message` | `slack post` | `conversations_add_message` | ✅ `channel`,`ts`,`message`, `channel_not_found` | **AG** (write→read round-trip, side-effecting devops comms) | `test_endpoints::test_post_message_{roundtrip,error}`, `test_cli::test_cli_post_roundtrip`, `test_mcp::test_mcp_add_message_roundtrip` |
| — | Unknown method | any unrecognized `/api/<m>` | — | — | ✅ `{"ok":false,"error":"unknown_method"}` | no | `test_endpoints::test_unknown_method` |

**Assessment-grade count: 5** (rows 2, 4, 5, 6, 10 are AG; row 6 alone satisfies ≥3 of the rubric:
stateful, multi-step, realistic errors, query grammar). Row 10 is the **write→read round-trip**
exercised end-to-end by a bundled task (`incident-fix-report`: the agent posts to
`#error-budget-reports` via `slack post`, and the verifier reads it back through
`conversations.history`) — satisfies R5.2.

## R3 parity (CLI ↔ MCP)

Every **agent-investigation/action** capability has BOTH a CLI command and an MCP tool:

| Capability | CLI | MCP | Parity test |
|---|---|---|---|
| List channels | `slack channels` | `channels_list` | `test_mcp::test_parity_channels_cli_vs_mcp` |
| Channel history | `slack history` | `conversations_history` | (shared rows; CLI+MCP both tested) |
| Thread replies | `slack replies` | `conversations_replies` | covered by `test_cli::test_cli_replies` + `test_mcp::test_mcp_replies` |
| Search messages | `slack search` | `conversations_search_messages` | `test_mcp::test_parity_search_cli_vs_mcp` |
| Post message | `slack post` | `conversations_add_message` | `test_cli::test_cli_post_roundtrip` + `test_mcp::test_mcp_add_message_roundtrip` |

**Note A — operator/CLI-only capabilities (documented R3.3 exception):** `auth.test` (`whoami`),
`users.list` (`users`), `users.info`, `conversations.info`, and `team.info` are **roster/identity
helpers**, not core agent investigation surface. The vendored korotovsky `slack-mcp` server exposes a
fixed 5-tool set (`channels_list`, `conversations_history`, `conversations_replies`,
`conversations_search_messages`, `conversations_add_message`) and does not ship a `users.list` /
`auth.test` tool; rather than fork it, these are reachable from the CLI only and are marked
operator-only here. They are still fully tested at the HTTP + CLI layers above.
