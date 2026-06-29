# Task Integration

Best format for Harbor/Oddish/TB3 tasks:

- `main`: thin agent image with the editable repo and the CLIs the agent should use.
- `github`: `ghcr.io/abundant-ai/ghc-service:latest` sidecar, with task-specific GitHub state.
- Optional sidecars: `ticketvector` for Linear/Jira and `slack` for Slack, just like `slack-linear-incident-ops`.

This keeps backend state out of the agent workspace while giving the agent a normal `gh` command.

## Compose Pattern

Use this alongside Slack and TicketVector:

```yaml
services:
  main:
    build:
      context: .
      dockerfile: Dockerfile
    image: ${MAIN_IMAGE_NAME}
    working_dir: /app/src
    environment:
      GH_HOST: http://github
      GH_TOKEN_FILE: /run/secrets/token
      WORLD_ISSUES_AGENT_MODE: "1"
      WORLD_ISSUES_BACKEND: remote
      WORLD_ISSUES_OUTPUT: json
      WORLD_ISSUES_ACTOR: agent
      PLANE_BASE_URL: http://127.0.0.1:8765
      PYTHONPATH: /opt/ticketvector:/opt/slackcli
      SLACK_API_URL: http://slack
      SLACK_BOT_TOKEN: test-token-acme-eval
    volumes:
      - ghc-shared:/run/secrets:ro
    depends_on:
      github:
        condition: service_healthy
      slack:
        condition: service_healthy

  github:
    image: ghcr.io/abundant-ai/ghc-service:latest
    hostname: github
    volumes:
      - ghc-shared:/shared
      - ./data/github/seed.sh:/usr/local/bin/task-seed.sh:ro
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost/api/healthz >/dev/null || exit 1"]
      interval: 5s
      timeout: 5s
      retries: 60
      start_period: 45s

  ticketvector:
    image: ghcr.io/abundant-ai/ticketvector-service:main
    network_mode: service:main
    environment:
      WORLD_ISSUES_STATE_FILE: /var/lib/ticketvector/state.json
      WORLD_ISSUES_BIND_HOST: 0.0.0.0
      WORLD_ISSUES_PORT: "8765"
      WORLD_ISSUES_ACTOR: agent
    volumes:
      - ./data/ticketvector/state.json:/var/lib/ticketvector/state.json

  slack:
    image: ghcr.io/abundant-ai/slack-service:latest
    environment:
      SLACK_BOT_TOKEN: test-token-acme-eval
    volumes:
      - ./data/slack:/data/mattermost:ro
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:80/api/auth.test >/dev/null || exit 1"]
      interval: 5s
      timeout: 5s
      retries: 24
      start_period: 30s

volumes:
  ghc-shared:
```

The `github` sidecar writes its token to `/shared/token`. The agent reads it as
`/run/secrets/token` because the same volume is mounted into `main` at
`/run/secrets`:

```yaml
main:
  volumes:
    - ghc-shared:/run/secrets:ro
  environment:
    GH_HOST: http://github
    GH_TOKEN_FILE: /run/secrets/token
```

## Agent Dockerfile

Copy the agent-visible tools from service images, then copy only the editable app:

```dockerfile
FROM ghcr.io/abundant-ai/ghc-service:latest AS gh-tools
FROM ghcr.io/abundant-ai/ticketvector-service:main AS ticketvector-tools
FROM ghcr.io/abundant-ai/slack-service:latest AS slack-tools
FROM python:3.11-slim

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    curl jq git ca-certificates bash && \
    rm -rf /var/lib/apt/lists/*

RUN id agent >/dev/null 2>&1 || useradd --create-home --shell /bin/bash agent

COPY --from=gh-tools /usr/local/bin/gh /usr/local/bin/gh
COPY --from=gh-tools /usr/local/bin/ghc /usr/local/bin/ghc
COPY --from=ticketvector-tools /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/
COPY --from=ticketvector-tools /opt/ticketvector /opt/ticketvector
COPY --from=slack-tools /usr/local/bin/slack /usr/local/bin/slack-mcp /usr/local/bin/
COPY --from=slack-tools /opt/slackcli /opt/slackcli

COPY shared/my-task/app-src /app/src

RUN git -C /app/src init && \
    git -C /app/src config user.email agent@example.local && \
    git -C /app/src config user.name "Agent User" && \
    git -C /app/src add . && \
    git -C /app/src commit -m "Initial task snapshot" && \
    chown -R agent:agent /app/src

WORKDIR /app/src
USER agent
ENV GH_HOST=http://github \
    GH_TOKEN_FILE=/run/secrets/token \
    WORLD_ISSUES_AGENT_MODE=1 \
    WORLD_ISSUES_BACKEND=remote \
    WORLD_ISSUES_OUTPUT=json \
    WORLD_ISSUES_ACTOR=agent \
    PLANE_BASE_URL=http://127.0.0.1:8765 \
    PYTHONPATH=/opt/ticketvector:/opt/slackcli:${PYTHONPATH} \
    SLACK_API_URL=http://slack \
    SLACK_BOT_TOKEN=test-token-acme-eval
CMD ["sleep", "infinity"]
```

## GitHub Seed

Mount a task-specific `environment/data/github/seed.sh` into the `github` sidecar.
The service runs it after creating the admin user and token.

```bash
#!/usr/bin/env bash
set -euo pipefail

gh repo create payments --description "payment service"
tmp="$(mktemp -d)"
git clone http://localhost/acme/payments.git "$tmp/payments"
cd "$tmp/payments"
git config user.email seed@example.local
git config user.name "Seed User"
git checkout -b main
cat > README.md <<'EOF'
# Payments
EOF
git add README.md
git commit -m "Initial payment service"
git push -u origin main

gh issue create -R acme/payments \
  -t "Fix payment retry policy" \
  -b "Use Slack and Linear context, patch the repo, and open a PR."
```

The seed script runs inside the `github` sidecar with `GH_HOST=http://localhost`
and `GH_TOKEN` already set. The agent should use `GH_HOST=http://github`.

## Agent Workflow

A GitHub-enabled incident task can require the agent to:

1. Find the work item with `linear` or `jira`.
2. Recover operational context with `slack`.
3. Inspect the affected repo with `gh issue view`, `gh repo clone`, and `gh pr`.
4. Modify code in `/app/src` or a cloned repo.
5. Commit, push a branch, and open a PR with `gh pr create`.
6. Add ticket evidence and Slack handoff.
7. Move the issue to review.

Good verifier checks:

- `gh` PR exists with the expected title/body/head branch.
- PR diff contains the intended code change and no unrelated files.
- TicketVector state has evidence, commit/PR link, owner, and review transition.
- Slack completion message references the PR and task-specific evidence.
- Distractor repos/issues remain untouched.

## Which Image To Use

Use `ghcr.io/abundant-ai/ghc-service:latest` for tasks. The older split images
were useful while developing the clone, but the service-image pattern is better
for reusable task packs because it matches Slack and TicketVector:

- one public image per cloned product
- task-specific state mounted into sidecars
- thin `main` image with only agent-visible tools and editable code
