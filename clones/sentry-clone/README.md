# sentry-clone

`sentry-clone` is a local Sentry-compatible error monitoring clone for SWE and on-call agent benchmarks. It provides grouped issues, events, stack traces, breadcrumbs, releases, suspect commits, ownership, comments, status transitions, and verifier-visible mutation logs without requiring Sentry Cloud, external auth, internet access, or a live Sentry service.

This project is not Sentry and is unaffiliated with Sentry. It implements a benchmark-focused API subset with Sentry-shaped JSON where practical.

## Quick Start

```sh
docker compose -f examples/docker-compose.yaml up -d --build
curl -sf http://localhost:3000/api/healthz
SENTRY_URL=http://localhost:3000 SENTRY_AUTH_TOKEN=test-token-acme-eval bin/sentry issues list --project payments-api --query 'is:unresolved' --json
```

The service reads a read-only seed from `/data/sentry-clone/state.json`, copies it to `/var/lib/sentry-clone/state.json` on startup, and mutates only the runtime copy.

## Task-Pack Sidecar Shape

Agent images should copy only:

```Dockerfile
COPY --from=sentry-tools /usr/local/bin/sentry /usr/local/bin/sentry-mcp /usr/local/bin/
COPY --from=sentry-tools /opt/sentry-clone-cli /opt/sentry-clone-cli
ENV PYTHONPATH=/opt/sentry-clone-cli:${PYTHONPATH}
ENV SENTRY_URL=http://sentry
ENV SENTRY_AUTH_TOKEN=test-token-acme-eval
ENV SENTRY_ORG=acme
```

Do not copy `sentry-clonectl` into agent images. Do not pass `SENTRY_CLONE_ADMIN_TOKEN` to the agent. Do not mount raw Sentry-clone state into the agent container.

The sidecar service image is published as:

```text
ghcr.io/abundant-ai/sentry-clone-service:main
ghcr.io/abundant-ai/sentry-clone-service:sha-<shortsha>
```

Use `:main` for quick local testing. Use `:sha-<shortsha>` for task-pack references, and add a digest pin when freezing benchmark inputs.

See `examples/task-pack-compose/` for a runnable two-container example.

## Tools

- `/usr/local/bin/sentry`: agent-facing CLI.
- `/usr/local/bin/sentry-mcp`: agent-facing stdio MCP server.
- `/usr/local/bin/sentry-clonectl`: verifier/admin-only debug CLI.

More details:

- `docs/TOOLS.md`
- `docs/STATE_SCHEMA.md`
- `docs/API_COMPATIBILITY.md`
- `docs/CREATING-TASKS.md`
- `docs/IMAGE-RELEASE.md`
