# Creating Tasks

Make Sentry evidence necessary, but do not leak the answer through raw state or verifier-only APIs.

Recommended flow:

1. Linear or Jira ticket points to a production exception or incident.
2. Slack provides noisy operational context and competing hypotheses.
3. Sentry-clone contains the grouped issue, latest event, stacktrace, breadcrumbs, suspect commit, release, affected users, and status.
4. The agent fixes code and runs tests or a replay.
5. The agent opens a GitHub PR.
6. Only after tests or replay pass, the agent comments on and resolves the Sentry issue.
7. The agent posts Slack and Linear/Jira handoff citing the Sentry issue, event, suspect commit, PR, and replay evidence.

Warnings:

- Do not mount raw Sentry-clone state into the agent container.
- Do not copy `sentry-clonectl` into the agent image.
- Do not pass `SENTRY_CLONE_ADMIN_TOKEN` to the agent.
- Keep `/api/_clone/*` endpoints verifier-only.
- Keep multiple plausible hypotheses in Slack or tickets; use stacktrace, breadcrumbs, release, and suspect commits to disambiguate.
