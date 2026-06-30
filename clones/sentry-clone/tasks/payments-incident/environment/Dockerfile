# Agent (`main`) container — Harbor builds this automatically as the agent's image.
# Neutral python base, data-free, carrying ONLY the agent's tools (the `sentry` CLI +
# the `sentry-mcp` MCP server, thin HTTP clients of the gateway). The gateway's HTTP
# API + state/seed source (sentry_clone.server) is STRIPPED so the seeded incident is
# neither greppable nor recomputable on the agent — state is reachable solely over HTTP
# at $SENTRY_URL. `sentry-clonectl` (admin) is deliberately NOT installed.
FROM python:3.10-slim

RUN useradd --create-home --shell /bin/sh agent

COPY sentryclone/sentry_clone /opt/sentry-clone-cli/sentry_clone
COPY sentryclone/bin/sentry sentryclone/bin/sentry-mcp /usr/local/bin/
RUN chmod +x /usr/local/bin/sentry /usr/local/bin/sentry-mcp && \
    rm -rf /opt/sentry-clone-cli/sentry_clone/server && \
    find /opt/sentry-clone-cli -name '__pycache__' -type d -prune -exec rm -rf {} +

COPY codebase /workspace

ENV PYTHONPATH=/opt/sentry-clone-cli \
    SENTRY_URL=http://sentry \
    SENTRY_AUTH_TOKEN=test-token-acme-eval \
    SENTRY_ORG=acme

USER agent
WORKDIR /workspace
CMD ["sleep", "infinity"]
