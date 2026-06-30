# Incident triage: PAYMENTS-501

A production incident has been firing on the `payments-api` project. You have the
`sentry` CLI and the `sentry-mcp` MCP server wired up (pointed at the Sentry workspace
via `$SENTRY_URL`). The seeded incident is reachable **only** through those tools.

Your job — use the tools to investigate, then close the loop in Sentry:

1. Investigate issue **PAYMENTS-501**: read its latest event stacktrace and the
   suspect commit to find the release that introduced the regression.
2. **Resolve** PAYMENTS-501 in the release that shipped the fix
   (`payments-api@2026.06.07.2`), so it is marked resolved on a later read.
3. **Comment** on PAYMENTS-501 with your root-cause note so the on-call has a record.

The verifier reads the workspace back through the Sentry API: PAYMENTS-501 must be
`resolved` AND carry a new agent-authored comment. Narration in chat is not graded —
only the state you leave in Sentry.
