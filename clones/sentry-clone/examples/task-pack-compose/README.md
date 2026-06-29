# Sentry-Clone Task-Pack Compose Example

This example models how task packs should consume the reusable sidecar.

- The `agent` image copies `/usr/local/bin/sentry`, `/usr/local/bin/sentry-mcp`, and `/opt/sentry-clone-cli`.
- The `agent` image does not copy `/usr/local/bin/sentry-clonectl`.
- The agent receives `SENTRY_AUTH_TOKEN`, not `SENTRY_CLONE_ADMIN_TOKEN`.
- The raw seed file is mounted only into the `sentry` sidecar.
- Verifiers can exec into the sidecar with `SENTRY_CLONE_ADMIN_TOKEN` to inspect mutation logs.
